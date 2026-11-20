# Lab 15.1 - Multi-Tenant API

## Overview
A multi-tenant task management REST API built using FastAPI and MongoDB.

## Technologies
- Python 3.12
- FastAPI
- Uvicorn
- MongoDB
- PyMongo
- JWT authentication
- Argon2 password hashing
- Pytest

## Architecture

Each tenant has an independent identity. Users and tasks are associated
with a tenant_id. Database queries for tasks always include the
authenticated tenant_id.

## MongoDB Database
Database: lab15_multitenant

Collections:
- tenants
- users
- tasks
- rate_limits

## Indexes
- Unique tenant slug
- Unique user email within each tenant
- Tenant and creation date index for tasks
- Tenant and status index for tasks
- TTL index for rate-limit expiration
- Unique tenant and rate-limit window index

## Authentication Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /auth/register | Register tenant and owner |
| POST | /auth/login | Authenticate and receive JWT |
| GET | /auth/me | Retrieve authenticated profile |

Passwords are hashed using Argon2. JWT tokens contain user ID,
tenant ID, role and expiration information.

## Task Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /tasks | Create task |
| GET | /tasks | List tenant tasks |
| GET | /tasks/{task_id} | Retrieve task |
| PUT | /tasks/{task_id} | Update task |
| DELETE | /tasks/{task_id} | Delete task |

All task database operations are scoped to the authenticated tenant.

## Rate Limiting

Storage: MongoDB rate_limits collection

Configured limit: 100 requests per tenant
Time window: 60 seconds

Excess requests receive HTTP 429 and a Retry-After header.
Expired counters are removed using a MongoDB TTL index.

## API Configuration

Application URL: http://127.0.0.1:8015

Interactive API documentation:
http://127.0.0.1:8015/docs

Health endpoint:
http://127.0.0.1:8015/health

## Automated Testing

Run from the lab15_1 directory:

    ..\.venv\Scripts\python.exe -m pytest .\tests -v

Verified test results:
- Health endpoint: PASSED
- Tenant registration, login and profile: PASSED
- CRUD and tenant isolation: PASSED
- MongoDB-backed rate limiting: PASSED

Total: 4 passed.

## Manual Security Verification

Two separate tenants were created.

Cross-tenant read attempts: HTTP 404
Cross-tenant update attempts: HTTP 404
Cross-tenant delete attempts: HTTP 404

Both tenants could access their own tasks only.

## Manual Rate-Limit Verification

Successful requests: 100
Rejected request: 101
HTTP status: 429
MongoDB counter verification: PASSED

## Database Connection Note

The development configuration currently connects directly to the
identified replica-set primary through port 27018.

If replica-set leadership changes, update the Lab 15.1 MONGODB_URI
to point to the current primary or configure an appropriate
replica-set-aware connection.

## Security Notes

- Do not commit .env.
- Do not publish JWT secrets.
- Use HTTPS and secure secret management in production.
- Configure authentication and authorization before production use.
