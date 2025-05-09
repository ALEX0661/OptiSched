import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, courses, faculty, schedule, excel, overrides, settings, progress
from app.core.firebase import (
    refresh_faculty_cache,
    refresh_courses_cache,
    refresh_rooms_cache,
    refresh_time_settings_cache,
    refresh_days_cache,
    load_admins_cache,
    get_start_end,
)
from app.core.globals import schedule_dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="OptiSchedule API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(progress.router)
app.include_router(settings.router, prefix="/settings", tags=["Settings"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(courses.router, prefix="/courses", tags=["Courses"])
app.include_router(faculty.router, prefix="/faculty", tags=["Faculty"])
app.include_router(schedule.router, prefix="/schedule", tags=["Schedule"])
app.include_router(excel.router, prefix="/upload", tags=["Excel Upload"])
app.include_router(overrides.router, prefix="/override", tags=["Overrides"])

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to OptiSchedule API",
        "docs_url": "/docs",
        "version": "1.0.0"
    }

@app.on_event("startup")
async def startup_event():
    refresh_faculty_cache()
    refresh_courses_cache()
    refresh_rooms_cache()
    refresh_time_settings_cache()
    refresh_days_cache()
    load_admins_cache()

    for ev in schedule_dict.values():
        if ev.get("period"):
            start, end = get_start_end(ev["period"])
            ev["start"] = start
            ev["end"] = end


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8000, host="0.0.0.0")
