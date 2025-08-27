from fastapi import APIRouter, HTTPException
from models import Package, StatusUpdateRequest, PackageIn, Location, StatusUpdates
from db.routes import insert_package, get_package, move_package
from datetime import datetime
import asyncio
import json
import aio_pika
import os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

# Cities and continents
all_cities = [
    "New York", "Los Angeles", "Toronto", "Chicago", "Houston", "Vancouver", "San Francisco", "Mexico City", "Miami", "Atlanta", "Montreal", "Seattle", "Boston", "Phoenix", "Dallas",
    "Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago", "Caracas", "Quito", "La Paz", "Montevideo", "Asuncion", "Cali", "Medellin", "Rio de Janeiro", "Brasilia", "Salvador",
    "London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Zurich", "Oslo", "Warsaw", "Lisbon", "Dublin", "Prague", "Budapest", "Copenhagen",
    "Lagos", "Cairo", "Nairobi", "Accra", "Johannesburg", "Algiers", "Casablanca", "Addis Ababa", "Dakar", "Tunis", "Kampala", "Luanda", "Abidjan", "Harare", "Gaborone",
    "Tokyo", "Beijing", "Shanghai", "Delhi", "Mumbai", "Seoul", "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Hanoi", "Manila", "Taipei", "Dhaka", "Riyadh",
    "Sydney", "Melbourne", "Auckland", "Brisbane", "Perth", "Wellington", "Adelaide", "Canberra", "Hobart", "Gold Coast", "Darwin", "Hamilton", "Christchurch", "Suva", "Noumea"
]

continents = {
    "NA": all_cities[:15],
    "SA": all_cities[15:30],
    "Europe": all_cities[30:45],
    "Africa": all_cities[45:60],
    "Asia": all_cities[60:75],
    "Oceania": all_cities[75:]
}

# RabbitMQ setup
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
rabbitmq_connection = None
rabbitmq_channel = None
rabbitmq_exchange = None
queue_name = "package_created"

async def start_rabbitmq_producer():
    global rabbitmq_connection, rabbitmq_channel, rabbitmq_exchange
    rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
    rabbitmq_channel = await rabbitmq_connection.channel()
    rabbitmq_exchange = await rabbitmq_channel.declare_exchange(
        "package_exchange", aio_pika.ExchangeType.DIRECT, durable=True
    )
    queue = await rabbitmq_channel.declare_queue(queue_name, durable=True)
    await queue.bind(rabbitmq_exchange, routing_key=queue_name)

async def stop_rabbitmq_producer():
    global rabbitmq_connection
    if rabbitmq_connection:
        await rabbitmq_connection.close()


# Helper: determine region by city
def get_region_from_city(city_name: str) -> str:
    for region, cities in continents.items():
        if city_name in cities:
            return region
    return ""


# Endpoint: list all packages (from all regions via index)
@router.get("/", response_model=list[Package])
async def list_packages():
    # Get all package IDs from index DB
    from db.connections import db_index, REGION_DBS
    cursor = db_index.packages.find()
    index_entries = await cursor.to_list(length=None)

    packages = []
    for entry in index_entries:
        pkg = await REGION_DBS[entry["current_region"]].packages.find_one({"package_id": entry["package_id"]})
        if pkg:
            pkg["_id"] = str(pkg["_id"])
            packages.append(Package(**pkg))
    return packages


# Endpoint: get single package
@router.get("/{package_id}", response_model=Package)
async def get_package_endpoint(package_id: str):
    pkg = await get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg["_id"] = str(pkg["_id"])
    return Package(**pkg)

@router.post("/", response_model=Package)
async def create_package_endpoint(package_in: PackageIn):
    origin_city = package_in.origin.city
    destination_city = package_in.destination.city

    # Validate cities
    if origin_city not in all_cities or destination_city not in all_cities:
        raise HTTPException(status_code=400, detail="Unserviceable location")

    origin_region = get_region_from_city(origin_city)
    destination_region = get_region_from_city(destination_city)
    now = datetime.utcnow()

    # Check if package ID already exists in the index DB
    from db.connections import db_index
    existing = await db_index.packages.find_one({"package_id": package_in.package_id})
    if existing:
        raise HTTPException(status_code=400, detail=f"Package ID '{package_in.package_id}' already exists")

    # Create the full package object
    full_package = Package(
        package_id=package_in.package_id,
        origin=Location(city=origin_city, region=origin_region),
        destination=Location(city=destination_city, region=destination_region),
        metric=package_in.metric,
        status="shipping",
        location=Location(city=origin_city, region=origin_region),
        history=[StatusUpdates(status="shipping", timestamp=now, location=Location(city=origin_city, region=origin_region))],
        last_updated=now
    )

    # Insert into distributed DB
    await insert_package(full_package.dict(by_alias=True, exclude={"id"}), origin_region)

    # Optionally insert into index DB to keep track of IDs
    await db_index.packages.insert_one({
        "package_id": full_package.package_id,
        "current_region": origin_region,
        "last_updated": now
    })

    # Send RabbitMQ message
    if rabbitmq_exchange:
        try:
            message_body = json.dumps({
                "package_id": full_package.package_id,
                "source": full_package.origin.city,
                "destination": full_package.destination.city,
                "metric": full_package.metric,
            }).encode()
            await rabbitmq_exchange.publish(
                aio_pika.Message(body=message_body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key=queue_name
            )
        except Exception as e:
            print(f"Failed to send RabbitMQ message: {e}")

    return full_package


# Endpoint: update package status
@router.put("/{package_id}/status", response_model=Package)
async def update_package_status_endpoint(package_id: str, update: StatusUpdateRequest):
    pkg = await get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    now = datetime.utcnow()
    pkg["status"] = update.status
    pkg["last_updated"] = now
    pkg["location"] = update.location.dict()
    pkg.setdefault("history", []).append({
        "status": update.status,
        "timestamp": now,
        "location": update.location.dict()
    })

    from db.connections import REGION_DBS, db_index
    current_region = (await db_index.packages.find_one({"package_id": package_id}))["current_region"]
    await REGION_DBS[current_region].packages.replace_one({"package_id": package_id}, pkg)

    pkg["_id"] = str(pkg["_id"])
    return Package(**pkg)


# Endpoint: delete package
@router.delete("/{package_id}")
async def delete_package_endpoint(package_id: str):
    from db.connections import REGION_DBS, db_index
    index_entry = await db_index.packages.find_one({"package_id": package_id})
    if not index_entry:
        raise HTTPException(status_code=404, detail="Package not found")
    region = index_entry["current_region"]

    result = await REGION_DBS[region].packages.delete_one({"package_id": package_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Package not found")

    # Remove from index DB
    await db_index.packages.delete_one({"package_id": package_id})
    return {"message": f"Package with ID {package_id} has been deleted."}
