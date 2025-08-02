import os
from motor.motor_asyncio import AsyncIOMotorClient

MongoURI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
client = AsyncIOMotorClient(MongoURI)
db = client[os.environ.get("DB_NAME", "package_tracker")]
