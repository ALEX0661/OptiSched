from pydantic import BaseModel
from typing import Optional

class OverrideRequest(BaseModel):
    schedule_id: str
    new_start: str  
    new_room: str
    new_day: Optional[str] = None
