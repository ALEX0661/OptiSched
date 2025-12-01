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
            new_start_minutes = int(parts[0]) * 60 + int(parts[1])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid time format")
    
        new_end_minutes = new_start_minutes + fixed_duration
        new_day = request.new_day if request.new_day and request.new_day.lower() != "auto" else event.get("day")
    
        # No conflict checking - frontend handles confirmation
        # Just apply the override
        new_period = format_period(request.new_start, fixed_duration)
        event["period"] = new_period
        event["room"] = request.new_room
        event["day"] = new_day
        schedule_dict[request.schedule_id] = event
    
        logger.info(f"Successfully overrode event {request.schedule_id} to {new_day} {new_period} in {request.new_room}")
        return {"status": "success", "event": event}
    except HTTPException as he:
        logger.error(f"HTTP error in override_event: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in override_event")
        raise HTTPException(status_code=500, detail="Internal Server Error in override_event")