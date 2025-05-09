from ortools.sat.python import cp_model
from collections import defaultdict
from app.core.globals import schedule_dict, progress_state
from app.core.firebase import load_courses, load_rooms, load_time_settings, load_days
import logging

logger = logging.getLogger("schedgeneration")

def generate_schedule(process_id=None):
    # Load & prioritize courses
    if process_id:
        progress_state[process_id] = 5  
    courses = sorted(load_courses(), key=lambda c: c.get("yearLevel", 0))
    if process_id:
        progress_state[process_id] = 15 
    rooms = load_rooms()
    if process_id:
        progress_state[process_id] = 25 
    time_settings = load_time_settings()
    if process_id:
        progress_state[process_id] = 35  
    days = load_days()
    if process_id:
        progress_state[process_id] = 45  

    # Time discretization
    start_t = time_settings["start_time"]
    end_t = time_settings["end_time"]
    inc_hr = 2
    inc_day = (end_t - start_t) * inc_hr
    total_inc = inc_day * len(days)
    if process_id:
        progress_state[process_id] = 50  

    # Valid lab starts (3-slot)
    lab_starts = []
    for d in range(len(days)):
        base = d * inc_day
        lab_starts += list(range(base, base + inc_day - 2))
    if process_id:
        progress_state[process_id] = 55  

    model = cp_model.CpModel()
    schedule_id = 1
    all_sessions = []  
    section_intervals = defaultdict(list)
    room_intervals = {('lecture', r): [] for r in range(len(rooms['lecture']))}
    room_intervals.update({('lab', r): [] for r in range(len(rooms['lab']))})
    if process_id:
        progress_state[process_id] = 60  
    
    for idx, course in enumerate(courses, start=1):
        code, title, prog, yr = (course["courseCode"], course["title"], course["program"], course["yearLevel"])
        lec_u, lab_u = course["unitsLecture"], course["unitsLab"]
        blocks = course.get("blocks", 1)
        day_vars = []

        for b in range(blocks):
            blk = chr(ord('A') + b)
            for sess_type, units, dur in [('lecture', lec_u, 2), ('lab', lab_u * 2, 3)]:
                for i in range(units):
                    # Start variable
                    if sess_type == 'lecture':
                        s = model.NewIntVar(0, total_inc - 1, f"{code}_{sess_type}_{b}_{i}_s")
                    else:
                        s = model.NewIntVarFromDomain(cp_model.Domain.FromValues(lab_starts), f"{code}_lab_{b}_{i}_s")
                    # End variable and consistency with duration
                    e = model.NewIntVar(0, total_inc, f"{code}_{sess_type}_{b}_{i}_e")
                    model.Add(e == s + dur)
                    # Day variable constraints
                    dvar = model.NewIntVar(0, len(days) - 1, f"{code}_{sess_type}_{b}_{i}_d")
                    model.Add(s >= dvar * inc_day)
                    model.Add(s < (dvar + 1) * inc_day)
                    day_vars.append(dvar)
                    # Room assignment variable
                    rv = model.NewIntVar(0, len(rooms[sess_type]) - 1, f"{code}_{sess_type}_{b}_{i}_room")
                    # Interval for section
                    iv = model.NewIntervalVar(s, dur, e, f"iv_{sess_type}_{schedule_id}")
                    section_intervals[(prog, yr, blk)].append(iv)
                    # Optional intervals per room
                    for r in range(len(rooms[sess_type])):
                        lit = model.NewBoolVar(f"use_{schedule_id}_room_{r}")
                        model.Add(rv == r).OnlyEnforceIf(lit)
                        model.Add(rv != r).OnlyEnforceIf(lit.Not())
                        opt_iv = model.NewOptionalIntervalVar(s, dur, e, lit, f"opt_iv_{schedule_id}_{sess_type}_{r}")
                        room_intervals[(sess_type, r)].append(opt_iv)
                    ckey = (code, prog, yr, blk, sess_type)
                    all_sessions.append((schedule_id, ckey, title, s, e, rv, dvar, dur))
                    schedule_id += 1
        # Ensure different days if fewer sessions than days
        if len(day_vars) <= len(days):
            model.AddAllDifferent(day_vars)
        # Update progress per course block
        if process_id:
            progress_state[process_id] = 60 + int(30 * idx / len(courses))  # up to 90

    if process_id:
        progress_state[process_id] = 90  # Variables and intervals created

    # Room consistency constraints
    by_ckey = defaultdict(list)
    for sid, ckey, title, s, e, rv, dvar, dur in all_sessions:
        by_ckey[ckey].append(rv)
    for rvs in by_ckey.values():
        for v1 in rvs[1:]:
            model.Add(v1 == rvs[0])

    # No overlap constraints
    for ivs in section_intervals.values():
        model.AddNoOverlap(ivs)
    for ivs in room_intervals.values():
        model.AddNoOverlap(ivs)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    solver.parameters.num_search_workers = 8
    if process_id:
        progress_state[process_id] = 95  # Solver configured, starting solve

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if process_id:
            progress_state[process_id] = -1
        logger.error("No feasible schedule found.")
        return "impossible"

    # Extract solution
    schedule = []
    for sid, ckey, title, s, e, rv, dvar, dur in all_sessions:
        code, prog, yr, blk, sess_type = ckey
        room_idx = solver.Value(rv)
        day_idx = solver.Value(dvar)
        offs = solver.Value(s) % inc_day
        hr = start_t + offs / inc_hr
        m1 = int((hr - int(hr)) * 60)
        t1 = f"{int(hr)%12 or 12}:{m1:02d} {'AM' if hr<12 else 'PM'}"
        hr2 = hr + dur / inc_hr
        m2 = int((hr2 - int(hr2)) * 60)
        t2 = f"{int(hr2)%12 or 12}:{m2:02d} {'AM' if hr2<12 else 'PM'}"
        schedule.append({
            'schedule_id': sid,
            'courseCode': code,
            'title': title,
            'program': prog,
            'year': yr,
            'session': 'Lecture' if sess_type == 'lecture' else 'Laboratory',
            'block': blk,
            'day': days[day_idx],
            'period': f"{t1} - {t2}",
            'room': rooms[sess_type][room_idx]
        })
    schedule.sort(key=lambda x: (days.index(x['day']), x['period']))

    
    schedule_dict.clear()
    schedule_dict.update({e['schedule_id']: e for e in schedule})
    if process_id:
        progress_state[process_id] = 100  
        
    return schedule
