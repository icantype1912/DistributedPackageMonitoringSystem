from motor.motor_asyncio import AsyncIOMotorClient

MongoURI = "mongodb://127.0.0.1:27017/?directConnection=true&serverSelectionTimeoutMS=2000&appName=mongosh+2.5.3"
client = AsyncIOMotorClient(MongoURI)
db = client["package_tracker"]
