from fastapi import APIRouter, HTTPException
from app.models.auth import LoginRequest, LoginResponse
from app.core.auth import create_access_token
from app.core.firebase import db
import logging
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger("auth")
router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(login_req: LoginRequest):
    try:
        admins_ref = db.collection("admins")
        admin_docs = admins_ref.where(filter=FieldFilter("email", "==", login_req.email)).stream()
        admin = None
        for doc in admin_docs:
            admin = doc.to_dict()
            break

        if not admin:
            logger.warning("Login failed: Admin not found")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if admin.get("password") != login_req.password:
            logger.warning("Login failed: Password mismatch")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = create_access_token({"email": login_req.email})
        return LoginResponse(access_token=access_token)
    except HTTPException as he:
        logger.error(f"HTTP error in login: {he.detail}")
        raise he
    except Exception as e:
        logger.exception("Unexpected error in login")
        raise HTTPException(status_code=500, detail="Internal Server Error in login")
