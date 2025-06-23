from fastapi import APIRouter
router = APIRouter(prefix="/packages")
from db import db

@router.get("/")
async def list_packages():
    packages = db["packages"].find()
    return {"packages": packages}

@router.post("/")
async def create_package(package: dict):
    new_package = db["packages"].insert_one(package)
    return {"message": "Package created successfully", "package": new_package}

@router.get("/{package_id}")
async def get_package(id: int):
    package = db["packages"].find_one({"package_id":id})
    if not package:
        return {"error": "Package not found"}
    return {"package": package}

@router.delete("/{package_id}")
async def delete_package(id: int):
    success = db["packages"].delete_one({"package_id":id})
    if not success:
        return {"error": "Failed to delete package"}
    return {"message": "Package deleted successfully"}