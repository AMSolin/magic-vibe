from pathlib import Path
from time import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.app_data_session import get_app_data_db
from app.db.user_data_session import get_user_data_db
from app.models.app_data import AppSetting, CatalogImport
from app.models.user_data import Collection, Player
from app.schemas.admin import (
    CatalogImportRead,
    CatalogStatusRead,
    GeneratedTestCollectionRead,
    GeneratedTestCollectionsRead,
    ScryfallSymbolsStatusRead,
    UserDataStatusRead,
)
from app.services import catalog, scryfall
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

TEST_COLLECTION_SPECS = (
    {
        "name": "Test EN ALL unique printings 2010+",
        "language_code": "en",
        "note": (
            "All unique English Scryfall printings from sets released since "
            "2010-01-01 in the local catalog; quantity 4 each."
        ),
        "where_sql": """
            p.language_code = 'en'
            and exists (
                select 1
                from catalog.card_printing_faces as face
                where face.printing_id = p.id
            )
        """,
    },
    {
        "name": "Test RU ALL localized printings 2010+",
        "language_code": "ru",
        "note": (
            "All unique Scryfall printings with Russian localization from sets "
            "released since 2010-01-01 in the local catalog; quantity 4 each."
        ),
        "where_sql": """
            exists (
                select 1
                from catalog.card_printing_faces as face
                join catalog.card_face_localizations as localization
                    on localization.face_id = face.id
                where face.printing_id = p.id
                    and localization.language_code = 'ru'
            )
        """,
    },
)

TEST_COLLECTION_SINCE_TIMESTAMP = 1_262_304_000


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


def _test_collection_player(db: Session) -> Player:
    player = db.scalar(select(Player).where(Player.is_default.is_(True)).limit(1))
    if player is None:
        player = db.scalar(select(Player).order_by(Player.created_at, Player.id).limit(1))
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User database is not initialized",
        )
    return player


def _get_or_create_test_collection(db: Session, player: Player, spec: dict[str, str]) -> Collection:
    collection = db.scalar(
        select(Collection).where(
            Collection.player_id == player.id,
            Collection.name == spec["name"],
        )
    )
    if collection is None:
        collection = Collection(
            player_id=player.id,
            name=spec["name"],
            note=spec["note"],
            is_default=False,
            is_wishlist=False,
            created_at=int(time()),
        )
        db.add(collection)
        db.flush()
    else:
        collection.note = spec["note"]
        collection.is_wishlist = False
    return collection


def _insert_test_collection_items(
    db: Session,
    collection: Collection,
    spec: dict[str, str],
) -> GeneratedTestCollectionRead:
    connection = db.connection()
    connection.exec_driver_sql(
        """
        insert or ignore into collection_items (
            collection_id,
            scryfall_id,
            finish_id,
            language_code,
            condition_code,
            quantity,
            created_at
        )
        select
            ?,
            p.scryfall_id,
            0,
            ?,
            'NM',
            4,
            ?
        from catalog.card_printings as p
        join catalog.sets as s on s.code = p.set_code
        join catalog.card_printing_finishes as finish
            on finish.printing_id = p.id
            and finish.finish_id = 0
        where s.release_date >= ?
            and p.scryfall_id is not null
            and {where_sql}
        group by p.scryfall_id
        """.format(where_sql=spec["where_sql"]),
        (
            collection.id,
            spec["language_code"],
            int(time()),
            TEST_COLLECTION_SINCE_TIMESTAMP,
        ),
    )
    connection.exec_driver_sql(
        """
        update collection_items
        set quantity = 4
        where collection_id = ?
            and finish_id = 0
            and language_code = ?
            and condition_code = 'NM'
            and quantity < 4
            and scryfall_id in (
                select p.scryfall_id
                from catalog.card_printings as p
                join catalog.sets as s on s.code = p.set_code
                join catalog.card_printing_finishes as finish
                    on finish.printing_id = p.id
                    and finish.finish_id = 0
                where s.release_date >= ?
                    and p.scryfall_id is not null
                    and {where_sql}
            )
        """.format(where_sql=spec["where_sql"]),
        (collection.id, spec["language_code"], TEST_COLLECTION_SINCE_TIMESTAMP),
    )
    row = connection.exec_driver_sql(
        """
        select
            count(*) as rows,
            count(distinct scryfall_id) as unique_scryfall_ids,
            coalesce(sum(quantity), 0) as total_quantity
        from collection_items
        where collection_id = ?
        """,
        (collection.id,),
    ).mappings().one()
    return GeneratedTestCollectionRead(
        id=collection.id,
        name=collection.name,
        language_code=spec["language_code"],
        rows=row["rows"],
        unique_scryfall_ids=row["unique_scryfall_ids"],
        total_quantity=row["total_quantity"],
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


@router.post("/test-collections/generate", response_model=GeneratedTestCollectionsRead)
def generate_test_collections(
    db: Session = Depends(get_user_data_db),
) -> GeneratedTestCollectionsRead:
    catalog_path = catalog.catalog_database_path()
    if not catalog_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Catalog database is not installed",
    )

    connection = db.connection()
    attached_database_names = {
        row[1] for row in connection.exec_driver_sql("pragma database_list").fetchall()
    }
    if "catalog" not in attached_database_names:
        connection.exec_driver_sql("attach database ? as catalog", (str(catalog_path.resolve()),))
    try:
        player = _test_collection_player(db)
        collections: list[GeneratedTestCollectionRead] = []
        for spec in TEST_COLLECTION_SPECS:
            collection = _get_or_create_test_collection(db, player, spec)
            collections.append(_insert_test_collection_items(db, collection, spec))
        db.commit()
    except Exception:
        db.rollback()
        raise

    return GeneratedTestCollectionsRead(collections=collections)


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
