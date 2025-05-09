import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Header
from app.core.firebase import verify_admin_email

SECRET_KEY = "SAAMDEVELOOPERS"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 180


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Token error: {str(e)}")


def verify_token_allowed(authorization: str = Header(...)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    payload = verify_token(token)
    email = payload.get("email")
    if not email or not verify_admin_email(email):
        raise HTTPException(status_code=403, detail="User not allowed")

    return payload