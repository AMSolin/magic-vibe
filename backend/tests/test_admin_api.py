from collections.abc import Generator
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.app_data_base import AppDataBase
from app.db.app_data_session import get_app_data_db
from app.db.user_data_base import UserDataBase
from app.db.user_data_session import get_user_data_db
from app.main import app
from app.models.app_data import APP_DATA_MODELS, AppSetting, CatalogImport
from app.models.user_data import CardCondition, Player, USER_DATA_MODELS
from app.services import catalog
from app.services.catalog_download import CATALOG_SOURCE_NAME
from app.services.catalog_import import LOCAL_CATALOG_SOURCE_NAME


@pytest.fixture()
def app_data_session() -> Generator[sessionmaker[Session]]:
    _ = APP_DATA_MODELS
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    AppDataBase.metadata.create_all(bind=engine)

    def override_get_app_data_db() -> Generator[Session]:
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_app_data_db] = override_get_app_data_db
    yield testing_session
    app.dependency_overrides.clear()


def _create_test_collection_catalog(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table sets (code text primary key, release_date integer);
        create table card_printings (
            id integer primary key, scryfall_id blob, oracle_id blob, set_code text,
            collector_number text, language_code text, name text, rarity text, layout text
        );
        create table card_printing_finishes (printing_id integer, finish_id integer);
        create table card_printing_faces (
            id integer primary key, printing_id integer, face_order integer
        );
        create table card_face_localizations (
            id integer primary key, face_id integer, language_code text
        );
        insert into sets values ('NEW', 1262304000);
        insert into sets values ('OLD', 1262217600);
        """
    )
    rows = [
        (1, "40000000-0000-0000-0000-000000000001", "NEW", "en"),
        (2, "40000000-0000-0000-0000-000000000002", "NEW", "en"),
        (3, "40000000-0000-0000-0000-000000000003", "OLD", "en"),
    ]
    for printing_id, scryfall_id, set_code, language_code in rows:
        db.execute(
            """
            insert into card_printings values (
                ?, ?, ?, ?, ?, ?, ?, 'common', 'normal'
            )
            """,
            (
                printing_id,
                UUID(scryfall_id).bytes,
                UUID("50000000-0000-0000-0000-000000000001").bytes,
                set_code,
                str(printing_id),
                language_code,
                f"Card {printing_id}",
            ),
        )
        db.execute("insert into card_printing_finishes values (?, 0)", (printing_id,))
        db.execute(
            "insert into card_printing_faces values (?, ?, 0)",
            (printing_id, printing_id),
        )
    db.execute("insert into card_face_localizations values (1, 2, 'ru')")
    db.commit()
    db.close()


def test_catalog_status_is_empty_before_first_import(
    app_data_session: sessionmaker[Session],
) -> None:
    _ = app_data_session

    with TestClient(app) as client:
        response = client.get("/api/admin/catalog")

    assert response.status_code == 200
    assert response.json() == {
        "latest_import": None,
        "latest_successful_import": None,
    }


def test_catalog_status_keeps_installed_catalog_when_latest_attempt_failed(
    app_data_session: sessionmaker[Session],
) -> None:
    with app_data_session() as db:
        db.add(
            CatalogImport(
                source="MTGJSON AllPrintings.sqlite",
                source_updated_at=1_780_272_000,
                started_at=1_780_275_600,
                finished_at=1_780_275_720,
                status="completed",
                catalog_row_count=81_939,
                source_file_size=284_491_776,
                source_sha256="a" * 64,
            )
        )
        db.add(
            CatalogImport(
                source="MTGJSON AllPrintings.sqlite",
                started_at=1_780_362_000,
                finished_at=1_780_362_030,
                status="failed",
                error_message="Download failed",
            )
        )
        db.commit()

    with TestClient(app) as client:
        response = client.get("/api/admin/catalog")

    assert response.status_code == 200
    data = response.json()
    assert data["latest_import"]["status"] == "failed"
    assert data["latest_import"]["error_message"] == "Download failed"
    assert data["latest_successful_import"]["status"] == "completed"
    assert data["latest_successful_import"]["catalog_row_count"] == 81_939


def test_catalog_update_starts_background_download(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloaded_import_ids: list[int] = []
    monkeypatch.setattr(
        "app.api.routes.admin.download_catalog_source",
        downloaded_import_ids.append,
    )

    with TestClient(app) as client:
        response = client.post("/api/admin/catalog/update")

    assert response.status_code == 202
    data = response.json()
    assert data["source"] == CATALOG_SOURCE_NAME
    assert data["status"] == "pending"
    assert downloaded_import_ids == [data["id"]]


def test_catalog_update_rejects_parallel_download(
    app_data_session: sessionmaker[Session],
) -> None:
    with app_data_session() as db:
        db.add(
            CatalogImport(
                source=CATALOG_SOURCE_NAME,
                started_at=1_780_362_000,
                status="downloading",
            )
        )
        db.commit()

    with TestClient(app) as client:
        response = client.post("/api/admin/catalog/update")

    assert response.status_code == 409
    assert response.json() == {"detail": "Catalog update is already running"}


def test_catalog_rebuild_starts_background_local_import(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebuilt_import_ids: list[int] = []
    monkeypatch.setattr(
        "app.api.routes.admin.rebuild_catalog_from_local_source",
        rebuilt_import_ids.append,
    )
    with app_data_session() as db:
        db.add(AppSetting(key="catalog.pending_source_path", value=__file__))
        db.add(AppSetting(key="catalog.pending_source_sha256", value="a" * 64))
        db.commit()

    with TestClient(app) as client:
        response = client.post("/api/admin/catalog/rebuild")

    assert response.status_code == 202
    data = response.json()
    assert data["source"] == LOCAL_CATALOG_SOURCE_NAME
    assert data["status"] == "pending"
    assert data["source_sha256"] == "a" * 64
    assert rebuilt_import_ids == [data["id"]]


def test_catalog_rebuild_requires_local_source(
    app_data_session: sessionmaker[Session],
) -> None:
    _ = app_data_session

    with TestClient(app) as client:
        response = client.post("/api/admin/catalog/rebuild")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Local MTGJSON source file is not available. Update the catalog first."
    }


def test_user_data_status_reports_missing_database(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app_data_session
    monkeypatch.setattr("app.api.routes.admin.user_data_database_exists", lambda: False)

    with TestClient(app) as client:
        response = client.get("/api/admin/user-data")

    assert response.status_code == 200
    assert response.json() == {
        "exists": False,
        "file_size": None,
        "modified_at": None,
    }


def test_user_data_recreate_initializes_database(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = app_data_session
    database_path = tmp_path / "user_data.db"
    recreate_calls: list[None] = []

    def recreate() -> None:
        recreate_calls.append(None)
        database_path.write_bytes(b"user data")

    monkeypatch.setattr("app.api.routes.admin.recreate_user_data_db", recreate)
    monkeypatch.setattr("app.api.routes.admin.user_data_database_path", lambda: database_path)
    monkeypatch.setattr(
        "app.api.routes.admin.user_data_database_exists",
        database_path.is_file,
    )

    with TestClient(app) as client:
        response = client.post("/api/admin/user-data/recreate")

    assert response.status_code == 200
    assert response.json()["exists"] is True
    assert response.json()["file_size"] == len(b"user data")
    assert recreate_calls == [None]


def test_generate_test_collections_is_idempotent(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = app_data_session, USER_DATA_MODELS
    catalog_path = tmp_path / "catalog.db"
    _create_test_collection_catalog(catalog_path)
    monkeypatch.setattr(catalog.settings, "catalog_database_path", str(catalog_path))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserDataBase.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with testing_session() as db:
        db.add(Player(name="Player", is_default=True, created_at=1))
        db.add(CardCondition(code="NM", name="Near Mint", sort_order=1))
        db.commit()

    def override_get_user_data_db() -> Generator[Session]:
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_user_data_db] = override_get_user_data_db

    with TestClient(app) as client:
        first = client.post("/api/admin/test-collections/generate")
        second = client.post("/api/admin/test-collections/generate")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["collections"] == [
        {
            "id": 1,
            "name": "Test EN ALL unique printings 2010+",
            "language_code": "en",
            "rows": 2,
            "unique_scryfall_ids": 2,
            "total_quantity": 8,
        },
        {
            "id": 2,
            "name": "Test RU ALL localized printings 2010+",
            "language_code": "ru",
            "rows": 1,
            "unique_scryfall_ids": 1,
            "total_quantity": 4,
        },
    ]


def test_scryfall_symbols_status_and_update(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app_data_session
    statuses = [
        {"exists": False, "symbol_count": 0, "updated_at": None},
        {"exists": True, "symbol_count": 82, "updated_at": 1_780_275_600},
    ]
    monkeypatch.setattr("app.api.routes.admin.scryfall.get_symbols_status", lambda: statuses[0])
    monkeypatch.setattr("app.api.routes.admin.scryfall.update_symbols_cache", lambda: statuses[1])

    with TestClient(app) as client:
        before = client.get("/api/admin/scryfall-symbols")
        after = client.post("/api/admin/scryfall-symbols/update")

    assert before.status_code == 200
    assert before.json() == statuses[0]
    assert after.status_code == 200
    assert after.json() == statuses[1]


def test_scryfall_symbols_update_reports_download_failure(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app_data_session

    def fail_update() -> dict:
        raise OSError("Network unavailable")

    monkeypatch.setattr("app.api.routes.admin.scryfall.update_symbols_cache", fail_update)

    with TestClient(app) as client:
        response = client.post("/api/admin/scryfall-symbols/update")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Scryfall symbols cache update failed: Network unavailable"
    }


def test_delver_lens_mapping_status_and_update(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app_data_session
    statuses = [
        {
            "exists": False,
            "database_path": "data/delver_lens_mapping.db",
            "database_file_size": None,
            "database_modified_at": None,
            "row_count": None,
            "unique_scryfall_ids": None,
            "apk_exists": False,
            "apk_path": "data/import/delver-lens.apk",
            "apk_file_size": None,
            "apk_modified_at": None,
            "source_url": None,
            "apk_url": None,
            "source_app_version": None,
            "source_release_date": None,
            "source_db_member": None,
            "source_table": None,
            "updated_at": None,
            "last_error": None,
        },
        {
            "exists": True,
            "database_path": "data/delver_lens_mapping.db",
            "database_file_size": 6_430_720,
            "database_modified_at": 1_781_727_668,
            "row_count": 128_452,
            "unique_scryfall_ids": 115_642,
            "apk_exists": True,
            "apk_path": "data/import/delver-lens.apk",
            "apk_file_size": 240_153_906,
            "apk_modified_at": 1_781_727_666,
            "source_url": "https://www.delverlab.com/",
            "apk_url": "https://delver-public.s3.us-west-1.amazonaws.com/app-release.apk",
            "source_app_version": "6.98",
            "source_release_date": 1_781_308_800,
            "source_db_member": "res/Cc.db",
            "source_table": "cards",
            "updated_at": 1_781_727_668,
            "last_error": None,
        },
    ]
    force_download_values: list[bool] = []

    def update_mapping(*, force_download: bool) -> dict:
        force_download_values.append(force_download)
        return statuses[1]

    monkeypatch.setattr(
        "app.api.routes.admin.delver_lens_mapping.get_mapping_status",
        lambda: statuses[0],
    )
    monkeypatch.setattr(
        "app.api.routes.admin.delver_lens_mapping.update_mapping_database",
        update_mapping,
    )

    with TestClient(app) as client:
        before = client.get("/api/admin/delver-lens-mapping")
        after = client.post("/api/admin/delver-lens-mapping/update?force_download=true")

    assert before.status_code == 200
    assert before.json() == statuses[0]
    assert after.status_code == 200
    assert after.json() == statuses[1]
    assert force_download_values == [True]


def test_delver_lens_mapping_update_reports_extraction_failure(
    app_data_session: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app_data_session

    def fail_update(*, force_download: bool) -> dict:
        _ = force_download
        raise ValueError("No res/*.db file was found inside Delver Lens APK")

    monkeypatch.setattr(
        "app.api.routes.admin.delver_lens_mapping.update_mapping_database",
        fail_update,
    )

    with TestClient(app) as client:
        response = client.post("/api/admin/delver-lens-mapping/update")

    assert response.status_code == 502
    assert response.json() == {
        "detail": (
            "Delver Lens mapping update failed: "
            "No res/*.db file was found inside Delver Lens APK"
        )
    }
