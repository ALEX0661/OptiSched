from pydantic import BaseModel
from typing import Optional
from typing import List

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
    schedule_id: str
    faculty_id: int
    merged_blocks: Optional[List[str]] = None

class GroupUnassignmentRequest(BaseModel):
    courseCode: str
    program: str
    block: str
    merged_blocks: Optional[List[str]] = None