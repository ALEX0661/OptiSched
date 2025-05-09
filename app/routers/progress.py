from fastapi import APIRouter
from app.core.globals import progress_state
import asyncio
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.get("/progress/{process_id}")
async def progress_stream(process_id: str):
    async def event_generator():
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                while True:
                    progress_value = progress_state.get(process_id, 0)
                    if progress_value == -1:  # Error state
                        yield f"data: error\n\n"
                        break
                    yield f"data: {progress_value}\n\n"
                    if progress_value >= 100:
                        break
                    await asyncio.sleep(1)
                break  # Successful completion
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    yield f"data: connection_error\n\n"
                    break
                await asyncio.sleep(1)  # Wait before retry
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
