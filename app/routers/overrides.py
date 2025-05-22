from fastapi import APIRouter, HTTPException, Depends
from app.core.auth import verify_token_allowed
from app.core.firebase import get_start_end
from app.utils.helper import format_period
from app.core.globals import schedule_dict
from app.models.schedule import OverrideRequest
import logging

logger = logging.getLogger("override")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])

@router.post("/event")
async def override_event(request: OverrideRequest):
    try:
        event = schedule_dict.get(request.schedule_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
    
        fixed_duration = 90 if event["session"] == "Laboratory" else 60
        try:
            parts = request.new_start.split(":")
            if len(parts) != 2:
                raise ValueError("Invalid time format: must be HH:MM")
            new_start_minutes = int(parts[0]) * 60 + int(parts[1])
            if new_start_minutes < 0 or new_start_minutes >= 24 * 60:
                raise ValueError("Start time out of valid range (00:00-23:59)")
        except ValueError as ve:
            logger.error(f"Invalid time format in override_event: {str(ve)}")
            raise HTTPException(status_code=400, detail=f"Invalid time format: {str(ve)}")
    
        new_end_minutes = new_start_minutes + fixed_duration
        new_day = request.new_day if request.new_day and request.new_day.lower() != "auto" else event.get("day")
    
        # Validate new_day
        valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if new_day and new_day not in valid_days:
            logger.error(f"Invalid day in override_event: {new_day}")
            raise HTTPException(status_code=400, detail=f"Invalid day: {new_day}")
    
        # Detect overlaps but allow saving
        overlap_details = {"hasOverlap": False, "reasons": [], "conflictingEvents": []}
        
        # Check for program/block/year time overlap
        for e in schedule_dict.values():
            if e["schedule_id"] == request.schedule_id:
                continue
            if (
                e.get("program") == event.get("program") and 
                e.get("block") == event.get("block") and 
                e.get("year") == event.get("year") and 
                e.get("day") == new_day
            ):
                try:
                    e_start, e_end = get_start_end(e["period"])
                    if not (new_end_minutes <= e_start or new_start_minutes >= e_end):
                        overlap_details["hasOverlap"] = True
                        overlap_details["reasons"].append("time_program")
                        overlap_details["conflictingEvents"].append(e["schedule_id"])
                except Exception as e:
                    logger.warn(f"Invalid period in conflicting event {e['schedule_id']}: {e.get('period')}")
        
        # Check for faculty time overlap
        if event.get("faculty"):
            for e in schedule_dict.values():
                if e["schedule_id"] == request.schedule_id:
                    continue
                if e.get("day") == new_day and e.get("faculty") == event.get("faculty"):
                    try:
                        e_start, e_end = get_start_end(e["period"])
                        if not (new_end_minutes <= e_start or new_start_minutes >= e_end):
                            overlap_details["hasOverlap"] = True
                            if "time_faculty" not in overlap_details["reasons"]:
                                overlap_details["reasons"].append("time_faculty")
                            overlap_details["conflictingEvents"].append(e["schedule_id"])
                    except Exception as e:
                        logger.warn(f"Invalid period in conflicting event {e['schedule_id']}: {e.get('period')}")
        
        # Check for room overlap
        for e in schedule_dict.values():
            if e["schedule_id"] == request.schedule_id:
                continue
            if e.get("day") == new_day and e.get("room") == request.new_room:
                try:
                    e_start, e_end = get_start_end(e["period"])
                    if not (new_end_minutes <= e_start or new_start_minutes >= e_end):
                        overlap_details["hasOverlap"] = True
                        if "room" not in overlap_details["reasons"]:
                            overlap_details["reasons"].append("room")
                        overlap_details["conflictingEvents"].append(e["schedule_id"])
                except Exception as e:
                    logger.warn(f"Invalid period in conflicting event {e['schedule_id']}: {e.get('period')}")
        
        # Update the event
        new_period = format_period(request.new_start, fixed_duration)
        if not new_period or not isinstance(new_period, str):
            logger.error(f"Invalid period generated: {new_period}")
            raise HTTPException(status_code=500, detail="Failed to generate valid period")
        
        event["period"] = new_period
        event["room"] = request.new_room
        event["day"] = new_day
        event["overlapDetails"] = overlap_details
        schedule_dict[request.schedule_id] = event
        
        # Update conflicting events with overlap details
        for conflicting_id in overlap_details["conflictingEvents"]:
            if conflicting_id in schedule_dict:
                conflicting_event = schedule_dict[conflicting_id]
                conflicting_event["overlapDetails"] = {
                    "hasOverlap": True,
                    "reasons": overlap_details["reasons"],
                    "conflictingEvents": [request.schedule_id]
                }
                schedule_dict[conflicting_id] = conflicting_event
    
        return {"status": "success", "event": event}
    except HTTPException as he:
        logger.error(f"HTTP error in override_event: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in override_event")
        raise HTTPException(status_code=500, detail="Internal Server Error in override_event")
