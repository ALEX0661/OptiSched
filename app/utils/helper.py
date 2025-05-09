import pandas as pd

def get_value(row, keys, default=None):
    for key in keys:
        if key in row and pd.notna(row[key]):
            return row[key]
    return default

def format_period(new_start_str: str, duration_minutes: int) -> str:
    hours, minutes = map(int, new_start_str.split(":"))
    start_total = hours * 60 + minutes
    end_total = start_total + duration_minutes 

    def format_time(total_minutes):
        hour = total_minutes // 60 
        minute = total_minutes % 60 
        suffix = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12
        hour_12 = 12 if hour_12 == 0 else hour_12
        return f"{hour_12}:{minute:02d} {suffix}"

    return f"{format_time(start_total)} - {format_time(end_total)}"
