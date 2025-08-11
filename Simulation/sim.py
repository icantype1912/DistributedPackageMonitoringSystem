"""
simulation_service.py

Async simulation microservice:
 - consumes messages from Kafka topic 'package_created'
 - reads package doc from MongoDB
 - computes shortest path on world_graph.gpickle using chosen metric
 - simulates travel: 1 real second = 2 simulation hours => 0.5s per 1 simulated hour
 - updates package history in MongoDB at every node
"""

import asyncio
import json
import logging
import signal
import math
from datetime import datetime
from typing import Dict, Any
import sys

import networkx as nx
from aiokafka import AIOKafkaConsumer
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import pickle

load_dotenv()

async def main():
    global running
    try:
        await start_service()
    except asyncio.CancelledError:
        logger.info("Main task cancelled, shutting down...")

# --- CONFIG (can also be set via env) ---
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "package_created")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "package_tracker")
PACKAGES_COLLECTION = os.getenv("PACKAGES_COLLECTION", "packages")
GRAPH_PATH = os.getenv("GRAPH_PATH", "/home/adi/dev/distpack/graph_engine/graph_data/world_graph.gpickle")

# Simulation speed: 1 real second = 2 simulated hours -> 0.5 real seconds per simulated hour
REAL_SECONDS_PER_SIM_HOUR = 1.0 / 1.0  

# Concurrency limit (how many simulations run in parallel)
MAX_CONCURRENT_SIMULATIONS = int(os.getenv("MAX_SIM", "8"))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sim-service")

# --- Pydantic model for Kafka payload ---
class PackageCreated(BaseModel):
    package_id: str
    source: str
    destination: str
    metric: str  # 'distance' | 'cost' | 'time' | 'risk'
    # optional: additional metadata
    metadata: Dict[str, Any] = {}

# --- Global placeholders (filled at startup) ---
graph: nx.DiGraph = None
mongo_client: AsyncIOMotorClient = None
db = None
sim_semaphore: asyncio.Semaphore = None
consumer: AIOKafkaConsumer = None
running = True


# --- Utility functions ---
def accumulated_risk_from_path(graph: nx.DiGraph, path: list) -> float:
    """Return accumulated risk (1 - product(1 - risk_i))."""
    survival = 1.0
    for i in range(len(path) - 1):
        edge = graph[path[i]][path[i + 1]]
        r = float(edge.get("risk", 0.0))
        # clamp
        r = min(max(r, 0.0), 1.0)
        survival *= (1.0 - r)
    return 1.0 - survival


async def push_history_and_status(package_id: str, entry: dict):
    """
    Push a history entry into the package doc and optionally set an updated status.
    entry example:
      {
        "node": "London",
        "timestamp": ISO str,
        "status": "arrived",
        "edge_distance": ...,
        "edge_cost": ...,
        "edge_time": ...,
        "edge_risk": ...
      }
    """
    global db
    coll = db[PACKAGES_COLLECTION]
    await coll.update_one(
        {"package_id": package_id},
        {"$push": {"history": entry}, "$set": {"updated_at": datetime.utcnow().isoformat()}},
    )


async def mark_package_status(package_id: str, status: str):
    global db
    coll = db[PACKAGES_COLLECTION]
    await coll.update_one({"package_id": package_id}, {"$set": {"status": status, "updated_at": datetime.utcnow().isoformat()}})


# --- Core simulation logic ---
async def simulate_package(package_id: str):
    """
    Read package doc from DB, compute path, and simulate movement.
    This function is an asyncio coroutine and should be run as an asyncio Task.
    """
    global graph, db

    coll = db[PACKAGES_COLLECTION]
    pkg = await coll.find_one({"package_id": package_id})
    if not pkg:
        logger.warning("Package not found in DB: %s", package_id)
        return

    source = pkg.get("source")
    dest = pkg.get("destination")
    metric = pkg.get("metric", "time")

    logger.info("Starting simulation for package %s: %s -> %s (metric=%s)", package_id, source, dest, metric)

    # compute shortest path using chosen metric
    try:
        path = nx.dijkstra_path(graph, source, dest, weight=metric)
        total_metric = nx.dijkstra_path_length(graph, source, dest, weight=metric)
    except nx.NetworkXNoPath:
        logger.error("No path found for %s -> %s", source, dest)
        await mark_package_status(package_id, "FAILED_NO_PATH")
        return
    except Exception as e:
        logger.exception("Error computing path: %s", e)
        await mark_package_status(package_id, "FAILED")
        return

    # calculate totals using edges (distance, cost, time) for reporting
    total_distance = 0.0
    total_cost = 0.0
    total_time = 0.0  # in simulated hours
    for i in range(len(path) - 1):
        e = graph[path[i]][path[i + 1]]
        total_distance += float(e.get("distance", 0.0))
        total_cost += float(e.get("cost", 0.0))
        total_time += float(e.get("time", 0.0))

    accumulated_risk = accumulated_risk_from_path(graph, path)

    # Update package doc with computed route and totals
    await coll.update_one(
        {"package_id": package_id},
        {
            "$set": {
                "route": path,
                "total_distance_km": round(total_distance, 2),
                "total_cost_usd": round(total_cost, 2),
                "total_time_hr": round(total_time, 2),
                "accumulated_risk": round(accumulated_risk, 6),
                "status": "IN_TRANSIT",
                "started_at": datetime.utcnow().isoformat(),
            }
        },
    )

    # For each hop simulate travel and update history when arrived at next node
    try:
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            edge = graph[u][v]
            edge_dist = float(edge.get("distance", 0.0))
            edge_cost = float(edge.get("cost", 0.0))
            edge_time = float(edge.get("time", 0.0))
            edge_risk = float(edge.get("risk", 0.0))

            # compute real sleep seconds: edge_time (hrs) * REAL_SECONDS_PER_SIM_HOUR
            sleep_seconds = edge_time * REAL_SECONDS_PER_SIM_HOUR

            logger.info("Package %s: %s -> %s : time=%.2f hr -> sleeping %.3f s", package_id, u, v, edge_time, sleep_seconds)

            # Wait to emulate travel (non-blocking)
            await asyncio.sleep(sleep_seconds)

            # On arrival push history entry
            entry = {
                "node": v,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "ARRIVED",
                "edge_from": u,
                "edge_distance_km": round(edge_dist, 2),
                "edge_cost_usd": round(edge_cost, 2),
                "edge_time_hr": round(edge_time, 2),
                "edge_risk": round(edge_risk, 4),
            }
            await push_history_and_status(package_id, entry)
            logger.info("Package %s arrived at %s (edge %s->%s)", package_id, v, u, v)

        # Completed delivery
        await mark_package_status(package_id, "DELIVERED")
        await coll.update_one({"package_id": package_id}, {"$set": {"delivered_at": datetime.utcnow().isoformat()}})
        logger.info("Package %s delivered. route=%s, total_time_hr=%.2f", package_id, path, total_time)

    except Exception as e:
        logger.exception("Error during simulation for %s: %s", package_id, e)
        await mark_package_status(package_id, "FAILED")
        return


# --- Kafka consumer loop --- 
async def consume_loop():
    global consumer, sim_semaphore, running

    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=True,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("Kafka consumer started, listening on topic '%s'", KAFKA_TOPIC)

    try:
        async for msg in consumer:
            if not running:
                break
            payload = msg.value
            try:
                pkg_msg = PackageCreated(**payload)
            except Exception as e:
                logger.warning("Received invalid package message: %s | error: %s", payload, e)
                continue

            # Launch simulation task with semaphore limit
            async def _run_sim(pkg_id: str):
                async with sim_semaphore:
                    try:
                        await simulate_package(pkg_id)
                    except Exception as e:
                        logger.exception("simulation task error for %s: %s", pkg_id, e)

            logger.info("Received package_created event: %s", pkg_msg.package_id)
            # prefer package_id from message; if not present skip
            asyncio.create_task(_run_sim(pkg_msg.package_id))

    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped")


# --- Startup and shutdown helpers ---
async def start_service():
    global graph, mongo_client, db, sim_semaphore

    # load graph
    logger.info("Loading graph from %s", GRAPH_PATH)
    with open(GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
# your graph must include edge attributes: distance, cost, time, risk
    logger.info("Graph loaded: nodes=%d edges=%d", graph.number_of_nodes(), graph.number_of_edges())

    # init mongo
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client[MONGO_DB]
    logger.info("Connected to MongoDB: %s/%s", MONGO_URI, MONGO_DB)

    sim_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SIMULATIONS)
    # start consumer loop
    await consume_loop()


def _shutdown():
    global running
    running = False
    logger.info("Shutdown requested")



if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    # Create the main task
    main_task = loop.create_task(main())

    def shutdown():
        global running
        running = False
        logger.info("Shutdown requested")
        main_task.cancel()

    # register signals
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, shutdown)

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logger.info("Shutdown complete")
    finally:
        # Cleanup Mongo and other resources
        if mongo_client:
            mongo_client.close()
        loop.stop()
        loop.close()
        sys.exit(0)