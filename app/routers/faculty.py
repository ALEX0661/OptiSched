from fastapi import APIRouter, HTTPException, Depends
import random
from app.core.auth import verify_token_allowed
from app.core.firebase import db, refresh_faculty_cache, get_faculty
from app.models.faculty import Faculty, AssignmentRequest, GroupUnassignmentRequest
from app.core.globals import schedule_dict
import logging

logger = logging.getLogger("faculty")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])

@router.get("/")
async def fetch_all_faculty():
    try:
        faculty_list = get_faculty()
        return {"status": "success", "faculty": faculty_list}
    except Exception as e:
        logger.exception("Unexpected error in fetch_all_faculty")
        raise HTTPException(status_code=500, detail="Internal Server Error in fetch_all_faculty")

@router.post("/add")
async def add_faculty(faculty: Faculty):
    try:
        refresh_faculty_cache()
        if faculty.id is None:
            faculty.id = random.randint(1, 1000000)
        db.collection("faculty").document(str(faculty.id)).set(faculty.dict())
        return {"status": "success", "message": "Faculty added successfully.", "faculty": faculty.dict()}
    except Exception as e:
        logger.exception("Unexpected error in add_faculty")
        raise HTTPException(status_code=500, detail="Internal Server Error in add_faculty")

@router.put("/update/{faculty_id}")
async def update_faculty(faculty_id: int, faculty: Faculty):
    try:
        faculty_ref = db.collection("faculty").document(str(faculty_id))
        doc = faculty_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Faculty not found")
    
        existing_data = doc.to_dict()
        updated_data = {**existing_data, **faculty.dict(exclude_unset=True)}
        updated_data["id"] = existing_data.get("id", faculty_id)
        faculty_ref.update(updated_data)
        refresh_faculty_cache()
        return {"status": "success", "message": f"Faculty {faculty_id} updated successfully.", "faculty": updated_data}
    except HTTPException as he:
        logger.error(f"HTTP error in update_faculty: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in update_faculty")
        raise HTTPException(status_code=500, detail="Internal Server Error in update_faculty")

@router.delete("/delete/{faculty_id}")
async def delete_faculty(faculty_id: int):
    try:
        refresh_faculty_cache()
        faculty_ref = db.collection("faculty").document(str(faculty_id))
        doc = faculty_ref.get()
    
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Faculty not found")
    
        faculty_data = doc.to_dict()
        archived_faculty_ref = db.collection("archived_faculty").document(str(faculty_id))
    
        batch = db.batch()
        batch.set(archived_faculty_ref, faculty_data)
        batch.delete(faculty_ref)
        batch.commit()
    
        for event in schedule_dict.values():
            if event.get("faculty") == faculty_data.get("name", ""):
                event["faculty"] = ""
    
        return {"status": "success", "message": f"Faculty {faculty_id} archived and deleted from active faculty."}
    except HTTPException as he:
        logger.error(f"HTTP error in delete_faculty: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in delete_faculty")
        raise HTTPException(status_code=500, detail="Internal Server Error in delete_faculty")

@router.post("/assign")
async def assign_faculty(request: AssignmentRequest):
    event = schedule_dict.get(request.schedule_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    faculty = next((f for f in get_faculty() if f["id"] == request.faculty_id), None)
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    group_key = (event["courseCode"], event["program"], event["block"])
    group_events = [e for e in schedule_dict.values() if 
                    (e["courseCode"], e["program"], e["block"]) == group_key]
    assigned_events = [e for e in schedule_dict.values() if e.get("faculty") == faculty["name"]]

    for ge in group_events:
        for ae in assigned_events:
            if ae["day"] != ge["day"]:
                continue
            if ge["start"] < ae["end"] and ae["start"] < ge["end"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Conflict on {ge['day']} for event {ae['schedule_id']}"
                )

    for ge in group_events:
        ge["faculty"] = faculty["name"]

    return {
        "status": "success",
        "message": f"Assigned {faculty['name']} to group",
        "events": group_events
    }

@router.post("/unassign")
async def unassign_faculty_group(request: GroupUnassignmentRequest):
    try:
        group_events = [
            e for e in schedule_dict.values()
            if e.get("courseCode") == request.courseCode and 
               e.get("program") == request.program and 
               e.get("block") == request.block
        ]
        if not group_events:
            raise HTTPException(status_code=404, detail="No matching events found for the provided group parameters")
        for e in group_events:
            e["faculty"] = ""
        return {"status": "success", "message": "Faculty unassigned from group", "events": group_events}
    except HTTPException as he:
        logger.error(f"HTTP error in unassign_faculty_group: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in unassign_faculty_group")
        raise HTTPException(status_code=500, detail="Internal Server Error in unassign_faculty_group")
