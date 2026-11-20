import uuid

import pytest
from fastapi.testclient import TestClient
from bson import ObjectId

from app.main import app
from app.database import db
import app.rate_limiter as rate_limiter


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def create_tenant(client, prefix="pytest"):
    unique = uuid.uuid4().hex[:12]
    slug = f"{prefix}-{unique}"
    email = f"owner-{unique}@example.com"
    password = "TestPassword123!"

    response = client.post(
        "/auth/register",
        json={
            "tenant_name": f"Test Company {unique}",
            "tenant_slug": slug,
            "email": email,
            "password": password
        }
    )

    assert response.status_code == 201, response.text

    login = client.post(
        "/auth/login",
        json={
            "tenant_slug": slug,
            "email": email,
            "password": password
        }
    )

    assert login.status_code == 200, login.text

    token = login.json()["access_token"]

    return {
        "slug": slug,
        "email": email,
        "password": password,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "user": response.json()
    }


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["database"] == "lab15_multitenant"


def test_registration_login_and_profile(client):
    tenant = create_tenant(client)

    profile = client.get(
        "/auth/me",
        headers=tenant["headers"]
    )

    assert profile.status_code == 200
    assert profile.json()["tenant_id"] == tenant["user"]["tenant_id"]
    assert profile.json()["role"] == "owner"

    invalid_login = client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant["slug"],
            "email": tenant["email"],
            "password": "IncorrectPassword123!"
        }
    )

    assert invalid_login.status_code == 401


def test_task_crud_and_tenant_isolation(client):
    tenant_a = create_tenant(client, "tenant-a")
    tenant_b = create_tenant(client, "tenant-b")

    headers_a = tenant_a["headers"]
    headers_b = tenant_b["headers"]

    # Create one task for each tenant.
    created_a = client.post(
        "/tasks",
        headers=headers_a,
        json={
            "title": "Tenant A private task",
            "description": "Private to tenant A",
            "status": "pending"
        }
    )

    created_b = client.post(
        "/tasks",
        headers=headers_b,
        json={
            "title": "Tenant B private task",
            "description": "Private to tenant B",
            "status": "pending"
        }
    )

    assert created_a.status_code == 201
    assert created_b.status_code == 201

    task_a = created_a.json()
    task_b = created_b.json()

    # Each tenant should see only its own task.
    list_a = client.get("/tasks", headers=headers_a)
    list_b = client.get("/tasks", headers=headers_b)

    assert list_a.status_code == 200
    assert list_b.status_code == 200

    assert [task["task_id"] for task in list_a.json()] == [task_a["task_id"]]
    assert [task["task_id"] for task in list_b.json()] == [task_b["task_id"]]

    # Cross-tenant read protection.
    assert client.get(
        f"/tasks/{task_a['task_id']}",
        headers=headers_b
    ).status_code == 404

    assert client.get(
        f"/tasks/{task_b['task_id']}",
        headers=headers_a
    ).status_code == 404

    # Cross-tenant update protection.
    assert client.put(
        f"/tasks/{task_a['task_id']}",
        headers=headers_b,
        json={"title": "Unauthorized update"}
    ).status_code == 404

    assert client.put(
        f"/tasks/{task_b['task_id']}",
        headers=headers_a,
        json={"title": "Unauthorized update"}
    ).status_code == 404

    # Cross-tenant delete protection.
    assert client.delete(
        f"/tasks/{task_a['task_id']}",
        headers=headers_b
    ).status_code == 404

    assert client.delete(
        f"/tasks/{task_b['task_id']}",
        headers=headers_a
    ).status_code == 404

    # Normal CRUD operations for tenant A.
    retrieved = client.get(
        f"/tasks/{task_a['task_id']}",
        headers=headers_a
    )
    assert retrieved.status_code == 200

    updated = client.put(
        f"/tasks/{task_a['task_id']}",
        headers=headers_a,
        json={
            "title": "Updated tenant A task",
            "status": "completed"
        }
    )

    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated tenant A task"
    assert updated.json()["status"] == "completed"

    deleted = client.delete(
        f"/tasks/{task_a['task_id']}",
        headers=headers_a
    )

    assert deleted.status_code == 200

    missing = client.get(
        f"/tasks/{task_a['task_id']}",
        headers=headers_a
    )

    assert missing.status_code == 404

    # Clean up the remaining test task.
    client.delete(
        f"/tasks/{task_b['task_id']}",
        headers=headers_b
    )


def test_mongodb_backed_rate_limit(client, monkeypatch):
    tenant = create_tenant(client, "rate-test")

    # Use a low limit in this isolated test rather than sending 101 requests.
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_REQUESTS", 2)

    first = client.get("/tasks", headers=tenant["headers"])
    second = client.get("/tasks", headers=tenant["headers"])
    third = client.get("/tasks", headers=tenant["headers"])

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Retry-After" in third.headers

    tenant_id = ObjectId(tenant["user"]["tenant_id"])

    counter = db.rate_limits.find_one({
        "tenant_id": tenant_id
    })

    assert counter is not None
    assert counter["requests"] == 3
    assert counter["expires_at"] is not None
