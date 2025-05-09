from fastapi import APIRouter, HTTPException, Response, Depends, BackgroundTasks
import uuid
from app.core.auth import verify_token_allowed
from app.core.scheduler import generate_schedule
from app.core.firebase import db, load_rooms
from app.core.globals import schedule_dict, progress_state
import logging

logger = logging.getLogger("schedule")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])


@router.get("/generate")
async def get_schedule(background_tasks: BackgroundTasks,
                       force: bool = False,
                       progress: bool = True):
    if schedule_dict and not force:
        event_count = len(schedule_dict)
        logger.info(f"Returning cached schedule ({event_count} events)")
        return {
            "status": "success",
            "schedule": list(schedule_dict.values()),
            "rooms": load_rooms(),
            "event_count": event_count  # Add this to show the actual count in response
        }

    process_id = str(uuid.uuid4())
    progress_state[process_id] = 0

    background_tasks.add_task(generate_schedule, process_id)
    logger.info(f"Started schedule generation process_id={process_id}")
    return {"status": "started", "process_id": process_id}

@router.get("/status/{process_id}")
async def get_generation_status(process_id: str):
    """Check the status of a schedule generation process"""
    if process_id not in progress_state:
        raise HTTPException(status_code=404, detail="Process ID not found")
    
    progress = progress_state[process_id]
    
    if progress == 100:
        return {
            "status": "complete",
            "progress": 100,
            "event_count": len(schedule_dict)
        }
    elif progress == -1:
        return {
            "status": "failed",
            "progress": -1
        }
    else:
        return {
            "status": "in_progress",
            "progress": progress
        }

@router.get("/result")
async def get_generated_schedule():
    """Get the full generated schedule after completion"""
    if not schedule_dict:
        raise HTTPException(status_code=404, detail="No schedule has been generated yet")
    
    all_events = list(schedule_dict.values())
    return {
        "status": "success",
        "schedule": all_events,
        "event_count": len(all_events),
        "rooms": load_rooms()
    }

@router.post("/save")
async def save_schedule(final_schedule: dict):
    try:
        name = final_schedule.get("schedule_name")
        logger.info("Saving schedule '%s'", name)
        db.collection("final_schedules").document(name).set(final_schedule)
        return {"status": "success", "message": f"Schedule '{name}' saved."}
    except Exception:
        logger.exception("Error saving schedule")
        raise HTTPException(500, "Internal Server Error in save_schedule")



@router.get("/final/{schedule_name}")
async def get_final_schedule(schedule_name: str):
    try:
        logger.info("GET /schedule/final/%s called", schedule_name)
        doc_ref = db.collection("final_schedules").document(schedule_name)
        doc = doc_ref.get()
        if not doc.exists:
            logger.error("Schedule '%s' not found", schedule_name)
            raise HTTPException(status_code=404, detail="Schedule not found")
        result = doc.to_dict()
        logger.info("Schedule retrieved: %s", result)
        return result
    except HTTPException as he:
        logger.error("HTTP error in get_final_schedule: %s", he.detail)
        raise he
    except Exception as e:
        logger.exception("Unexpected error in get_final_schedule")
        raise HTTPException(status_code=500, detail="Internal Server Error in get_final_schedule")


@router.get("/final")
async def list_final_schedules():
    try:
        logger.info("GET /schedule/final called to list schedules")
        schedules_ref = db.collection("final_schedules")
        docs = schedules_ref.stream()
        schedule_names = [doc.id for doc in docs]
        logger.info("Found %d Schedules", len(schedule_names))
        return {"status": "success", "schedules": schedule_names}
    except Exception as e:
        logger.exception("Unexpected error in list_final_schedules")
        raise HTTPException(status_code=500, detail="Internal Server Error in list_final_schedules")



