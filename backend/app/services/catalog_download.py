import hashlib
import lzma
import shutil
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import sleep, time
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.app_data_session import AppDataSessionLocal
from app.models.app_data import AppSetting, CatalogImport
from app.services.catalog_import import import_catalog_source

ACTIVE_DOWNLOAD_STATUSES = ("pending", "downloading", "importing")
CATALOG_SOURCE_NAME = "MTGJSON AllPrintings.sqlite.xz"
HTTP_HEADERS = {"User-Agent": "MagicExplorer/0.1"}


def _set_setting(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting is None:
        db.add(AppSetting(key=key, value=value))
        return
    setting.value = value


def _download_file(url: str, destination: Path) -> int | None:
    request = Request(url, headers=HTTP_HEADERS)
    with urlopen(request) as response, destination.open("wb") as target:  # noqa: S310
        shutil.copyfileobj(response, target)
        last_modified = response.headers.get("Last-Modified")

    if last_modified is None:
        return None

    parsed = parsedate_to_datetime(last_modified)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _download_checksum(url: str) -> str:
    request = Request(url, headers=HTTP_HEADERS)
    with urlopen(request) as response:  # noqa: S310
        checksum = response.read().decode("ascii").strip().split()[0]

    if len(checksum) != 64:
        raise ValueError("MTGJSON checksum response is invalid")
    return checksum.lower()


def _calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decompress_xz(source: Path, destination: Path) -> None:
    with lzma.open(source, "rb") as compressed, destination.open("wb") as extracted:
        shutil.copyfileobj(compressed, extracted)


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(60):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if attempt == 59:
                raise
            sleep(0.5)


def _versioned_source_path(source_path: str, catalog_import_id: int) -> Path:
    base_path = Path(source_path)
    return base_path.with_name(f"{base_path.stem}.{catalog_import_id}{base_path.suffix}")


def _remove_previous_sources(base_path: Path, current_path: Path) -> None:
    for candidate in base_path.parent.glob(f"{base_path.stem}.*{base_path.suffix}"):
        if candidate != current_path:
            try:
                candidate.unlink()
            except OSError:
                # A previous source may still be open in an external SQLite viewer.
                pass


def download_catalog_source(
    catalog_import_id: int,
    *,
    session_factory: sessionmaker[Session] = AppDataSessionLocal,
    source_url: str = settings.catalog_source_url,
    source_path: str = settings.catalog_source_path,
) -> None:
    base_path = Path(source_path)
    destination = _versioned_source_path(source_path, catalog_import_id)
    compressed_part = destination.with_suffix(destination.suffix + ".xz.part")
    extracted_part = destination.with_suffix(destination.suffix + ".part")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        compressed_part.unlink(missing_ok=True)
        extracted_part.unlink(missing_ok=True)

        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is None:
                raise ValueError("Catalog import record does not exist")
            catalog_import.status = "downloading"
            db.commit()

        source_updated_at = _download_file(source_url, compressed_part)
        expected_sha256 = _download_checksum(f"{source_url}.sha256")
        actual_sha256 = _calculate_sha256(compressed_part)
        if actual_sha256 != expected_sha256:
            raise ValueError("Downloaded MTGJSON checksum does not match")

        _decompress_xz(compressed_part, extracted_part)
        _replace_with_retry(extracted_part, destination)

        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is None:
                raise ValueError("Catalog import record does not exist")
            catalog_import.source_updated_at = source_updated_at
            catalog_import.finished_at = int(time())
            catalog_import.status = "downloaded"
            catalog_import.source_file_size = destination.stat().st_size
            catalog_import.source_sha256 = actual_sha256
            _set_setting(db, "catalog.pending_source_path", str(destination))
            _set_setting(db, "catalog.pending_source_sha256", actual_sha256)
            db.commit()
        import_catalog_source(
            catalog_import_id,
            session_factory=session_factory,
            source_path=str(destination),
        )
        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is not None and catalog_import.status == "completed":
                _remove_previous_sources(base_path, destination)
    except Exception as error:
        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is not None:
                catalog_import.finished_at = int(time())
                catalog_import.status = "failed"
                catalog_import.error_message = str(error)
                db.commit()
    finally:
        compressed_part.unlink(missing_ok=True)
        extracted_part.unlink(missing_ok=True)
