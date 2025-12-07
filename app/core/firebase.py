import firebase_admin
from firebase_admin import credentials, firestore, auth
from app.core.globals import schedule_dict, in_memory_faculty_loads
import os
import logging
import json

# Setup Logger
logger = logging.getLogger("app.core.firebase")

if os.environ.get("FIREBASE_SERVICE_ACCOUNT"):
    # Production: Load from Railway Variable
    service_account_info = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])
    cred = credentials.Certificate(service_account_info)
else:
    # Local Development: Fallback to a local file (optional)
    # If you use 'gcloud auth application-default login' locally, you can keep
    # credentials.ApplicationDefault() here, or point to a downloaded JSON file.
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
    except Exception:
        print("Warning: serviceAccountKey.json not found. Attempting Application Default Credentials.")
        cred = credentials.ApplicationDefault()

try:
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except ValueError:
    # App already initialized
    db = firestore.client()

# Caches
_courses_cache = None 
_rooms_cache = None
_time_settings_cache = None
_days_cache = None
_faculty_cache = None

def get_start_end(period_str: str):
    def parse_time(t: str) -> int:
        try:
            time_part, meridiem = t.split(" ")
            hour, minute = map(int, time_part.split("." if ":" not in time_part else ":"))
            if meridiem.upper() == "PM" and hour != 12:
                hour += 12
            if meridiem.upper() == "AM" and hour == 12:
                hour = 0
            return hour * 60 + minute
        except ValueError:
            logger.error(f"Time parsing error for string: {t}")
            return 0

    try:
        start_str, end_str = period_str.split(" - ")
        return parse_time(start_str), parse_time(end_str)
    except ValueError:
        logger.error(f"Period parsing error for string: {period_str}")
        return 0, 0

def recalc_units_in_memory():
    global in_memory_faculty_loads
    in_memory_faculty_loads = {}
    batch = db.batch()
    
    try:
        faculty_ref = db.collection("faculty")
        faculty_docs = {doc.id: doc for doc in faculty_ref.stream()}

        for event in schedule_dict.values():
            if not event.get("faculty") or not event.get("period"):
                continue
            try:
                start, end = get_start_end(event["period"])
                duration = (end - start) / 60.0
                in_memory_faculty_loads[event["faculty"]] = in_memory_faculty_loads.get(event["faculty"], 0) + duration
            except Exception as e:
                logger.warning(f"Unit calculation error for event {event.get('id', 'unknown')}: {e}")

        update_count = 0
        for doc_id, doc in faculty_docs.items():
            faculty_name = doc.to_dict().get("name")
            new_units = in_memory_faculty_loads.get(faculty_name, 0)
            if doc.to_dict().get("units", 0) != new_units:
                batch.update(faculty_ref.document(doc_id), {"units": new_units})
                update_count += 1

        if update_count > 0:
            batch.commit()
            logger.info(f"Successfully updated units for {update_count} faculty members.")
            
    except Exception as e:
        logger.error(f"Error recalculating faculty units: {e}")

def get_faculty():
    global _faculty_cache
    if _faculty_cache is None:
        try:
            faculty_ref = db.collection("faculty")
            docs = faculty_ref.stream()
            _faculty_cache = [doc.to_dict() for doc in docs]
            logger.debug("Faculty cache refreshed.")
        except Exception as e:
            logger.error(f"Error fetching faculty from Firestore: {e}")
            return []
    return _faculty_cache

def load_courses():
    global _courses_cache
    if _courses_cache is None:
        try:
            courses_ref = db.collection("courses")
            docs = courses_ref.stream()
            _courses_cache = [doc.to_dict() for doc in docs]
            logger.debug("Courses cache refreshed.")
        except Exception as e:
            logger.error(f"Error fetching courses from Firestore: {e}")
            return []
    return _courses_cache

def load_rooms():
    global _rooms_cache
    if _rooms_cache is None:
        try:
            rooms_ref = db.collection("rooms").document("rooms")
            doc = rooms_ref.get()
            _rooms_cache = doc.to_dict() if doc.exists else {"lecture": [], "lab": []}
            logger.debug("Rooms cache refreshed.")
        except Exception as e:
            logger.error(f"Error fetching rooms from Firestore: {e}")
            return {"lecture": [], "lab": []}
    return _rooms_cache

def load_time_settings():
    global _time_settings_cache
    if _time_settings_cache is None:
        try:
            time_ref = db.collection("settings").document("time")
            doc = time_ref.get()
            _time_settings_cache = doc.to_dict() if doc.exists else {"start_time": 7, "end_time": 21}
            logger.debug("Time settings cache refreshed.")
        except Exception as e:
            logger.error(f"Error fetching time settings: {e}")
            return {"start_time": 7, "end_time": 21}
    return _time_settings_cache

def load_days():
    global _days_cache
    if _days_cache is None:
        try:
            days_ref = db.collection("settings").document("days")
            doc = days_ref.get()
            _days_cache = doc.to_dict().get("days", []) if doc.exists else []
            logger.debug("Days cache refreshed.")
        except Exception as e:
            logger.error(f"Error fetching days settings: {e}")
            return []
    return _days_cache

def refresh_faculty_cache():
    global _faculty_cache
    _faculty_cache = None

def refresh_courses_cache():
    global _courses_cache
    _courses_cache = None

def refresh_rooms_cache():
    global _rooms_cache
    _rooms_cache = None

def refresh_time_settings_cache():
    global _time_settings_cache
    _time_settings_cache = None

def refresh_days_cache():
    global _days_cache

    _days_cache = None

