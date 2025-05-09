from fastapi import APIRouter, HTTPException, Depends
from app.core.auth import verify_token_allowed
from app.core.firebase import (
    db, load_rooms, load_days, refresh_rooms_cache,
    refresh_days_cache, refresh_time_settings_cache
)
from app.models.settings import RoomData, DaysSettings, TimeSettings
import logging

logger = logging.getLogger("settings")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])

@router.get("/get_rooms")
async def get_rooms(): 
    try:
        rooms = load_rooms()
        return {"status": "success", "rooms": rooms}
    except Exception as e:
        logger.exception("Error fetching rooms")
        raise HTTPException(status_code=500, detail="Failed to fetch rooms")

@router.get("/get_days")
async def get_days():
    try:
        days = load_days()
        return {"status": "success", "days": days}
    except Exception as e:
        logger.exception("Error fetching days")
        raise HTTPException(status_code=500, detail="Failed to fetch days")

@router.get("/get_time_settings")
async def get_time_settings():
    try:
        time_settings_doc = db.collection("settings").document("time").get()
        if not time_settings_doc.exists:
            raise HTTPException(status_code=404, detail="Time settings not found")
        time_settings = time_settings_doc.to_dict()
        return {"status": "success", "time_settings": time_settings}
    except Exception as e:
        logger.exception("Error fetching time settings")
        raise HTTPException(status_code=500, detail="Failed to fetch time settings")

@router.post("/add_rooms")
async def add_rooms(room_data: RoomData):
    try:
        refresh_rooms_cache()
        db.collection("rooms").document("rooms").set(room_data.dict())
        return {"status": "success", "message": "Rooms updated successfully."}
    except Exception as e:
        logger.exception("Error updating rooms")
        raise HTTPException(status_code=500, detail="Failed to update rooms")

@router.post("/update_time_settings")
async def update_time_settings(settings: TimeSettings):
    try:
        refresh_time_settings_cache()
        db.collection("settings").document("time").set(settings.dict())
        return {"status": "success", "message": "Time settings updated successfully."}
    except Exception as e:
        logger.exception("Error updating time settings")
        raise HTTPException(status_code=500, detail="Failed to update time settings")

@router.post("/update_days")
async def update_days(days_settings: DaysSettings):
    try:
        refresh_days_cache()
        db.collection("settings").document("days").set(days_settings.dict())
        return {"status": "success", "message": "Days updated successfully."}
    except Exception as e:
        logger.exception("Error updating days")
        raise HTTPException(status_code=500, detail="Failed to update days")
