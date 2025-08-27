from motor.motor_asyncio import AsyncIOMotorClient

# Regional Async MongoDB connections
db_asia = AsyncIOMotorClient("mongodb://localhost:27018")["asia"]
db_europe = AsyncIOMotorClient("mongodb://localhost:27019")["europe"]
db_na = AsyncIOMotorClient("mongodb://localhost:27020")["na"]
db_sa = AsyncIOMotorClient("mongodb://localhost:27021")["sa"]
db_africa = AsyncIOMotorClient("mongodb://localhost:27022")["africa"]
db_oceania = AsyncIOMotorClient("mongodb://localhost:27023")["oceania"]

# Global Index DB
db_index = AsyncIOMotorClient("mongodb://localhost:27024")["index"]

# Map region name to DB
REGION_DBS = {
    "Asia": db_asia,
    "Europe": db_europe,
    "NA": db_na,
    "SA": db_sa,
    "Africa": db_africa,
    "Oceania": db_oceania,
}
