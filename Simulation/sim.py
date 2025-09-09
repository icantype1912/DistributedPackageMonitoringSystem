# sim.py -- multi-region / sharded-aware simulator
import asyncio
import json
import logging
import sys
from datetime import datetime,UTC
from typing import Dict, Any
import os
import pickle

import networkx as nx
import aio_pika
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG (env-backed, fallbacks) ---
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
GRAPH_PATH = os.getenv("GRAPH_PATH", "graph.pkl")
REAL_SECONDS_PER_SIM_HOUR = float(os.getenv("REAL_SECONDS_PER_SIM_HOUR", "1.0"))
MAX_CONCURRENT_SIMULATIONS = int(os.getenv("MAX_SIM", "8"))
PACKAGES_COLLECTION = os.getenv("PACKAGES_COLLECTION", "packages")

# --- CONTINENTS / CITIES (same as your data) ---
continents = {
    "NA": ["New York", "Los Angeles", "Toronto", "Chicago", "Houston", "Vancouver", "San Francisco", "Mexico City", "Miami", "Atlanta", "Montreal", "Seattle", "Boston", "Phoenix", "Dallas"],
    "SA": ["Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago", "Caracas", "Quito", "La Paz", "Montevideo", "Asuncion", "Cali", "Medellin", "Rio de Janeiro", "Brasilia", "Salvador"],
    "Europe": ["London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Zurich", "Oslo", "Warsaw", "Lisbon", "Dublin", "Prague", "Budapest", "Copenhagen"],
    "Africa": ["Lagos", "Cairo", "Nairobi", "Accra", "Johannesburg", "Algiers", "Casablanca", "Addis Ababa", "Dakar", "Tunis", "Kampala", "Luanda", "Abidjan", "Harare", "Gaborone"],
    "Asia": ["Tokyo", "Beijing", "Shanghai", "Delhi", "Mumbai", "Seoul", "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Hanoi", "Manila", "Taipei", "Dhaka", "Riyadh"],
    "Oceania": ["Sydney", "Melbourne", "Auckland", "Brisbane", "Perth", "Wellington", "Adelaide", "Canberra", "Hobart", "Gold Coast", "Darwin", "Hamilton", "Christchurch", "Suva", "Noumea"]
}

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sim-service")

# --- Pydantic for incoming RabbitMQ package events ---
class PackageCreated(BaseModel):
    package_id: str
    source: str
    destination: str
    metric: str
    metadata: Dict[str, Any] = {}

# --- Multi-region MongoDB connections (one client / DB per container) ---
# NOTE: these URIs assume Mongo containers are exposed on localhost ports as in your docker-compose.
db_asia = AsyncIOMotorClient("mongodb://localhost:27018")["asia"]
db_europe = AsyncIOMotorClient("mongodb://localhost:27019")["europe"]
db_na = AsyncIOMotorClient("mongodb://localhost:27020")["na"]
db_sa = AsyncIOMotorClient("mongodb://localhost:27021")["sa"]
db_africa = AsyncIOMotorClient("mongodb://localhost:27022")["africa"]
db_oceania = AsyncIOMotorClient("mongodb://localhost:27023")["oceania"]

# Global Index DB (keeps package_id -> current_region)
db_index = AsyncIOMotorClient("mongodb://localhost:27024")["index"]

REGION_DBS = {
    "Asia": db_asia,
    "Europe": db_europe,
    "NA": db_na,
    "SA": db_sa,
    "Africa": db_africa,
    "Oceania": db_oceania,
}

# --- Globals filled at startup ---
graph: nx.DiGraph = None
sim_semaphore: asyncio.Semaphore = None
running = True

# --- Helpers ---
def get_region_from_city(city_name: str) -> str:
    for region, cities in continents.items():
        if city_name in cities:
            return region
    return ""

def accumulated_risk_from_path(graph: nx.DiGraph, path: list) -> float:
    survival = 1.0
    for i in range(len(path) - 1):
        edge = graph[path[i]][path[i + 1]]
        r = float(edge.get("risk", 0.0))
        r = min(max(r, 0.0), 1.0)
        survival *= (1.0 - r)
    return 1.0 - survival

# --- DB operations aware of region (history/status) ---
async def push_history_and_status(region: str, package_id: str, entry: dict):
    coll = REGION_DBS[region][PACKAGES_COLLECTION]
    await coll.update_one(
        {"package_id": package_id},
        {
            "$push": {"history": entry},
            "$set": {
                "updated_at": datetime.now(UTC).isoformat(),
                "status": entry.get("status"),
                "location": entry.get("location"),
            },
        },
    )

async def mark_package_status(region: str, package_id: str, status: str):
    coll = REGION_DBS[region][PACKAGES_COLLECTION]
    await coll.update_one(
        {"package_id": package_id},
        {"$set": {"status": status, "updated_at": datetime.now(UTC).isoformat()}},
    )

# --- Move package between regions (preserve history + fields) ---
async def move_package_to_new_region(package_id: str, new_region: str, old_region: str, channel: aio_pika.RobustChannel | None = None):
    """
    Move the package doc from old_region DB to new_region DB.
    - Reads from old_region
    - Inserts into new_region (removes _id so new server assigns a new ObjectId)
    - Deletes from old_region
    - Updates index DB current_region
    - Publishes package_region_changed on RabbitMQ (if channel provided)
    """
    old_coll = REGION_DBS[old_region][PACKAGES_COLLECTION]
    new_coll = REGION_DBS[new_region][PACKAGES_COLLECTION]

    pkg = await old_coll.find_one({"package_id": package_id})
    if not pkg:
        logger.error("move_package: package not found in old region %s: %s", old_region, package_id)
        return False

    # Clean _id (avoid ObjectId collision across different Mongo instances)
    pkg_to_insert = dict(pkg)
    if "_id" in pkg_to_insert:
        del pkg_to_insert["_id"]

    # Ensure location reflects entry into new region (will be set by simulation loop)
    # Insert into new region
    await new_coll.insert_one(pkg_to_insert)
    # Delete from old region
    await old_coll.delete_one({"package_id": package_id})
    # Update index DB
    await db_index["packages"].update_one({"package_id": package_id}, {"$set": {"current_region": new_region, "last_updated": datetime.now(UTC).isoformat()}})

    logger.info("move_package: moved %s from %s -> %s", package_id, old_region, new_region)

    # Publish event that region changed
    if channel:
        body = json.dumps({
            "package_id": package_id,
            "old_region": old_region,
            "new_region": new_region,
            "timestamp": datetime.now(UTC).isoformat()
        }).encode()
        try:
            await channel.default_exchange.publish(
                aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key="package_region_changed"
            )
            logger.info("Published package_region_changed for %s", package_id)
        except Exception as e:
            logger.warning("Failed to publish region change for %s: %s", package_id, e)

    return True

# --- Core simulation function (region-aware) ---
async def simulate_package(package_id: str):
    """
    Main simulation:
      - look up package region in index DB
      - read package from that region's DB
      - compute route
      - for each hop: sleep (simulate time), when entering a city check its region:
           - if region changed: move package between DBs and update index
           - add history entry into current region DB
      - mark delivered at end
    """
    # find starting region using index DB
    idx = await db_index["packages"].find_one({"package_id": package_id})
    if not idx:
        logger.warning("simulate_package: package not found in index DB: %s", package_id)
        return

    current_region = idx.get("current_region")
    if current_region not in REGION_DBS:
        logger.error("simulate_package: unknown current_region '%s' for %s", current_region, package_id)
        return

    coll = REGION_DBS[current_region][PACKAGES_COLLECTION]
    pkg = await coll.find_one({"package_id": package_id})
    if not pkg:
        logger.error("simulate_package: package not found in region DB %s: %s", current_region, package_id)
        return

    # extract source/dest
    source = pkg.get("origin", {}).get("city") if isinstance(pkg.get("origin"), dict) else pkg.get("origin")
    dest = pkg.get("destination", {}).get("city") if isinstance(pkg.get("destination"), dict) else pkg.get("destination")
    metric = pkg.get("metric", "time")
    logger.info("Starting simulation %s: %s -> %s (metric=%s) [region=%s]", package_id, source, dest, metric, current_region)

    # compute route
    try:
        path = nx.dijkstra_path(graph, source, dest, weight=metric)
    except nx.NetworkXNoPath:
        logger.error("No path for %s -> %s", source, dest)
        await mark_package_status(current_region, package_id, "FAILED_NO_PATH")
        return
    except Exception as e:
        logger.exception("Error computing path for %s: %s", package_id, e)
        await mark_package_status(current_region, package_id, "FAILED")
        return

    # compute totals
    total_distance = total_cost = total_time = 0.0
    for i in range(len(path) - 1):
        e = graph[path[i]][path[i + 1]]
        total_distance += float(e.get("distance", 0.0))
        total_cost += float(e.get("cost", 0.0))
        total_time += float(e.get("time", 0.0))
    accumulated_risk = accumulated_risk_from_path(graph, path)

    # update initial package doc in whichever region it currently lives
    await REGION_DBS[current_region][PACKAGES_COLLECTION].update_one(
        {"package_id": package_id},
        {"$set": {
            "route": path,
            "total_distance_km": round(total_distance, 2),
            "total_cost_usd": round(total_cost, 2),
            "total_time_hr": round(total_time, 2),
            "accumulated_risk": round(accumulated_risk, 6),
            "status": "IN_TRANSIT",
            "started_at": datetime.now(UTC).isoformat()
        }}
    )

    # we'll open one publisher channel for region-change publishes during the sim run
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()

    try:
        prev_region = current_region
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            edge = graph[u][v]

            # simulate travel time
            edge_time = float(edge.get("time", 0.0))
            sleep_seconds = edge_time * REAL_SECONDS_PER_SIM_HOUR
            logger.info("Package %s: hop %s -> %s time=%.2f hr -> sleep %.3f s", package_id, u, v, edge_time, sleep_seconds)
            await asyncio.sleep(sleep_seconds)

            # determine region of arrival city
            arrival_region = get_region_from_city(v)
            if arrival_region == "":
                # unknown city -> still record in previous region's doc
                arrival_region = prev_region

            # if region changed, move the package doc between region DBs and update index
            if arrival_region != prev_region:
                moved = await move_package_to_new_region(package_id, arrival_region, prev_region, channel)
                if not moved:
                    # couldn't move; mark failure and stop
                    await mark_package_status(prev_region, package_id, "FAILED_MOVE")
                    logger.error("Failed to move package %s from %s to %s", package_id, prev_region, arrival_region)
                    await connection.close()
                    return
                # now current document lives in arrival_region
                prev_region = arrival_region

            # push history + status into whichever region currently holds the package
            entry = {
                "location": {"city": v, "region": arrival_region},
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "IN_TRANSIT",
                "edge_from": u,
                "edge_distance_km": round(float(edge.get("distance", 0.0)), 2),
                "edge_cost_usd": round(float(edge.get("cost", 0.0)), 2),
                "edge_time_hr": round(edge_time, 2),
                "edge_risk": round(float(edge.get("risk", 0.0)), 4),
            }
            await push_history_and_status(arrival_region, package_id, entry)
            logger.info("Package %s arrived at %s (region=%s)", package_id, v, arrival_region)

        # final delivery update on the region that currently holds the doc
        await REGION_DBS[prev_region][PACKAGES_COLLECTION].update_one(
            {"package_id": package_id},
            {"$set": {
                "status": "DELIVERED",
                "delivered_at": datetime.now(UTC).isoformat(),
                "location": {"city": dest, "region": get_region_from_city(dest)}
            }}
        )
        logger.info("Package %s delivered (route=%s)", package_id, path)

    except Exception as e:
        logger.exception("Error during simulation for %s: %s", package_id, e)
        # attempt to mark package as failed in whichever region currently holds it
        try:
            await mark_package_status(prev_region, package_id, "FAILED")
        except Exception:
            logger.exception("Also failed to mark package as FAILED in region %s", prev_region)
    finally:
        await connection.close()

# --- Consumer (receives package_id messages and schedules sims) ---
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
                    logger.warning("Invalid package message: %s | error: %s", message.body, e)
                    continue

                async def _run_sim(pkg_id: str):
                    async with sim_semaphore:
                        try:
                            await simulate_package(pkg_id)
                        except Exception as e:
                            logger.exception("simulation task error for %s: %s", pkg_id, e)

                logger.info("Received package_created event: %s", pkg_msg.package_id)
                asyncio.create_task(_run_sim(pkg_msg.package_id))

    await connection.close()
    logger.info("RabbitMQ consumer stopped")

# --- Startup / Shutdown ---
async def start_service_and_run_forever():
    global graph, sim_semaphore

    logger.info("Loading graph from %s", GRAPH_PATH)
    if not GRAPH_PATH or not os.path.exists(GRAPH_PATH):
        logger.error("Graph file not found at: %s", GRAPH_PATH)
        sys.exit(1)

    with open(GRAPH_PATH, "rb") as f:
        graph = pickle.load(f)
    logger.info("Graph loaded: nodes=%d edges=%d", graph.number_of_nodes(), graph.number_of_edges())

    sim_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SIMULATIONS)

    await consume_loop()

def _shutdown():
    global running
    running = False
    logger.info("Shutdown requested")

if __name__ == "__main__":
    try:
        asyncio.run(start_service_and_run_forever())
    except asyncio.CancelledError:
        logger.info("Shutdown complete")
    except Exception as e:
        logger.exception("Unhandled exception: %s", e)
    finally:
        # close motor clients (each REGION_DBS entry is a Database object; .client is the AsyncIOMotorClient)
        for db_obj in [db_asia, db_europe, db_na, db_sa, db_africa, db_oceania]:
            try:
                db_obj.client.close()
            except Exception:
                pass
        try:
            db_index.client.close()
        except Exception:
            pass
        sys.exit(0)
