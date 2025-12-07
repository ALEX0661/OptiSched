from fastapi import HTTPException, Header
from firebase_admin import auth
import logging

# Setup Logger
logger = logging.getLogger("app.core.auth")

def verify_token_allowed(authorization: str = Header(...)) -> dict:
    """
    Verifies the Firebase ID Token provided in the Authorization header.
    """
    # 1. Validate Header Existence
    if not authorization:
        logger.warning("Authentication failed: Missing Authorization header.")
        raise HTTPException(status_code=401, detail="Authorization header missing")

    # 2. Validate Header Format
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            logger.warning(f"Authentication failed: Invalid scheme '{scheme}'. Expected 'Bearer'.")
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    except ValueError:
        logger.warning("Authentication failed: Invalid header format.")
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    # 3. Verify Token with Firebase Admin SDK
    try:
        decoded_token = auth.verify_id_token(token)
        email = decoded_token.get("email")
        
        # Log successful authentication (useful for audit trails)
        logger.info(f"User successfully authenticated: {email}")
        
        return decoded_token

    except auth.ExpiredIdTokenError:
        logger.warning("Authentication failed: Token has expired.")
        raise HTTPException(status_code=401, detail="Token expired")
        
    except auth.InvalidIdTokenError:
        logger.warning("Authentication failed: Invalid ID token provided.")
        raise HTTPException(status_code=401, detail="Invalid token")
        
    except auth.RevokedIdTokenError:
        logger.warning("Authentication failed: Token has been revoked.")
        raise HTTPException(status_code=401, detail="Token revoked")
        
    except Exception as e:
        logger.error(f"Critical authentication error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed due to internal error")