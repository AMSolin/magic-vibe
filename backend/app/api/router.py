from fastapi import APIRouter

from app.api.routes import admin, import_data, workspace

api_router = APIRouter()
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(import_data.router, prefix="/import", tags=["import"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["workspace"])
