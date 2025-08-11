
import asyncio
import json
import logging
import signal
import math
from datetime import datetime
from typing import Dict, Any
import sys

import networkx as nx
import aio_pika
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
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "package_tracker")
PACKAGES_COLLECTION = os.getenv("PACKAGES_COLLECTION", "packages")
GRAPH_PATH = os.getenv("GRAPH_PATH", "/home/adi/dev/distpack/graph_data/world_graph.gpickle")

continents = {
    "North America": ["New York", "Los Angeles", "Toronto", "Chicago", "Houston", "Vancouver", "San Francisco", "Mexico City", "Miami", "Atlanta", "Montreal", "Seattle", "Boston", "Phoenix", "Dallas"],
    "South America": ["Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago", "Caracas", "Quito", "La Paz", "Montevideo", "Asuncion", "Cali", "Medellin", "Rio de Janeiro", "Brasilia", "Salvador"],
    "Europe": ["London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Zurich", "Oslo", "Warsaw", "Lisbon", "Dublin", "Prague", "Budapest", "Copenhagen"],
    "Africa": ["Lagos", "Cairo", "Nairobi", "Accra", "Johannesburg", "Algiers", "Casablanca", "Addis Ababa", "Dakar", "Tunis", "Kampala", "Luanda", "Abidjan", "Harare", "Gaborone"],
    "Asia": ["Tokyo", "Beijing", "Shanghai", "Delhi", "Mumbai", "Seoul", "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Hanoi", "Manila", "Taipei", "Dhaka", "Riyadh"],
    "Oceania": ["Sydney", "Melbourne", "Auckland", "Brisbane", "Perth", "Wellington", "Adelaide", "Canberra", "Hobart", "Gold Coast", "Darwin", "Hamilton", "Christchurch", "Suva", "Noumea"]
}

# Simulation speed: 1 real second = 2 simulated hours -> 0.5 real seconds per simulated hour
REAL_SECONDS_PER_SIM_HOUR = 1.0 / 1.0  

# Concurrency limit (how many simulations run in parallel)
MAX_CONCURRENT_SIMULATIONS = int(os.getenv("MAX_SIM", "8"))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sim-service")


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
running = True

def get_region_from_city(city_name: str) -> str:
    """Helper function to find the region for a given city."""
    for region, cities in continents.items():
        if city_name in cities:
            return region
    return ""

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
    Push a history entry into the package doc and set updated status and location.
    """
    global db
    coll = db[PACKAGES_COLLECTION]
    await coll.update_one(
        {"package_id": package_id},
        {
            "$push": {"history": entry},
            "$set": {
                "updated_at": datetime.utcnow().isoformat(),
                "status": entry.get("status"),
                "location": entry.get("location")
            }
        },
    )

async def mark_package_status(package_id: str, status: str):
    global db
    coll = db[PACKAGES_COLLECTION]
    await coll.update_one({"package_id": package_id}, {"$set": {"status": status, "updated_at": datetime.utcnow().isoformat()}})

# Assuming the 'continents' dictionary and 'get_region_from_city' helper
# function are defined elsewhere in your code, as shown in previous responses.

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

    source = pkg.get("origin")
    dest = pkg.get("destination")
    metric = pkg.get("metric", "time")

    if isinstance(source, dict):
        source = source.get("city")
    else:
        source = str(source)

    if isinstance(dest, dict):
        dest = dest.get("city")
    else:
        dest = str(dest)

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

            # On arrival push history entry and update location
            # Get the correct region for the city `v`
            location = {"city": v, "region": get_region_from_city(v)}

            entry = {
                "location": location,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "IN_TRANSIT", # Set status to IN_TRANSIT at intermediate stops
                "edge_from": u,
                "edge_distance_km": round(edge_dist, 2),
                "edge_cost_usd": round(edge_cost, 2),
                "edge_time_hr": round(edge_time, 2),
                "edge_risk": round(edge_risk, 4),
            }
            
            # This call updates the history, status, and location simultaneously
            await push_history_and_status(package_id, entry)
            logger.info("Package %s arrived at %s (edge %s->%s)", package_id, v, u, v)

        # Completed delivery
        await coll.update_one(
            {"package_id": package_id},
            {
                "$set": {
                    "status": "DELIVERED",
                    "delivered_at": datetime.utcnow().isoformat(),
                    # Set the final location to the destination city
                    "location": {"city": dest, "region": get_region_from_city(dest)},
                }
            }
        )
        logger.info("Package %s delivered. route=%s, total_time_hr=%.2f", package_id, path, total_time)

    except Exception as e:
        logger.exception("Error during simulation for %s: %s", package_id, e)
        await mark_package_status(package_id, "FAILED")
        return

async def consume_loop():
    global sim_semaphore, running

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    
    queue = await channel.declare_queue("package_created", durable=True)

    async with queue.iterator() as queue_iter:
        logger.info("RabbitMQ consumer started, listening on queue 'package_created'")
        async for message in queue_iter:
            if not running:
                break
            async with message.process():
                try:
                    payload = json.loads(message.body.decode())
                    pkg_msg = PackageCreated(**payload)
                except Exception as e:
                    logger.warning(f"Received invalid package message: {message.body} | error: {e}")
                    continue

                async def _run_sim(pkg_id: str):
                    async with sim_semaphore:
                        try:
                            await simulate_package(pkg_id)
                        except Exception as e:
                            logger.exception(f"simulation task error for {pkg_id}: {e}")

                logger.info(f"Received package_created event: {pkg_msg.package_id}")
                asyncio.create_task(_run_sim(pkg_msg.package_id))

    await connection.close()
    logger.info("RabbitMQ consumer stopped")


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