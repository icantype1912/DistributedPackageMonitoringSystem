# models.py

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class Location(BaseModel):
    city: str
    region: str = "" # Default to an empty string, will be populated by the endpoint

class StatusUpdates(BaseModel):
    status: str
    timestamp: datetime
    location: Location

class StatusUpdateRequest(BaseModel):
    status: str
    location: Location

# This is the new model for the incoming request
class PackageIn(BaseModel):
    package_id: str
    origin: Location
    destination: Location
    metric: Literal["distance", "time", "cost", "risk"] # Enforce specific metric values

# models.py

class Package(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    package_id: str
    origin: Location
    destination: Location
    metric: str
    status: str = "shipping"  # Default status
    location: Location
    history: List[StatusUpdates] = []  # Default empty history list
    last_updated: datetime = datetime.utcnow() # Default timestamp

    class Config:
        allow_population_by_field_name = True

