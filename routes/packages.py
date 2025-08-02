from fastapi import APIRouter, HTTPException
from models import Package, StatusUpdateRequest
from db import db
from datetime import datetime

router = APIRouter()

# 🔎 List all packages
@router.get("/", response_model=list[Package])
async def list_packages():
    packages_cursor = db["packages"].find()
    packages = await packages_cursor.to_list(length=None)

    for p in packages:
        p["_id"] = str(p["_id"])

    return [Package(**p) for p in packages]

# 🔎 Get one package by package_id
@router.get("/{package_id}", response_model=Package)
async def get_package(package_id: str):
    package = await db["packages"].find_one({"package_id": package_id})
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    package["_id"] = str(package["_id"])
    return Package(**package)

# ➕ Create a new package
@router.post("/", response_model=Package)
async def create_package(package: Package):
    # Ensure no duplicate package_id
    existing = await db["packages"].find_one({"package_id": package.package_id})
    if existing:
        raise HTTPException(status_code=400, detail=f"Package ID '{package.package_id}' already exists")

    package_dict = package.dict(by_alias=True, exclude={"id"})
    await db["packages"].insert_one(package_dict)

    # Fetch and return the inserted package
    inserted = await db["packages"].find_one({"package_id": package.package_id})
    inserted["_id"] = str(inserted["_id"])
    return Package(**inserted)

# ✏️ Update package status + location
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

# ❌ Delete a package
@router.delete("/{package_id}")
async def delete_package(package_id: str):
    result = await db["packages"].delete_one({"package_id": package_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Package not found")

    return {"message": f"Package with ID {package_id} has been deleted."}
