from pydantic import BaseModel
from typing import List

class RoomData(BaseModel):
    lecture: List[str]
    lab: List[str]

class DaysSettings(BaseModel):
    days: List[str]

class TimeSettings(BaseModel):
    start_time: int
    end_time: int