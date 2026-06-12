from fastapi import APIRouter

from app.api.routes import admin, workspace

api_router = APIRouter()
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["workspace"])
