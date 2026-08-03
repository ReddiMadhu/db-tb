import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import engine, Base

import app.models.db_models  # Ensures all ORM models are registered with Base
import app.models.stage_model  # Stage results + Databricks connections tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create all SQLite tables on startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully.")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = f"Exception: {str(exc)}\n{traceback.format_exc()}"
    logger.error("Unhandled exception on %s %s:\n%s", request.method, request.url.path, error_msg)

    try:
        log_path = os.path.join(os.getcwd(), "error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- ERROR AT {datetime.now()} ---\n{error_msg}\n")
    except Exception:
        pass

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check server logs for details."},
    )


@app.get("/")
def root():
    return {"message": "Welcome to Tableau to Databricks Lakeview Migration Engine API"}
