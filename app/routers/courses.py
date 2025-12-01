from fastapi import APIRouter, HTTPException, Depends
from app.core.auth import verify_token_allowed
from app.core.firebase import db, refresh_courses_cache, load_courses
from app.models.course import Course
import logging
from google.cloud.firestore_v1 import FieldFilter
from urllib.parse import unquote

logger = logging.getLogger("courses")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])

@router.post("/add")      
async def add_course(course: Course):
    try:
        refresh_courses_cache()
        courses_ref = db.collection("courses")
        
        # Check if a course with the same courseCode AND program already exists
        existing_courses = list(courses_ref.where(
            filter=FieldFilter("courseCode", "==", course.courseCode)
        ).where(
            filter=FieldFilter("program", "==", course.program)
        ).stream())
        
        if existing_courses:
            raise HTTPException(status_code=400, detail="Course with this code already exists for this program")
        
        # Create a unique document ID combining courseCode and program
        doc_id = f"{course.courseCode}_{course.program}"
        courses_ref.document(doc_id).set(course.dict(by_alias=True))
        return {"status": "success", "message": "Course added"}
    except HTTPException as he:
        logger.error(f"HTTP error in add_course: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in add_course")
        raise HTTPException(status_code=500, detail="Internal Server Error in add_course")

@router.put("/update/{course_code}/{program}")
async def update_course(course_code: str, program: str, course: Course):
    try:
        # Decode URL parameters
        course_code = unquote(course_code)
        program = unquote(program)
        
        course_data = course.dict(by_alias=True)
        if not course_data.get("courseCode"):
            course_data["courseCode"] = course_code

        doc_id = f"{course_code}_{program}"
        courses_ref = db.collection("courses").document(doc_id)
        doc = courses_ref.get()
        
        if not doc.exists:
            logger.error(f"Course not found: {doc_id}")
            raise HTTPException(status_code=404, detail="Course not found")

        courses_ref.update(course_data)
        refresh_courses_cache()
        return {"status": "success", "message": f"Course {course_code} updated successfully."}
    except HTTPException as he:
        logger.error(f"HTTP error in update_course: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in update_course")
        raise HTTPException(status_code=500, detail="Internal Server Error in update_course")

@router.delete("/delete/{course_code}/{program}")
async def delete_course(course_code: str, program: str):
    try:
        # Decode URL parameters
        course_code = unquote(course_code)
        program = unquote(program)
        
        doc_id = f"{course_code}_{program}"
        courses_ref = db.collection("courses").document(doc_id)
        doc = courses_ref.get()
        
        if not doc.exists:
            logger.error(f"Course not found: {doc_id}")
            raise HTTPException(status_code=404, detail="Course not found")

        course_data = doc.to_dict()
        archived_courses_ref = db.collection("archived_courses").document(doc_id)

        batch = db.batch()
        batch.set(archived_courses_ref, course_data)
        batch.delete(courses_ref)
        batch.commit()

        refresh_courses_cache()
        return {"status": "success", "message": f"Course {course_code} archived and deleted from active courses."}
    except HTTPException as he:
        logger.error(f"HTTP error in delete_course: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in delete_course")
        raise HTTPException(status_code=500, detail="Internal Server Error in delete_course")

@router.get("/")
async def list_courses():
    try:
        courses = load_courses()
        return {"status": "success", "courses": courses}
    except Exception as e:
        logger.exception("Unexpected error in list_courses")
        raise HTTPException(status_code=500, detail="Internal Server Error in list_courses")