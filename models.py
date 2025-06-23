from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class StatusUpdates(BaseModel):
    status:str
    timestamp:datetime

class Package(BaseModel):
    package_id:str
    origin:str
    destination:str
    status:str
    history:list[StatusUpdates]
    last_updated:datetime

        