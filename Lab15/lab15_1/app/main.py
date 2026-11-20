from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import db, client, ensure_indexes, check_connection
from .auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_connection()
    ensure_indexes()
    yield
    client.close()


app = FastAPI(
    title="Lab 15.1 - Multi-Tenant Task Management API",
    description="A tenant-isolated REST API using FastAPI and MongoDB.",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(auth_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "Multi-Tenant Task Management API",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
def health():
    check_connection()
    return {
        "ok": True,
        "database": db.name
    }

from .tasks import router as tasks_router
app.include_router(tasks_router)
