from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from .database import db
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if credentials is None:
        raise unauthorized

    try:
        claims = decode_access_token(credentials.credentials)
        user_id = ObjectId(claims["sub"])
        tenant_id = ObjectId(claims["tenant_id"])
    except (JWTError, ValueError, TypeError, KeyError):
        raise unauthorized

    # Both IDs must match the same user record.
    user = db.users.find_one({
        "_id": user_id,
        "tenant_id": tenant_id,
        "status": "active"
    })

    if not user:
        raise unauthorized

    tenant = db.tenants.find_one({
        "_id": tenant_id,
        "status": "active"
    })

    if not tenant:
        raise unauthorized

    return {
        "user_id": str(user["_id"]),
        "tenant_id": str(tenant["_id"]),
        "tenant_slug": tenant["slug"],
        "email": user["email"],
        "role": user["role"]
    }
