import firebase_admin
from firebase_admin import credentials, firestore
from app.core.globals import schedule_dict, in_memory_faculty_loads

cred = credentials.Certificate("optisched-6b881-firebase-adminsdk-fbsvc-61c4234df0.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

_courses_cache = None
_rooms_cache = None
_time_settings_cache = None
_days_cache = None
_faculty_cache = None
_admins_cache: set[str] = set()


def get_start_end(period_str: str):
    def parse_time(t: str) -> int:
        time_part, meridiem = t.split(" ")
        hour, minute = map(int, time_part.split("." if ":" not in time_part else ":"))
        if meridiem.upper() == "PM" and hour != 12:
            hour += 12
        if meridiem.upper() == "AM" and hour == 12:
            hour = 0
        return hour * 60 + minute

    start_str, end_str = period_str.split(" - ")
    return parse_time(start_str), parse_time(end_str)


def recalc_units_in_memory():
    global in_memory_faculty_loads
    in_memory_faculty_loads = {}
    batch = db.batch()
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
            print(f"Calculation error: {str(e)}")

    update_count = 0
    for doc_id, doc in faculty_docs.items():
        faculty_name = doc.to_dict().get("name")
        new_units = in_memory_faculty_loads.get(faculty_name, 0)
        if doc.to_dict().get("units", 0) != new_units:
            batch.update(faculty_ref.document(doc_id), {"units": new_units})
            update_count += 1

    if update_count > 0:
        batch.commit()
        print(f"Batched {update_count} faculty updates")


def get_faculty():
    global _faculty_cache
    if _faculty_cache is None:
        faculty_ref = db.collection("faculty")
        docs = faculty_ref.stream()
        _faculty_cache = [doc.to_dict() for doc in docs]
    return _faculty_cache


def load_courses():
    global _courses_cache
    if _courses_cache is None:
        courses_ref = db.collection("courses")
        docs = courses_ref.stream()
        _courses_cache = [doc.to_dict() for doc in docs]
    return _courses_cache


def load_rooms():
    global _rooms_cache
    if _rooms_cache is None:
        rooms_ref = db.collection("rooms").document("rooms")
        doc = rooms_ref.get()
        _rooms_cache = doc.to_dict() if doc.exists else {"lecture": [], "lab": []}
    return _rooms_cache


def load_time_settings():
    global _time_settings_cache
    if _time_settings_cache is None:
        time_ref = db.collection("settings").document("time")
        doc = time_ref.get()
        _time_settings_cache = doc.to_dict() if doc.exists else {"start_time": 7, "end_time": 21}
    return _time_settings_cache


def load_days():
    global _days_cache
    if _days_cache is None:
        days_ref = db.collection("settings").document("days")
        doc = days_ref.get()
        _days_cache = doc.to_dict().get("days", []) if doc.exists else []
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


def load_admins_cache():
    global _admins_cache
    docs = db.collection("admins").stream()
    _admins_cache = {d.to_dict().get("email") for d in docs}


def verify_admin_email(email: str) -> bool:
    return email in _admins_cache
