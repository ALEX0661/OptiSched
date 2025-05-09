from pydantic import BaseModel
from typing import Optional

class Faculty(BaseModel):
    id: Optional[int] = None
    name: str
    specialization: str = ""
    AcademicRank: Optional[str] = None
    Department: Optional[str] = None
    Educational_attainment: Optional[str] = None
    Sex: Optional[str] = None
    Status: Optional[str] = None
    units: float = 0.0

class AssignmentRequest(BaseModel):
    schedule_id: int
    faculty_id: int

class GroupUnassignmentRequest(BaseModel):
    courseCode: str
    program: str
    block: str