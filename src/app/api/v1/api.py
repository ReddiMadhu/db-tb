"""
Tableau to Databricks Migration — API Router Registry
"""

from fastapi import APIRouter
from app.api.v1.upload import router as upload_router
from app.api.v1.migrations import router as migrations_router
from app.api.v1.validation import router as validation_router
from app.api.v1.datasource_mapping import router as mapping_router
from app.api.v1.stages import router as stages_router
from app.api.v1.connections import router as connections_router

api_router = APIRouter()
api_router.include_router(upload_router, prefix="/migrations", tags=["upload"])
api_router.include_router(migrations_router, prefix="/migrations", tags=["migrations"])
api_router.include_router(stages_router, prefix="/migrations", tags=["stages"])
api_router.include_router(validation_router, prefix="/validation", tags=["validation"])
api_router.include_router(mapping_router, prefix="/mapping", tags=["datasource-mapping"])
api_router.include_router(connections_router, prefix="/connections", tags=["connections"])
