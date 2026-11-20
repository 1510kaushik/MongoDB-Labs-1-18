from pydantic import BaseModel, Field


class TenantRegistrationRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=80)
    tenant_slug: str = Field(
        min_length=2,
        max_length=48,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    tenant_slug: str
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    user_id: str
    tenant_id: str
    tenant_slug: str
    email: str
    role: str

from datetime import datetime
from typing import Literal


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["pending", "in_progress", "completed"] = "pending"


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["pending", "in_progress", "completed"] | None = None


class TaskResponse(BaseModel):
    task_id: str
    tenant_id: str
    title: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
