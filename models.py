from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Location(BaseModel):
    city:str
    region:str

class StatusUpdates(BaseModel):
    status: str
    timestamp: datetime
    location:Location

class StatusUpdateRequest(BaseModel):
    status: str
    location: Location

class Package(BaseModel):
    package_id: str
    origin: Location
    destination: Location
    metric : str 
    status: str
    location:Location
    history: List[StatusUpdates] = []
    last_updated: datetime
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        allow_population_by_field_name = True
