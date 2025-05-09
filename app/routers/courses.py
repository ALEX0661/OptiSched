from fastapi import APIRouter, HTTPException, Depends
from app.core.auth import verify_token_allowed
from app.core.firebase import db, refresh_courses_cache, load_courses
from app.models.course import Course
import logging
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger("courses")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])

@router.post("/add")      
async def add_course(course: Course):
    try:
        refresh_courses_cache()
        courses_ref = db.collection("courses")
        if any(courses_ref.where(filter=FieldFilter("courseCode", "==", course.courseCode)).stream()):
            raise HTTPException(status_code=400, detail="Course exists")
        courses_ref.document(course.courseCode).set(course.dict(by_alias=True))
        return {"status": "success", "message": "Course added"}
    except HTTPException as he:
        logger.error(f"HTTP error in add_course: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in add_course")
        raise HTTPException(status_code=500, detail="Internal Server Error in add_course")

@router.put("/update/{course_code}")
async def update_course(course_code: str, course: Course):
    try:
        course_data = course.dict(by_alias=True)
        if not course_data.get("courseCode"):
            course_data["courseCode"] = course_code

        courses_ref = db.collection("courses").document(course_code)
        doc = courses_ref.get()
        if not doc.exists:
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

@router.delete("/delete/{course_code}")
async def delete_course(course_code: str):
    try:
        courses_ref = db.collection("courses").document(course_code)
        doc = courses_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Course not found")

        course_data = doc.to_dict()
        archived_courses_ref = db.collection("archived_courses").document(course_code)

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
