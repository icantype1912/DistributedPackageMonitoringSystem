from fastapi import APIRouter, HTTPException
from models import Package, StatusUpdateRequest, PackageIn, Location, StatusUpdates
from db import db
from datetime import datetime
import asyncio
import json
import aio_pika
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

all_cities = [
    "New York", "Los Angeles", "Toronto", "Chicago", "Houston", "Vancouver", "San Francisco", "Mexico City", "Miami", "Atlanta", "Montreal", "Seattle", "Boston", "Phoenix", "Dallas",
    "Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago", "Caracas", "Quito", "La Paz", "Montevideo", "Asuncion", "Cali", "Medellin", "Rio de Janeiro", "Brasilia", "Salvador",
    "London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Zurich", "Oslo", "Warsaw", "Lisbon", "Dublin", "Prague", "Budapest", "Copenhagen",
    "Lagos", "Cairo", "Nairobi", "Accra", "Johannesburg", "Algiers", "Casablanca", "Addis Ababa", "Dakar", "Tunis", "Kampala", "Luanda", "Abidjan", "Harare", "Gaborone",
    "Tokyo", "Beijing", "Shanghai", "Delhi", "Mumbai", "Seoul", "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Hanoi", "Manila", "Taipei", "Dhaka", "Riyadh",
    "Sydney", "Melbourne", "Auckland", "Brisbane", "Perth", "Wellington", "Adelaide", "Canberra", "Hobart", "Gold Coast", "Darwin", "Hamilton", "Christchurch", "Suva", "Noumea"
]

continents = {
    "North America": ["New York", "Los Angeles", "Toronto", "Chicago", "Houston", "Vancouver", "San Francisco", "Mexico City", "Miami", "Atlanta", "Montreal", "Seattle", "Boston", "Phoenix", "Dallas"],
    "South America": ["Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago", "Caracas", "Quito", "La Paz", "Montevideo", "Asuncion", "Cali", "Medellin", "Rio de Janeiro", "Brasilia", "Salvador"],
    "Europe": ["London", "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Vienna", "Zurich", "Oslo", "Warsaw", "Lisbon", "Dublin", "Prague", "Budapest", "Copenhagen"],
    "Africa": ["Lagos", "Cairo", "Nairobi", "Accra", "Johannesburg", "Algiers", "Casablanca", "Addis Ababa", "Dakar", "Tunis", "Kampala", "Luanda", "Abidjan", "Harare", "Gaborone"],
    "Asia": ["Tokyo", "Beijing", "Shanghai", "Delhi", "Mumbai", "Seoul", "Bangkok", "Singapore", "Kuala Lumpur", "Jakarta", "Hanoi", "Manila", "Taipei", "Dhaka", "Riyadh"],
    "Oceania": ["Sydney", "Melbourne", "Auckland", "Brisbane", "Perth", "Wellington", "Adelaide", "Canberra", "Hobart", "Gold Coast", "Darwin", "Hamilton", "Christchurch", "Suva", "Noumea"]
}

rabbitmq_exchange = None
rabbitmq_channel = None
queue_name = "package_created"

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
rabbitmq_connection = None
rabbitmq_channel = None
rabbitmq_exchange = None
queue_name = "package_created"


async def start_rabbitmq_producer():
    global rabbitmq_channel, rabbitmq_exchange

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    rabbitmq_channel = await connection.channel()

    rabbitmq_exchange = await rabbitmq_channel.declare_exchange(
        "package_exchange", aio_pika.ExchangeType.DIRECT, durable=True
    )
    
    queue = await rabbitmq_channel.declare_queue(queue_name, durable=True)
    await queue.bind(rabbitmq_exchange, routing_key=queue_name)


async def stop_rabbitmq_producer():
    global rabbitmq_connection
    if rabbitmq_connection:
        await rabbitmq_connection.close()


@router.get("/", response_model=list[Package])
async def list_packages():
    packages_cursor = db["packages"].find()
    packages = await packages_cursor.to_list(length=None)

    for p in packages:
        p["_id"] = str(p["_id"])

    return [Package(**p) for p in packages]


@router.get("/{package_id}", response_model=Package)
async def get_package(package_id: str):
    package = await db["packages"].find_one({"package_id": package_id})
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    package["_id"] = str(package["_id"])
    return Package(**package)


def get_region_from_city(city_name: str) -> str:
    """Helper function to find the region for a given city."""
    for region, cities in continents.items():
        if city_name in cities:
            return region
    return ""


@router.post("/", response_model=Package)
async def create_package(package_in: PackageIn):
    # Check if the package ID already exists
    existing = await db["packages"].find_one({"package_id": package_in.package_id})
    if existing:
        raise HTTPException(status_code=400, detail=f"Package ID '{package_in.package_id}' already exists")

    # Validate that the cities are serviceable
    origin_city = package_in.origin.city
    destination_city = package_in.destination.city

    if origin_city not in all_cities or destination_city not in all_cities:
        raise HTTPException(status_code=400, detail=f"Unservicable location")

    # Automatically determine regions and fill in default values
    origin_region = get_region_from_city(origin_city)
    destination_region = get_region_from_city(destination_city)
    now = datetime.utcnow()

    # Create the complete Package object
    full_package = Package(
        package_id=package_in.package_id,
        origin=Location(city=origin_city, region=origin_region),
        destination=Location(city=destination_city, region=destination_region),
        metric=package_in.metric,
        status="shipping",  # Default status
        location=Location(city=origin_city, region=origin_region),  # Initial location is origin
        history=[
            StatusUpdates(status="shipping", timestamp=now, location=Location(city=origin_city, region=origin_region))
        ],
        last_updated=now,
    )
    
    # Convert the Pydantic model to a dictionary for database insertion
    package_dict = full_package.dict(by_alias=True, exclude={"id"})
    await db["packages"].insert_one(package_dict)

    # Prepare and send the message to RabbitMQ
    package_data = {
        "package_id": full_package.package_id,
        "source": full_package.origin.city,
        "destination": full_package.destination.city,
        "metric": full_package.metric,
    }

    try:
        message_body = json.dumps(package_data).encode()
        await rabbitmq_exchange.publish(
            aio_pika.Message(
                body=message_body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=queue_name
        )
    except Exception as e:
        print(f"Failed to send RabbitMQ message: {e}")

    # Fetch the newly created document from the database to return
    inserted = await db["packages"].find_one({"package_id": package_in.package_id})
    if inserted:
        inserted["_id"] = str(inserted["_id"])
        return Package(**inserted)
    else:
        # This case should ideally not be reached if insertion was successful
        raise HTTPException(status_code=500, detail="Failed to retrieve newly created package")


@router.put("/{package_id}/status", response_model=Package)
async def update_package_status(package_id: str, update: StatusUpdateRequest):
    now = datetime.utcnow()

    result = await db["packages"].update_one(
        {"package_id": package_id},
        {
            "$set": {
                "status": update.status,
                "last_updated": now,
                "location": update.location.dict()
            },
            "$push": {
                "history": {
                    "status": update.status,
                    "timestamp": now,
                    "location": update.location.dict()
                }
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Package not found")

    updated_package = await db["packages"].find_one({"package_id": package_id})
    updated_package["_id"] = str(updated_package["_id"])
    return Package(**updated_package)


@router.delete("/{package_id}")
async def delete_package(package_id: str):
    result = await db["packages"].delete_one({"package_id": package_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Package not found")

    return {"message": f"Package with ID {package_id} has been deleted."}