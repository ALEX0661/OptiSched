from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
import pandas as pd
import io
from app.core.auth import verify_token_allowed
from app.utils.helper import get_value
import logging

logger = logging.getLogger("excel")
router = APIRouter(dependencies=[Depends(verify_token_allowed)])
 
@router.post("/")
async def upload_excel(file: UploadFile = File(...)):
    try:
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(status_code=400, detail="Invalid file format. Please upload an Excel file.")
    
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        courses = []
        for index, row in df.iterrows():
            course = {
                "courseCode": get_value(row, ["Course Code", "CourseCode"]),
                "title": get_value(row, ["Title"]),
                "program": get_value(row, ["Program"]),
                "unitsLecture": int(get_value(row, ["Units Lecture", "Lecture Units"], 0)),
                "unitsLab": int(get_value(row, ["Units Lab", "Lab Units"], 0)),
                "yearLevel": int(get_value(row, ["Year Level", "Year"], 0)),
                "blocks": 0
            }
            courses.append(course)
        return {"courses": courses}
    except HTTPException as he:
        logger.error(f"HTTP error in upload_excel: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in upload_excel")
        raise HTTPException(status_code=500, detail="Internal Server Error in upload_excel")
