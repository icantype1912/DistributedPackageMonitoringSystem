from fastapi import APIRouter, HTTPException
from models import Package, StatusUpdateRequest
from db import db
from datetime import datetime
import asyncio
import json
import aio_pika
import os

router = APIRouter()



rabbitmq_exchange = None
rabbitmq_channel = None
queue_name = "package_created"

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
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


import json
import aio_pika

@router.post("/", response_model=Package)
async def create_package(package: Package):
    existing = await db["packages"].find_one({"package_id": package.package_id})
    if existing:
        raise HTTPException(status_code=400, detail=f"Package ID '{package.package_id}' already exists")

    package_dict = package.dict(by_alias=True, exclude={"id"})
    await db["packages"].insert_one(package_dict)

    package_data = {
        "package_id": package.package_id,
        "source": package.origin.city,
        "destination": package.destination.city,
        "metric": package.metric,
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

    inserted = await db["packages"].find_one({"package_id": package.package_id})
    inserted["_id"] = str(inserted["_id"])
    return Package(**inserted)


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
