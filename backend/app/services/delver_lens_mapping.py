import os
import re
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from collections.abc import Iterable
from pathlib import Path
from time import sleep, time
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.app_data_session import AppDataSessionLocal
from app.models.app_data import AppSetting

DELVER_LAB_URL = "https://www.delverlab.com/"
APK_LINK_TEXT = "APK (Combined ABI)"
HTTP_HEADERS = {"User-Agent": "MagicVibe/0.1"}
SETTING_PREFIX = "delver_lens_mapping."

_update_lock = threading.Lock()


def _data_root() -> Path:
    catalog_path = Path(settings.catalog_database_path)
    return catalog_path.parent


def _import_root() -> Path:
    path = _data_root() / "import"
    path.mkdir(parents=True, exist_ok=True)
    return path


def apk_path() -> Path:
    return _import_root() / "delver-lens.apk"


def mapping_database_path() -> Path:
    return _data_root() / "delver_lens_mapping.db"


def _setting_key(name: str) -> str:
    return SETTING_PREFIX + name


def _read_settings(session_factory: sessionmaker[Session]) -> dict[str, str | None]:
    with session_factory() as db:
        rows = db.scalars(select(AppSetting).where(AppSetting.key.startswith(SETTING_PREFIX))).all()
        return {row.key.removeprefix(SETTING_PREFIX): row.value for row in rows}


def _write_settings(values: dict[str, object], session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        for name, value in values.items():
            setting = db.get(AppSetting, _setting_key(name))
            text_value = None if value is None else str(value)
            if setting is None:
                db.add(AppSetting(key=_setting_key(name), value=text_value))
                continue
            setting.value = text_value
        db.commit()


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _download_bytes(url: str, *, timeout_seconds: int = 60) -> tuple[bytes, str | None]:
    request = Request(url, headers=HTTP_HEADERS)
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read(), response.headers.get("Last-Modified")


def _download_file(url: str, destination: Path) -> tuple[int, str | None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers=HTTP_HEADERS)
    try:
        with urlopen(request, timeout=120) as response, temporary_path.open("wb") as target:  # noqa: S310
            shutil.copyfileobj(response, target)
            last_modified = response.headers.get("Last-Modified")
        _replace_with_retry(temporary_path, destination)
        return destination.stat().st_size, last_modified
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def _latest_source_metadata() -> tuple[str | None, int | None]:
    html_bytes, _ = _download_bytes(DELVER_LAB_URL, timeout_seconds=2)
    html = html_bytes.decode("utf-8", errors="replace")
    return _parse_latest_changelog_entry(html)


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(60):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 59:
                raise
            sleep(0.5)


def _find_apk_link(html: str) -> str:
    link_pattern = re.compile(
        r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in link_pattern.finditer(html):
        label = re.sub(r"<[^>]+>", " ", match.group("label"))
        label = " ".join(label.split())
        if label == APK_LINK_TEXT:
            return urljoin(DELVER_LAB_URL, match.group("href"))
    raise ValueError(f"Could not find {APK_LINK_TEXT!r} link on Delver Lab")


def _parse_latest_changelog_entry(html: str) -> tuple[str | None, int | None]:
    version_match = re.search(r"Version\s+([0-9][0-9. -]*)", html, re.IGNORECASE)
    release_date = None
    if version_match is not None:
        date_match = re.search(
            r"Version\s+[0-9][0-9. -]*.*?(\d{4})/(\d{2})/(\d{2})",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if date_match is not None:
            from datetime import UTC, datetime

            release_date = int(
                datetime(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3)),
                    tzinfo=UTC,
                ).timestamp()
            )
    return (version_match.group(1).strip() if version_match else None), release_date


def _source_db_members(apk: zipfile.ZipFile) -> list[str]:
    return sorted(
        info.filename
        for info in apk.infolist()
        if not info.is_dir()
        and info.filename.startswith("res/")
        and info.filename.lower().endswith(".db")
    )


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _candidate_tables(connection: sqlite3.Connection) -> Iterable[tuple[str, str, str]]:
    rows = connection.execute(
        """
        select name
        from sqlite_master
        where type = 'table'
            and name not like 'sqlite_%'
        order by name
        """
    ).fetchall()
    for (table_name,) in rows:
        columns = {
            row[1].lower(): row[1]
            for row in connection.execute(f"pragma table_info({_quoted_identifier(table_name)})")
        }
        id_column = columns.get("_id")
        scryfall_column = columns.get("scryfall_id") or columns.get("scryfallid")
        if id_column and scryfall_column:
            yield table_name, id_column, scryfall_column


def _scryfall_blob(value: object) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        if len(value) == 16:
            return value
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return uuid.UUID(text).bytes
    except ValueError:
        try:
            raw = bytes.fromhex(text)
        except ValueError:
            return None
        return raw if len(raw) == 16 else None


def _extract_mapping_from_source_db(source_db_path: Path) -> tuple[str, int, int]:
    source = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    try:
        source.row_factory = sqlite3.Row
        for table_name, id_column, scryfall_column in _candidate_tables(source):
            rows = source.execute(
                f"""
                select {_quoted_identifier(id_column)} as source_id,
                    {_quoted_identifier(scryfall_column)} as scryfall_id
                from {_quoted_identifier(table_name)}
                where {_quoted_identifier(scryfall_column)} is not null
                    and {_quoted_identifier(scryfall_column)} != ''
                """
            ).fetchall()
            mappings: dict[int, bytes] = {}
            for row in rows:
                try:
                    source_id = int(row["source_id"])
                except (TypeError, ValueError):
                    continue
                scryfall_id = _scryfall_blob(row["scryfall_id"])
                if scryfall_id is not None:
                    mappings[source_id] = scryfall_id
            if mappings:
                return table_name, len(rows), _write_mapping_database(mappings.items())
    finally:
        source.close()
    raise ValueError("No table with usable _id and scryfall_id columns was found in APK database")


def _write_mapping_database(rows: Iterable[tuple[int, bytes]]) -> int:
    destination = mapping_database_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(".db.tmp")
    temporary_path.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary_path)
    try:
        connection.execute(
            """
            create table cards (
                _id integer primary key,
                scryfall_id blob not null check(length(scryfall_id) = 16)
            )
            """
        )
        row_count = 0
        for source_id, scryfall_id in rows:
            connection.execute(
                "insert or replace into cards (_id, scryfall_id) values (?, ?)",
                (source_id, scryfall_id),
            )
            row_count += 1
        connection.execute("create index idx_cards_scryfall_id on cards (scryfall_id)")
        connection.commit()
    except Exception:
        connection.close()
        temporary_path.unlink(missing_ok=True)
        raise
    else:
        connection.close()
        os.replace(temporary_path, destination)
        return row_count


def get_mapping_status(session_factory: sessionmaker[Session] = AppDataSessionLocal) -> dict:
    stored_settings = _read_settings(session_factory)
    database_path = mapping_database_path()
    apk = apk_path()
    row_count = None
    unique_scryfall_ids = None
    if database_path.is_file():
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "select count(*) as rows, count(distinct scryfall_id) as unique_ids from cards"
            ).fetchone()
            row_count = row[0]
            unique_scryfall_ids = row[1]
        finally:
            connection.close()

    latest_source_app_version = None
    latest_source_release_date = None
    source_status_error = None
    try:
        latest_source_app_version, latest_source_release_date = _latest_source_metadata()
    except (OSError, ValueError) as error:
        source_status_error = str(error)

    installed_source_release_date = _optional_int(stored_settings.get("source_release_date"))
    if not database_path.is_file():
        source_status = "not_installed"
    elif latest_source_release_date is None or installed_source_release_date is None:
        source_status = "unknown"
    elif installed_source_release_date < latest_source_release_date:
        source_status = "outdated"
    else:
        source_status = "current"

    return {
        "exists": database_path.is_file(),
        "database_path": str(database_path),
        "database_file_size": database_path.stat().st_size if database_path.is_file() else None,
        "database_modified_at": int(database_path.stat().st_mtime) if database_path.is_file() else None,
        "row_count": row_count,
        "unique_scryfall_ids": unique_scryfall_ids,
        "apk_exists": apk.is_file(),
        "apk_path": str(apk),
        "apk_file_size": apk.stat().st_size if apk.is_file() else None,
        "apk_modified_at": int(apk.stat().st_mtime) if apk.is_file() else None,
        "source_url": stored_settings.get("source_url"),
        "apk_url": stored_settings.get("apk_url"),
        "source_app_version": stored_settings.get("source_app_version"),
        "source_release_date": installed_source_release_date,
        "latest_source_app_version": latest_source_app_version,
        "latest_source_release_date": latest_source_release_date,
        "source_status": source_status,
        "source_status_error": source_status_error,
        "source_db_member": stored_settings.get("source_db_member"),
        "source_table": stored_settings.get("source_table"),
        "updated_at": _optional_int(stored_settings.get("updated_at")),
        "last_error": stored_settings.get("last_error"),
    }


def update_mapping_database(
    *,
    force_download: bool,
    session_factory: sessionmaker[Session] = AppDataSessionLocal,
) -> dict:
    if not _update_lock.acquire(blocking=False):
        raise RuntimeError("Delver Lens mapping update is already running")
    try:
        stored_settings = _read_settings(session_factory)
        source_app_version = stored_settings.get("source_app_version")
        source_release_date = _optional_int(stored_settings.get("source_release_date"))
        apk_url = stored_settings.get("apk_url") or ""
        apk_last_modified = None

        if force_download or not apk_path().is_file():
            html_bytes, _ = _download_bytes(DELVER_LAB_URL)
            html = html_bytes.decode("utf-8", errors="replace")
            apk_url = _find_apk_link(html)
            source_app_version, source_release_date = _parse_latest_changelog_entry(html)
            apk_size, apk_last_modified = _download_file(apk_url, apk_path())
        else:
            apk_size = apk_path().stat().st_size

        with zipfile.ZipFile(apk_path()) as apk:
            members = _source_db_members(apk)
            if not members:
                raise ValueError("No res/*.db file was found inside Delver Lens APK")
            with tempfile.TemporaryDirectory(
                prefix="magic-vibe-delver-",
                dir=_import_root(),
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                last_error: Exception | None = None
                for member in members:
                    source_db_path = temporary_root / Path(member).name
                    with apk.open(member) as source, source_db_path.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    try:
                        table_name, scanned_rows, mapped_rows = _extract_mapping_from_source_db(source_db_path)
                    except (sqlite3.DatabaseError, ValueError) as error:
                        last_error = error
                        continue

                    _write_settings(
                        {
                            "source_url": DELVER_LAB_URL,
                            "apk_url": apk_url,
                            "apk_last_modified": apk_last_modified,
                            "apk_file_size": apk_size,
                            "source_app_version": source_app_version,
                            "source_release_date": source_release_date,
                            "source_db_member": member,
                            "source_table": table_name,
                            "source_rows_scanned": scanned_rows,
                            "mapped_rows": mapped_rows,
                            "updated_at": int(time()),
                            "last_error": None,
                        },
                        session_factory,
                    )
                    return get_mapping_status(session_factory)
                if last_error is not None:
                    raise ValueError(str(last_error)) from last_error
                raise ValueError("No usable mapping table was found inside Delver Lens APK")
    except Exception as error:
        _write_settings(
            {
                "last_error": str(error),
                "updated_at": int(time()),
            },
            session_factory,
        )
        raise
    finally:
        _update_lock.release()
