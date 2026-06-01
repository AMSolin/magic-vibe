from pathlib import Path
from time import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.app_data_session import get_app_data_db
from app.models.app_data import AppSetting, CatalogImport
from app.schemas.admin import (
    CatalogImportRead,
    CatalogStatusRead,
    ScryfallSymbolsStatusRead,
    UserDataStatusRead,
)
from app.services import scryfall
from app.services.catalog_download import (
    ACTIVE_DOWNLOAD_STATUSES,
    CATALOG_SOURCE_NAME,
    download_catalog_source,
)
from app.services.catalog_import import LOCAL_CATALOG_SOURCE_NAME, rebuild_catalog_from_local_source
from app.services.user_data import (
    recreate_user_data_db,
    user_data_database_exists,
    user_data_database_path,
)

router = APIRouter()


def _user_data_status() -> UserDataStatusRead:
    if not user_data_database_exists():
        return UserDataStatusRead(exists=False, file_size=None, modified_at=None)

    database_stat = user_data_database_path().stat()
    return UserDataStatusRead(
        exists=True,
        file_size=database_stat.st_size,
        modified_at=int(database_stat.st_mtime),
    )


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


@router.get("/user-data", response_model=UserDataStatusRead)
def get_user_data_status() -> UserDataStatusRead:
    return _user_data_status()


@router.post("/user-data/recreate", response_model=UserDataStatusRead)
def recreate_user_data() -> UserDataStatusRead:
    recreate_user_data_db()
    return _user_data_status()


@router.get("/scryfall-symbols", response_model=ScryfallSymbolsStatusRead)
def get_scryfall_symbols_status() -> dict:
    return scryfall.get_symbols_status()


@router.post("/scryfall-symbols/update", response_model=ScryfallSymbolsStatusRead)
def update_scryfall_symbols() -> dict:
    try:
        return scryfall.update_symbols_cache()
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Scryfall symbols cache update failed: {error}",
        ) from error


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
