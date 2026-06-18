import hashlib
import lzma
import shutil
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.db.app_data_base import AppDataBase
from app.models.app_data import APP_DATA_MODELS, AppSetting, CatalogImport
from app.services import catalog_download
from app.services.catalog_source_index import _find_source_file_timestamp


@pytest.fixture()
def workspace_tmp_path() -> Generator[Path]:
    path = Path(".test-data") / uuid4().hex
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path)


def _create_session_factory(database_path: Path) -> sessionmaker[Session]:
    _ = APP_DATA_MODELS
    engine = create_engine(f"sqlite:///{database_path}", poolclass=NullPool)
    AppDataBase.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed_catalog_import(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as db:
        catalog_import = CatalogImport(
            source=catalog_download.CATALOG_SOURCE_NAME,
            started_at=1_780_362_000,
            status="pending",
        )
        db.add(catalog_import)
        db.commit()
        db.refresh(catalog_import)
        return catalog_import.id


def test_catalog_source_index_parses_all_printings_sqlite_xz_timestamp() -> None:
    html = """
    <html><body>
    <a href="AllPrintings.sqlite.xz">AllPrintings.sqlite.xz</a> 117.3 MiB 2026-Jun-18 02:10
    <a href="AllPrintings.sqlite.xz.sha256">AllPrintings.sqlite.xz.sha256</a> 64 B 2026-Jun-18 02:10
    </body></html>
    """

    assert (
        _find_source_file_timestamp(html, "https://mtgjson.com/api/v5/AllPrintings.sqlite.xz")
        == 1_781_748_600
    )


def test_catalog_download_verifies_and_extracts_source(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = workspace_tmp_path
    session_factory = _create_session_factory(tmp_path / "app_data.db")
    catalog_import_id = _seed_catalog_import(session_factory)
    source_contents = b"SQLite format 3\x00test catalog"
    compressed_source = tmp_path / "source.sqlite.xz"
    compressed_source.write_bytes(lzma.compress(source_contents))
    source_sha256 = hashlib.sha256(compressed_source.read_bytes()).hexdigest()

    def copy_source(_: str, destination: Path) -> int:
        shutil.copyfile(compressed_source, destination)
        return 1_780_272_000

    monkeypatch.setattr(catalog_download, "_download_file", copy_source)
    monkeypatch.setattr(catalog_download, "_download_checksum", lambda _: source_sha256)
    monkeypatch.setattr(
        catalog_download,
        "get_catalog_source_index_updated_at",
        lambda _: 1_781_868_600,
    )
    def complete_import(*_: object, **__: object) -> None:
        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            assert catalog_import is not None
            catalog_import.status = "completed"
            db.commit()

    monkeypatch.setattr(catalog_download, "import_catalog_source", complete_import)
    base_destination = tmp_path / "import" / "AllPrintings.sqlite"
    previous_destination = tmp_path / "import" / "AllPrintings.0.sqlite"
    previous_destination.parent.mkdir(parents=True)
    previous_destination.write_bytes(b"old source")
    destination = tmp_path / "import" / f"AllPrintings.{catalog_import_id}.sqlite"

    catalog_download.download_catalog_source(
        catalog_import_id,
        session_factory=session_factory,
        source_url="https://example.test/AllPrintings.sqlite.xz",
        source_path=str(base_destination),
    )

    with session_factory() as db:
        catalog_import = db.get(CatalogImport, catalog_import_id)
        pending_source_path = db.get(AppSetting, "catalog.pending_source_path")
        pending_source_sha256 = db.get(AppSetting, "catalog.pending_source_sha256")
        source_index_updated_at = db.get(AppSetting, "catalog.source_index_updated_at")

    assert destination.read_bytes() == source_contents
    assert catalog_import is not None
    assert catalog_import.status == "completed"
    assert catalog_import.source_updated_at == 1_780_272_000
    assert catalog_import.source_sha256 == source_sha256
    assert catalog_import.source_file_size == len(source_contents)
    assert pending_source_path is not None
    assert pending_source_path.value == str(destination)
    assert pending_source_sha256 is not None
    assert pending_source_sha256.value == source_sha256
    assert source_index_updated_at is not None
    assert source_index_updated_at.value == "1781868600"
    assert not previous_destination.exists()


def test_catalog_download_keeps_previous_source_when_checksum_fails(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = workspace_tmp_path
    session_factory = _create_session_factory(tmp_path / "app_data.db")
    catalog_import_id = _seed_catalog_import(session_factory)
    compressed_source = tmp_path / "source.sqlite.xz"
    compressed_source.write_bytes(lzma.compress(b"replacement catalog"))

    def copy_source(_: str, destination: Path) -> int:
        shutil.copyfile(compressed_source, destination)
        return 1_780_272_000

    monkeypatch.setattr(catalog_download, "_download_file", copy_source)
    monkeypatch.setattr(catalog_download, "_download_checksum", lambda _: "0" * 64)
    monkeypatch.setattr(
        catalog_download,
        "get_catalog_source_index_updated_at",
        lambda _: 1_781_868_600,
    )
    destination = tmp_path / "import" / "AllPrintings.sqlite"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"existing catalog")

    catalog_download.download_catalog_source(
        catalog_import_id,
        session_factory=session_factory,
        source_url="https://example.test/AllPrintings.sqlite.xz",
        source_path=str(destination),
    )

    with session_factory() as db:
        catalog_import = db.get(CatalogImport, catalog_import_id)

    assert destination.read_bytes() == b"existing catalog"
    assert catalog_import is not None
    assert catalog_import.status == "failed"
    assert catalog_import.error_message == "Downloaded MTGJSON checksum does not match"


def test_replace_with_retry_handles_temporary_windows_file_lock(
    workspace_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = workspace_tmp_path / "source.part"
    destination = workspace_tmp_path / "source.sqlite"
    source.write_bytes(b"catalog")
    original_replace = Path.replace
    attempts = 0

    def replace_with_temporary_lock(path: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(32, "file is temporarily locked")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace_with_temporary_lock)
    monkeypatch.setattr(catalog_download, "sleep", lambda _: None)

    catalog_download._replace_with_retry(source, destination)

    assert attempts == 3
    assert destination.read_bytes() == b"catalog"
