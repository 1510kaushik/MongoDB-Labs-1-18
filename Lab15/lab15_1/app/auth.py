from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from .database import db
from .schemas import (
    TenantRegistrationRequest,
    LoginRequest,
    TokenResponse,
    UserResponse
)
from .security import (
    hash_password,
    verify_password,
    create_access_token
)
from .dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_tenant(data: TenantRegistrationRequest):
    tenant_slug = data.tenant_slug.strip().lower()
    email = data.email.strip().lower()

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(
            status_code=422,
            detail="A valid email address is required"
        )

    now = datetime.now(timezone.utc)
    tenant_id = ObjectId()

    tenant = {
        "_id": tenant_id,
        "name": data.tenant_name.strip(),
        "slug": tenant_slug,
        "status": "active",
        "created_at": now
    }

    try:
        db.tenants.insert_one(tenant)

        user = {
            "_id": ObjectId(),
            "tenant_id": tenant_id,
            "email": email,
            "password_hash": hash_password(data.password),
            "role": "owner",
            "status": "active",
            "created_at": now
        }

        db.users.insert_one(user)

    except DuplicateKeyError:
        db.tenants.delete_one({"_id": tenant_id})

        raise HTTPException(
            status_code=409,
            detail="Tenant slug or user already exists"
        )

    except Exception:
        db.tenants.delete_one({"_id": tenant_id})
        raise

    return UserResponse(
        user_id=str(user["_id"]),
        tenant_id=str(tenant_id),
        tenant_slug=tenant_slug,
        email=email,
        role="owner"
    )


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest):
    tenant = db.tenants.find_one({
        "slug": data.tenant_slug.strip().lower(),
        "status": "active"
    })

    if not tenant:
        raise HTTPException(
            status_code=401,
            detail="Invalid tenant or login credentials"
        )

    email = data.email.strip().lower()

    user = db.users.find_one({
        "tenant_id": tenant["_id"],
        "email": email,
        "status": "active"
    })

    if not user or not verify_password(
        data.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid tenant or login credentials"
        )

    token = create_access_token(
        user_id=str(user["_id"]),
        tenant_id=str(tenant["_id"]),
        role=user["role"]
    )

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)
