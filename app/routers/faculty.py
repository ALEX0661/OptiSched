from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
import random
import csv
import io
import re
from app.core.auth import verify_token_allowed
from app.core.firebase import db, refresh_faculty_cache, get_faculty
from app.models.faculty import Faculty, AssignmentRequest, GroupUnassignmentRequest
from app.core.globals import schedule_dict
import logging


logger = logging.getLogger("faculty")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])

# Add this new model for specialization updates
class SpecializationUpdate(BaseModel):
    specialization: str

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

# NEW ENDPOINT: Update only specialization
@router.put("/update-specialization/{faculty_id}")
async def update_specialization(faculty_id: int, update: SpecializationUpdate):
    try:
        faculty_ref = db.collection("faculty").document(str(faculty_id))
        doc = faculty_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Faculty not found")
        
        # Update only the specialization field
        faculty_ref.update({"specialization": update.specialization})
        refresh_faculty_cache()
        
        return {
            "status": "success", 
            "message": f"Specialization updated for faculty {faculty_id}",
            "specialization": update.specialization
        }
    except HTTPException as he:
        logger.error(f"HTTP error in update_specialization: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in update_specialization")
        raise HTTPException(status_code=500, detail="Internal Server Error in update_specialization")

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
    """
    Assign faculty to a group of events.
    Handles merged classes by assigning to all schedules of the merged blocks.
    Groups by base course code (strips A/L suffix) to include both Lecture and Lab.
    """
    try:
        schedule_id = str(request.schedule_id)
        event = schedule_dict.get(schedule_id)
        
        if not event:
            for key, evt in schedule_dict.items():
                if str(key) == schedule_id or str(evt.get('schedule_id')) == schedule_id:
                    event = evt
                    logger.info(f"Found event using search: {key}")
                    break
        
        if not event:
            raise HTTPException(status_code=404, detail=f"Event not found with ID: {schedule_id}")

        faculty = next((f for f in get_faculty() if f["id"] == request.faculty_id), None)
        if not faculty:
            raise HTTPException(status_code=404, detail="Faculty not found")

        base_code = event.get("baseCourseCode", event["courseCode"].rstrip("AL"))
        event_program = event.get("program", event.get("Program", ""))
        event_year = event.get("year", event.get("Year", ""))
        
        blocks_to_assign = request.merged_blocks if request.merged_blocks else [event.get("block", event.get("Block", ""))]
        
        logger.info(f"Assigning faculty {faculty['name']} to base course: {base_code}, program: {event_program}, year: {event_year}, blocks: {blocks_to_assign}")
        
        group_events = []
        for key, e in schedule_dict.items():
            e_base_code = e.get("baseCourseCode", e.get("courseCode", "").rstrip("AL"))
            e_program = e.get("program", e.get("Program", ""))
            e_year = e.get("year", e.get("Year", ""))
            e_block = e.get("block", e.get("Block", ""))
            
            if (e_base_code == base_code and 
                e_program == event_program and 
                str(e_year) == str(event_year) and
                e_block in blocks_to_assign):
                group_events.append(e)
        
        assigned_events = [e for e in schedule_dict.values() if e.get("faculty") == faculty["name"]]

        for ge in group_events:
            ge_period = ge.get("period", "")
            if not ge_period:
                continue
            try:
                ge_parts = ge_period.split(" - ")
                if len(ge_parts) != 2:
                    continue
                ge_start_str, ge_end_str = ge_parts[0], ge_parts[1]
                
                def parse_time_to_minutes(time_str):
                    parts = time_str.strip().split()
                    if len(parts) != 2:
                        return None
                    time_parts = parts[0].split(":")
                    if len(time_parts) != 2:
                        return None
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    meridiem = parts[1].upper()
                    if meridiem == "PM" and hours != 12:
                        hours += 12
                    elif meridiem == "AM" and hours == 12:
                        hours = 0
                    return hours * 60 + minutes
                
                ge_start = parse_time_to_minutes(ge_start_str)
                ge_end = parse_time_to_minutes(ge_end_str)
                
                if ge_start is None or ge_end is None:
                    continue
            except Exception:
                continue

            for ae in assigned_events:
                if ae.get("day") != ge.get("day"):
                    continue
                ae_period = ae.get("period", "")
                if not ae_period:
                    continue
                try:
                    ae_parts = ae_period.split(" - ")
                    if len(ae_parts) != 2:
                        continue
                    ae_start_str, ae_end_str = ae_parts[0], ae_parts[1]
                    ae_start = parse_time_to_minutes(ae_start_str)
                    ae_end = parse_time_to_minutes(ae_end_str)
                    
                    if ae_start is None or ae_end is None:
                        continue
                    
                    if ge_start < ae_end and ae_start < ge_end:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Schedule conflict on {ge.get('day')}: {ge['period']} overlaps with event {ae.get('schedule_id')} ({ae['period']})"
                        )
                except Exception:
                    continue

        for ge in group_events:
            ge["faculty"] = faculty["name"]
        
        return {
            "status": "success",
            "message": f"Assigned {faculty['name']} to {len(group_events)} event(s)",
            "events": group_events
        }
    except HTTPException as he:
        logger.error(f"HTTP error in assign_faculty: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in assign_faculty")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post("/unassign")
async def unassign_faculty_group(request: GroupUnassignmentRequest):
    try:
        group_events = []
        request_base_code = request.courseCode.rstrip("AL")
        target_blocks = request.merged_blocks if (request.merged_blocks and len(request.merged_blocks) > 0) else [request.block]
        
        for e in schedule_dict.values():
            event_base_code = e.get("baseCourseCode", e.get("courseCode", "").rstrip("AL"))
            if (event_base_code == request_base_code and 
                e.get("program") == request.program and 
                e.get("block") in target_blocks):
                group_events.append(e)
        
        if not group_events:
            raise HTTPException(status_code=404, detail=f"No matching events found")
        
        for e in group_events:
            e["faculty"] = ""
        
        return {"status": "success", "message": f"Faculty unassigned from {len(group_events)} event(s)", "events": group_events}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("Unexpected error in unassign_faculty_group")
        raise HTTPException(status_code=500, detail="Internal Server Error in unassign_faculty_group")

def clean_name(name):
    """
    Clean and normalize faculty name for matching.
    Removes special characters, extra spaces, and converts to lowercase.
    """
    if not name:
        return ""
    # Remove special characters (commas, periods) for matching logic
    cleaned = re.sub(r'[^\w\s-]', '', name)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip().lower()
    return cleaned

def match_faculty_name(csv_name, db_faculty_map):
    """
    Advanced faculty name matching.
    """
    csv_clean = clean_name(csv_name)
    
    # Strategy 1: Exact match
    if csv_clean in db_faculty_map:
        return db_faculty_map[csv_clean]
    
    # Strategy 2: CSV parts in DB name
    csv_parts = [p for p in csv_clean.split() if p and len(p) > 1]
    for db_name, db_id in db_faculty_map.items():
        if all(part in db_name for part in csv_parts):
            return db_id
    
    # Strategy 3: DB parts in CSV name
    for db_name, db_id in db_faculty_map.items():
        db_parts = [p for p in db_name.split() if p and len(p) > 1]
        if all(part in csv_clean for part in db_parts):
            return db_id
            
    # Strategy 4: Last name matching (first word usually)
    if csv_parts:
        csv_last = csv_parts[0]
        for db_name, db_id in db_faculty_map.items():
            db_parts = db_name.split()
            if db_parts and csv_last == db_parts[0]:
                return db_id
    
    return None

@router.post("/upload-csv-ranking")
async def upload_specialization_csv(
    file: UploadFile = File(...), 
    default_position: str = Form("Part Time")
):
    """
    Parses CSV Matrix.
    - Row 1: Last Names
    - Row 2: First Names
    - Column A: Courses
    - Cells: Ratings (0-5)
    """
    try:
        content = await file.read()
        decoded_content = content.decode('utf-8', errors='replace')
        f = io.StringIO(decoded_content)
        reader = csv.reader(f)
        rows = list(reader)

        if len(rows) < 3:
            raise HTTPException(status_code=400, detail="CSV file is too short. Need at least 3 rows.")

        # --- 1. Parse Faculty Names (Rows 1 & 2) ---
        last_name_row = rows[0]
        first_name_row = rows[1]
        START_COL_IDX = 1
        
        col_to_faculty = {}
        col_to_faculty_formatted = {}  # Store properly formatted names
        
        for i in range(START_COL_IDX, max(len(last_name_row), len(first_name_row))):
            # Get and clean the names - remove any extra commas/periods
            last_name_raw = last_name_row[i] if i < len(last_name_row) else ""
            first_name_raw = first_name_row[i] if i < len(first_name_row) else ""
            
            # Remove special characters that might cause issues
            last_name = re.sub(r'[,.]', '', last_name_raw).strip().upper()
            first_name = re.sub(r'[,.]', '', first_name_raw).strip().upper()
            
            # Create formatted name for database storage: "LASTNAME, FIRSTNAME"
            if last_name and first_name:
                formatted_name = f"{last_name}, {first_name}"
                temp_match_name = f"{last_name}, {first_name}"
            elif last_name:
                formatted_name = last_name
                temp_match_name = last_name
            elif first_name:
                formatted_name = first_name
                temp_match_name = first_name
            else:
                continue
            
            col_to_faculty[i] = temp_match_name  # For matching logic
            col_to_faculty_formatted[i] = formatted_name  # For database storage

        if not col_to_faculty:
            raise HTTPException(status_code=400, detail="No faculty names found in Rows 1-2.")

        # --- 2. Prepare Database Mapping ---
        faculty_ref = db.collection("faculty")
        db_faculty_map = {}
        db_faculty_original = {}
        
        for doc in faculty_ref.stream():
            d = doc.to_dict()
            original_name = d.get('name', '').strip()
            if original_name:
                cleaned_name = clean_name(original_name)
                db_faculty_map[cleaned_name] = doc.id
                db_faculty_original[doc.id] = original_name

        # --- 3. Create Missing Faculty Members ---
        created_faculty = []
        unmatched_faculty_cols = []
        
        for col_idx, csv_faculty_name in col_to_faculty.items():
            target_id = match_faculty_name(csv_faculty_name, db_faculty_map)
            if not target_id:
                unmatched_faculty_cols.append(col_idx)
        
        for col_idx in unmatched_faculty_cols:
            # Use the properly formatted name from col_to_faculty_formatted
            db_name = col_to_faculty_formatted[col_idx]
            csv_name = col_to_faculty[col_idx]
            
            new_faculty_id = random.randint(1, 1000000)
            
            # Set ALL possible status field variations to ensure it works
            new_faculty_data = {
                "id": new_faculty_id,
                "name": db_name,  # Already in "LASTNAME, FIRSTNAME" format
                "email": "",
                "specialization": "",
                "department": "",
                "position": "Faculty",
                "status": default_position,
                "employmentStatus": default_position,
                "Status": default_position,
            }
            
            faculty_ref.document(str(new_faculty_id)).set(new_faculty_data)
            
            # Update local maps so we can match courses to this new faculty immediately
            cleaned_name = clean_name(db_name)
            db_faculty_map[cleaned_name] = str(new_faculty_id)
            db_faculty_original[str(new_faculty_id)] = db_name
            
            created_faculty.append({
                "csv_name": csv_name,
                "db_name": db_name,
                "id": new_faculty_id,
                "status": default_position
            })
            
            logger.info(f"Created faculty: {db_name} (ID: {new_faculty_id}) Status: {default_position}")

        # --- 4. Prepare Batch Updates for Courses ---
        batch = db.batch()
        faculty_updates = {}
        matching_log = []

        for row_idx in range(2, len(rows)):
            row = rows[row_idx]
            if not row: continue

            course_name = row[0].strip() if len(row) > 0 else ""
            if not course_name: continue

            # Check for valid ratings in this row
            has_ratings = False
            for col_idx in range(START_COL_IDX, len(row)):
                cell_val = row[col_idx].strip() if col_idx < len(row) else ""
                if cell_val.isdigit() and 0 <= int(cell_val) <= 5:
                    has_ratings = True
                    break
            
            if not has_ratings: continue

            # Process Ratings
            for col_idx, csv_faculty_name in col_to_faculty.items():
                if col_idx >= len(row): continue
                
                rating_str = row[col_idx].strip()
                if not rating_str: continue

                try:
                    rating = int(float(rating_str))
                    if 0 <= rating <= 5:
                        target_id = match_faculty_name(csv_faculty_name, db_faculty_map)
                        
                        if target_id:
                            if target_id not in faculty_updates:
                                faculty_updates[target_id] = []
                                if not any(log.get('db_id') == target_id for log in matching_log):
                                    matching_log.append({
                                        "csv_name": csv_faculty_name,
                                        "db_name": db_faculty_original[target_id],
                                        "db_id": target_id,
                                        "matched": True
                                    })
                            
                            clean_course = course_name.replace('"', '').strip()
                            faculty_updates[target_id].append(f"{clean_course} ({rating})")
                except ValueError:
                    continue

        # --- 5. Commit Updates ---
        count = 0
        for doc_id, specializations in faculty_updates.items():
            if specializations:
                spec_string = ", ".join(specializations)
                batch.update(faculty_ref.document(doc_id), {"specialization": spec_string})
                count += 1
        
        if count > 0:
            batch.commit()
            refresh_faculty_cache()
        
        matched_faculty = [log for log in matching_log if log['matched']]
        
        return {
            "status": "success", 
            "message": f"Updated rankings for {count} faculty. Created {len(created_faculty)} new faculty.",
            "details": {
                "total_faculty_in_csv": len(col_to_faculty),
                "matched_faculty": count,
                "created_faculty": len(created_faculty),
                "default_position": default_position,
                "total_specializations": sum(len(specs) for specs in faculty_updates.values()),
                "matched_names": [f"{m['csv_name']} → {m['db_name']}" for m in matched_faculty],
                "created_faculty_list": [f"{f['csv_name']} → {f['db_name']} (ID: {f['id']})" for f in created_faculty]
            }
        }

    except Exception as e:
        logger.exception("Error processing CSV ranking")
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")