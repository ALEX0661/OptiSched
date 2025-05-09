from pydantic import BaseModel, Field
from typing import Optional

class Course(BaseModel):
    courseCode: Optional[str] = Field(None, description="Course code is taken from URL if not provided")
    title: str
    program: str
    unitsLecture: int
    unitsLab: int
    yearLevel: int
    blocks: int

    class Config:
        allow_population_by_field_name = True
        schema_extra = {
            "example": {
                "courseCode": "IT101",
                "title": "Introduction to Computing",
                "program": "BSIT",
                "unitsLecture": 2,
                "unitsLab": 1,
                "yearLevel": 1,
                "blocks": 4
            }
        }

class CoursesPayload(BaseModel): 
    courses: list[Course]

class FinalSchedule(BaseModel):
    schedule_name: str
    schedule: list[dict]
