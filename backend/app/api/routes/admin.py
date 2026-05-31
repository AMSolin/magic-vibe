from pathlib import Path
from time import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.app_data_session import get_app_data_db
from app.models.app_data import AppSetting, CatalogImport
from app.schemas.admin import CatalogImportRead, CatalogStatusRead
from app.services.catalog_download import (
    ACTIVE_DOWNLOAD_STATUSES,
    CATALOG_SOURCE_NAME,
    download_catalog_source,
)
from app.services.catalog_import import LOCAL_CATALOG_SOURCE_NAME, rebuild_catalog_from_local_source

router = APIRouter()


def _reject_active_catalog_update(db: Session) -> None:
    active_import = db.scalar(
        select(CatalogImport)
        .where(CatalogImport.status.in_(ACTIVE_DOWNLOAD_STATUSES))
        .order_by(CatalogImport.id.desc())
        .limit(1)
    )
    if active_import is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog update is already running",
        )


@router.get("/catalog", response_model=CatalogStatusRead)
def get_catalog_status(db: Session = Depends(get_app_data_db)) -> CatalogStatusRead:
    latest_import = db.scalar(select(CatalogImport).order_by(CatalogImport.id.desc()).limit(1))
    latest_successful_import = db.scalar(
        select(CatalogImport)
        .where(CatalogImport.status == "completed")
        .order_by(CatalogImport.id.desc())
        .limit(1)
    )

    return CatalogStatusRead(
        latest_import=latest_import,
        latest_successful_import=latest_successful_import,
    )


@router.post(
    "/catalog/update",
    response_model=CatalogImportRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_catalog_update(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_app_data_db),
) -> CatalogImport:
    _reject_active_catalog_update(db)

    catalog_import = CatalogImport(
        source=CATALOG_SOURCE_NAME,
        started_at=int(time()),
        status="pending",
    )
    db.add(catalog_import)
    db.commit()
    db.refresh(catalog_import)
    background_tasks.add_task(download_catalog_source, catalog_import.id)
    return catalog_import


@router.post(
    "/catalog/rebuild",
    response_model=CatalogImportRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_catalog_rebuild(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_app_data_db),
) -> CatalogImport:
    _reject_active_catalog_update(db)
    source_path = db.get(AppSetting, "catalog.pending_source_path")
    if source_path is None or source_path.value is None or not Path(source_path.value).is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local MTGJSON source file is not available. Update the catalog first.",
        )
    source_sha256 = db.get(AppSetting, "catalog.pending_source_sha256")
    known_sha256 = source_sha256.value if source_sha256 is not None else db.scalar(
        select(CatalogImport.source_sha256)
        .where(CatalogImport.source_sha256.is_not(None))
        .order_by(CatalogImport.id.desc())
        .limit(1)
    )

    catalog_import = CatalogImport(
        source=LOCAL_CATALOG_SOURCE_NAME,
        started_at=int(time()),
        status="pending",
        source_sha256=known_sha256,
    )
    db.add(catalog_import)
    db.commit()
    db.refresh(catalog_import)
    background_tasks.add_task(rebuild_catalog_from_local_source, catalog_import.id)
    return catalog_import
