import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
load_dotenv()

MONGO_URI = os.getenv("MONGO_URL") 

client = AsyncIOMotorClient(MONGO_URI)   
db = client[os.environ.get("DB_NAME", "package_tracker")]
