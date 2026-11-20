from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .database import db
from .rate_limiter import enforce_tenant_rate_limit
from .dependencies import get_current_user
from .schemas import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter(prefix="/tasks", tags=["Tasks"], dependencies=[Depends(enforce_tenant_rate_limit)])


def serialize_task(document):
    return {
        "task_id": str(document["_id"]),
        "tenant_id": str(document["tenant_id"]),
        "title": document["title"],
        "description": document.get("description"),
        "status": document["status"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"]
    }


def get_task_object_id(task_id: str):
    try:
        return ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Task not found")


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED
)
def create_task(
    data: TaskCreate,
    current_user: dict = Depends(get_current_user)
):
    tenant_id = ObjectId(current_user["tenant_id"])
    now = datetime.now(timezone.utc)

    document = {
        "_id": ObjectId(),
        "tenant_id": tenant_id,
        "title": data.title.strip(),
        "description": data.description,
        "status": data.status,
        "created_at": now,
        "updated_at": now
    }

    if not document["title"]:
        raise HTTPException(status_code=422, detail="Title cannot be empty")

    db.tasks.insert_one(document)

    # Retrieve only within the authenticated tenant.
    saved = db.tasks.find_one({
        "_id": document["_id"],
        "tenant_id": tenant_id
    })

    return serialize_task(saved)


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    task_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(pending|in_progress|completed)$"
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    tenant_id = ObjectId(current_user["tenant_id"])

    # Tenant filter is always present.
    query = {"tenant_id": tenant_id}

    if task_status:
        query["status"] = task_status

    cursor = (
        db.tasks.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    return [serialize_task(doc) for doc in cursor]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    tenant_id = ObjectId(current_user["tenant_id"])
    task_oid = get_task_object_id(task_id)

    document = db.tasks.find_one({
        "_id": task_oid,
        "tenant_id": tenant_id
    })

    if not document:
        raise HTTPException(status_code=404, detail="Task not found")

    return serialize_task(document)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    data: TaskUpdate,
    current_user: dict = Depends(get_current_user)
):
    tenant_id = ObjectId(current_user["tenant_id"])
    task_oid = get_task_object_id(task_id)

    updates = data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    if "title" in updates:
        if updates["title"] is None or not updates["title"].strip():
            raise HTTPException(
                status_code=422,
                detail="Title cannot be empty"
            )
        updates["title"] = updates["title"].strip()

    if "status" in updates and updates["status"] is None:
        raise HTTPException(
            status_code=422,
            detail="Status cannot be null"
        )

    updates["updated_at"] = datetime.now(timezone.utc)

    # Both task ID and tenant ID are required for an update.
    task_filter = {
        "_id": task_oid,
        "tenant_id": tenant_id
    }

    result = db.tasks.update_one(
        task_filter,
        {"$set": updates}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = db.tasks.find_one(task_filter)

    return serialize_task(updated)


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    tenant_id = ObjectId(current_user["tenant_id"])
    task_oid = get_task_object_id(task_id)

    result = db.tasks.delete_one({
        "_id": task_oid,
        "tenant_id": tenant_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "message": "Task deleted successfully",
        "task_id": task_id
    }

