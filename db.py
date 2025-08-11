import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"  # put quotes around the URI string

client = AsyncIOMotorClient(MONGO_URI)   # use the variable name MONGO_URI (case-sensitive)
db = client[os.environ.get("DB_NAME", "package_tracker")]
