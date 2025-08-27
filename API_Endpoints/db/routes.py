from .connections import REGION_DBS, db_index
from datetime import datetime

async def insert_package(package: dict, region: str):
    await REGION_DBS[region].packages.insert_one(package)
    await db_index.packages.update_one(
        {"package_id": package["package_id"]},
        {"$set": {"current_region": region}},
        upsert=True
    )

async def get_package(package_id: str):
    entry = await db_index.packages.find_one({"package_id": package_id})
    if not entry:
        return None
    region = entry["current_region"]
    return await REGION_DBS[region].packages.find_one({"package_id": package_id})

async def move_package(package_id: str, to_region: str, new_city: str):
    pkg = await get_package(package_id)
    if not pkg:
        return None

    old_region = (await db_index.packages.find_one({"package_id": package_id}))["current_region"]
    await REGION_DBS[old_region].packages.delete_one({"package_id": package_id})

    pkg["current_location"] = new_city
    pkg.setdefault("history", []).append({"city": new_city, "timestamp": datetime.utcnow().isoformat()})

    await REGION_DBS[to_region].packages.insert_one(pkg)
    await db_index.packages.update_one(
        {"package_id": package_id},
        {"$set": {"current_region": to_region}}
    )
    return pkg
