from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.app_data_base import AppDataBase
from app.db.app_data_session import get_app_data_db
from app.main import app
from app.models.app_data import APP_DATA_MODELS, AppSetting, CatalogImport
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
