from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import time
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user_data import Collection, CollectionItem, Deck, DeckItem, Player, WishDeckItem
from app.services.delver_lens_mapping import mapping_database_path

ImportTargetType = Literal["collection", "wishlist", "deck", "wishdeck"]
TargetCollectionMode = Literal["new", "existing", "import"]
MergeSection = Literal["keep", "main", "side", "maybe", "commander"]

LANGUAGE_MAP = {
    "": "en",
    "English": "en",
    "Chinese Traditional": "zht",
    "Chinese Simplified": "zhs",
    "German": "de",
    "French": "fr",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Portuguese": "pt",
    "Russian": "ru",
    "Spanish": "es",
}

CONDITION_MAP = {
    "": "NM",
    "Near Mint": "NM",
    "Slightly Played": "SP",
    "Moderately Played": "MP",
    "Heavily Played": "HP",
}

FINISH_NAMES = {
    0: "nonfoil",
    1: "foil",
    2: "etched",
    3: "signed",
}

TARGET_LABELS = {
    "collection": "Collection",
    "wishlist": "Wishlist",
    "deck": "Deck",
    "wishdeck": "Wish deck",
}

NON_BLOCKING_CARD_ERROR_PREFIXES = ("Delver card id ",)
NON_BLOCKING_CARD_ERROR_FRAGMENTS = (
    " is not mapped",
    " does not resolve to catalog",
)

REQUIRED_LIST_COLUMNS = {"_id", "background", "category", "name", "creation", "tab", "uuid", "note"}
REQUIRED_CARD_COLUMNS = {
    "_id",
    "card",
    "foil",
    "quantity",
    "creation",
    "list",
    "note",
    "condition",
    "language",
    "tab",
    "general",
}


class DelverLensImportError(ValueError):
    pass


def _now() -> int:
    return int(time())


def _import_sessions_root() -> Path:
    path = Path(settings.catalog_database_path).parent / "import" / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_database_path(session_id: str) -> Path:
    if not session_id or any(char not in "0123456789abcdef-" for char in session_id.lower()):
        raise DelverLensImportError("Import session id is invalid")
    return _import_sessions_root() / f"{session_id}.db"


def cleanup_old_import_sessions(max_age_seconds: int = 24 * 60 * 60) -> None:
    cutoff = time() - max_age_seconds
    root = _import_sessions_root()
    for path in root.glob("*.db"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def delete_import_session(session_id: str) -> None:
    _session_database_path(session_id).unlink(missing_ok=True)


def _uuid_text(value: bytes | None) -> str | None:
    return str(UUID(bytes=value)) if value is not None else None


def _unix_seconds(milliseconds: object) -> int:
    try:
        return max(0, int(int(milliseconds) / 1000))
    except (TypeError, ValueError):
        return 0


def _catalog_database_path() -> Path:
    return Path(settings.catalog_database_path)


def _connect_dlens(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.DatabaseError as error:
        raise DelverLensImportError("Selected file is not a readable Delver Lens database") from error


def _attach_database(connection: sqlite3.Connection, alias: str, path: Path) -> None:
    if not path.is_file():
        raise DelverLensImportError(f"Required database is missing: {path}")
    escaped = str(path).replace("'", "''")
    try:
        connection.execute(f"attach database '{escaped}' as {alias}")
    except sqlite3.DatabaseError as error:
        raise DelverLensImportError(f"Could not attach required database: {path}") from error


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = connection.execute(f'pragma table_info("{table}")').fetchall()
    except sqlite3.DatabaseError as error:
        raise DelverLensImportError("Selected file is not a valid Delver Lens export") from error
    return {row["name"] for row in rows}


def _validate_dlens_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in connection.execute(
            """
            select name
            from sqlite_master
            where type = 'table'
            """
        )
    }
    if "lists" not in tables or "cards" not in tables:
        raise DelverLensImportError("Selected file does not contain Delver Lens lists/cards")

    missing_lists = REQUIRED_LIST_COLUMNS - _table_columns(connection, "lists")
    missing_cards = REQUIRED_CARD_COLUMNS - _table_columns(connection, "cards")
    if missing_lists or missing_cards:
        missing = sorted(missing_lists | missing_cards)
        raise DelverLensImportError(f"Selected file is missing required columns: {', '.join(missing)}")


def _preferred_player_id(db: Session) -> int:
    player_id = db.scalar(select(Player.id).where(Player.is_default.is_(True)))
    if player_id is None:
        raise DelverLensImportError("Preferred player is required before importing")
    return player_id


def _target_type_for_category(category: int) -> ImportTargetType:
    if category == 2:
        return "deck"
    if category == 3:
        return "wishlist"
    return "collection"


def _section_for_card(row: sqlite3.Row) -> str:
    if int(row["general"] or 0) == 1:
        return "commander"
    tab = int(row["tab"] or 0)
    if tab == 1:
        return "side"
    if tab == 2:
        return "maybe"
    return "main"


def _legal_languages(connection: sqlite3.Connection, printing_id: int, printing_language: str) -> list[dict]:
    rows = connection.execute(
        """
        select distinct language_code
        from (
            select p.language_code
            from catalog.card_printings as p
            where p.id = ?
            union all
            select l.language_code
            from catalog.card_printing_faces as f
            join catalog.card_face_localizations as l on l.face_id = f.id
            where f.printing_id = ?
        )
        """,
        (printing_id, printing_id),
    ).fetchall()
    codes = [row["language_code"] for row in rows]
    codes.sort(key=lambda code: (0 if code == printing_language else 1, code))
    return [
        {
            "code": code,
            "name": _language_name(connection, code) or code,
        }
        for code in codes
    ]


def _language_name(connection: sqlite3.Connection, code: str) -> str | None:
    row = connection.execute(
        "select name from catalog.languages where code = ?",
        (code,),
    ).fetchone()
    return row["name"] if row is not None else None


def _legal_finishes(connection: sqlite3.Connection, printing_id: int) -> list[dict]:
    return [
        {"id": row["id"], "name": row["name"]}
        for row in connection.execute(
            """
            select f.id, f.name
            from catalog.card_printing_finishes as cpf
            join catalog.finishes as f on f.id = cpf.finish_id
            where cpf.printing_id = ?
            order by f.id
            """,
            (printing_id,),
        ).fetchall()
    ]


def _normalize_language(
    connection: sqlite3.Connection,
    *,
    printing_id: int,
    printing_language: str,
    delver_language: str,
    card_name: str,
) -> tuple[str | None, str | None, dict | None, list[str]]:
    errors: list[str] = []
    requested_code = LANGUAGE_MAP.get(delver_language)
    if requested_code is None:
        return None, None, None, [f"Unknown Delver language: {delver_language}"]

    requested_name = _language_name(connection, requested_code) or requested_code
    legal = _legal_languages(connection, printing_id, printing_language)
    legal_codes = [language["code"] for language in legal]
    selected_code = requested_code
    selected_name = requested_name
    reason = None
    if requested_code not in legal_codes:
        if "en" in legal_codes:
            selected_code = "en"
        elif legal_codes:
            selected_code = legal_codes[0]
        else:
            return requested_code, requested_name, None, [
                f"No legal language is available for {card_name}"
            ]
        selected_name = _language_name(connection, selected_code) or selected_code
        reason = "Selected printing does not support requested language"

    change = None
    if selected_code != requested_code:
        change = {
            "attribute": "language",
            "before_code": requested_code,
            "before": requested_name,
            "after_code": selected_code,
            "after": selected_name,
            "reason": reason,
        }
    return requested_code, requested_name, change, errors


def _normalize_finish(
    connection: sqlite3.Connection,
    *,
    printing_id: int,
    delver_foil: int,
    card_name: str,
) -> tuple[int | None, str | None, int | None, str | None, dict | None, list[str]]:
    requested_id = 1 if int(delver_foil or 0) == 1 else 0
    requested_name = FINISH_NAMES.get(requested_id, str(requested_id))
    legal = _legal_finishes(connection, printing_id)
    legal_ids = [finish["id"] for finish in legal]
    if requested_id in legal_ids:
        return requested_id, requested_name, requested_id, requested_name, None, []
    if 0 in legal_ids:
        selected_id = 0
    elif legal_ids:
        selected_id = legal_ids[0]
    else:
        return requested_id, requested_name, None, None, None, [
            f"No legal finish is available for {card_name}"
        ]
    selected_name = FINISH_NAMES.get(selected_id) or next(
        (finish["name"] for finish in legal if finish["id"] == selected_id),
        str(selected_id),
    )
    return (
        requested_id,
        requested_name,
        selected_id,
        selected_name,
        {
            "attribute": "finish",
            "before_code": requested_id,
            "before": requested_name,
            "after_code": selected_id,
            "after": selected_name,
            "reason": "Selected printing does not support requested finish",
        },
        [],
    )


def _card_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        select
            c._id as source_card_id,
            c.card as delver_card_id,
            c.foil,
            c.quantity,
            c.creation,
            c.list as source_list_id,
            c.condition,
            c.language as delver_language,
            c.tab,
            c.general,
            m.scryfall_id as mapped_scryfall_id,
            p.id as printing_id,
            p.oracle_id,
            p.set_code,
            p.collector_number,
            p.language_code as printing_language_code,
            p.name,
            f.mana_cost,
            f.type
        from cards as c
        left join mapping.cards as m on m._id = c.card
        left join catalog.card_printings as p on p.scryfall_id = m.scryfall_id
        left join catalog.sets as s on s.code = p.set_code
        left join catalog.card_printing_faces as f
            on f.printing_id = p.id
            and f.face_order = (
                select min(face_order)
                from catalog.card_printing_faces
                where printing_id = p.id
            )
        order by c.list, c.tab, c._id
        """
    ).fetchall()


def _build_card_preview(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    errors: list[str] = []
    changes: list[dict] = []
    warnings: list[str] = []
    condition_code = CONDITION_MAP.get(row["condition"])
    if condition_code is None:
        errors.append(f"Unknown Delver condition: {row['condition']}")

    if row["mapped_scryfall_id"] is None:
        errors.append(f"Delver card id {row['delver_card_id']} is not mapped")
    if row["printing_id"] is None:
        errors.append(f"Delver card id {row['delver_card_id']} does not resolve to catalog")

    requested_language_code = None
    requested_language = None
    language_code = None
    language = None
    finish_id = None
    finish = None

    if row["printing_id"] is not None:
        requested_language_code, requested_language, language_change, language_errors = _normalize_language(
            connection,
            printing_id=row["printing_id"],
            printing_language=row["printing_language_code"],
            delver_language=row["delver_language"],
            card_name=row["name"],
        )
        errors.extend(language_errors)
        language_code = (
            language_change["after_code"] if language_change is not None else requested_language_code
        )
        language = language_change["after"] if language_change is not None else requested_language
        if language_change is not None:
            changes.append(language_change)
            warnings.append(language_change["reason"])

        (
            _requested_finish_id,
            _requested_finish,
            finish_id,
            finish,
            finish_change,
            finish_errors,
        ) = _normalize_finish(
            connection,
            printing_id=row["printing_id"],
            delver_foil=row["foil"],
            card_name=row["name"],
        )
        errors.extend(finish_errors)
        if finish_change is not None:
            changes.append(finish_change)
            warnings.append(finish_change["reason"])

    quantity = int(row["quantity"] or 0)
    if quantity < 1:
        errors.append("Quantity must be greater than zero")

    return {
        "source_card_id": row["source_card_id"],
        "source_list_id": row["source_list_id"],
        "delver_card_id": row["delver_card_id"],
        "printing_id": row["printing_id"],
        "scryfall_id": _uuid_text(row["mapped_scryfall_id"]),
        "oracle_id": _uuid_text(row["oracle_id"]),
        "name": row["name"] or f"Delver card {row['delver_card_id']}",
        "set_code": row["set_code"],
        "collector_number": row["collector_number"],
        "mana_cost": row["mana_cost"] or "",
        "type": row["type"] or "",
        "quantity": quantity,
        "section": _section_for_card(row),
        "condition_code": condition_code,
        "language_code": language_code,
        "language": language,
        "finish_id": finish_id,
        "finish": finish,
        "attribute_changes": changes,
        "warnings": sorted(set(warnings)),
        "errors": errors,
    }


def _metadata(connection: sqlite3.Connection) -> dict:
    if "delverlens" not in {
        row["name"]
        for row in connection.execute("select name from sqlite_master where type = 'table'")
    }:
        return {"version": None, "timestamp": None}
    rows = connection.execute("select key, value from delverlens").fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return {"version": values.get("version"), "timestamp": values.get("timestamp")}


def _parse_preview(path: Path, db: Session) -> dict:
    preferred_player_id = _preferred_player_id(db)
    mapping_path = mapping_database_path()
    catalog_path = _catalog_database_path()

    connection = _connect_dlens(path)
    try:
        _validate_dlens_schema(connection)
        _attach_database(connection, "mapping", mapping_path)
        _attach_database(connection, "catalog", catalog_path)

        cards_by_list: dict[int, list[dict]] = {}
        for row in _card_rows(connection):
            card = _build_card_preview(connection, row)
            cards_by_list.setdefault(card["source_list_id"], []).append(card)

        entities: list[dict] = []
        for row in connection.execute("select * from lists order by _id").fetchall():
            category = int(row["category"] or 0)
            target_type = _target_type_for_category(category)
            cards = cards_by_list.get(row["_id"], [])
            errors = [error for card in cards for error in card["errors"]]
            warnings = [warning for card in cards for warning in card["warnings"]]
            attribute_changes = [
                {
                    **change,
                    "source_card_id": card["source_card_id"],
                    "source_list_id": row["_id"],
                    "container_name": row["name"],
                    "card_name": card["name"],
                    "quantity": card["quantity"],
                }
                for card in cards
                for change in card["attribute_changes"]
            ]
            attribute_change_reasons = {
                change["reason"] for change in attribute_changes if change.get("reason")
            }
            plain_warnings = [warning for warning in set(warnings) if warning not in attribute_change_reasons]
            entities.append(
                {
                    "source_list_id": row["_id"],
                    "source_category": category,
                    "source_category_label": _source_category_label(category),
                    "target_type": target_type,
                    "target_type_label": TARGET_LABELS[target_type],
                    "name": row["name"] or f"Delver list {row['_id']}",
                    "note": row["note"] or None,
                    "player_id": preferred_player_id,
                    "created_at": _unix_seconds(row["creation"]),
                    "source_background": row["background"],
                    "source_tab": row["tab"],
                    "source_uuid": row["uuid"] or None,
                    "target_collection_mode": _default_target_collection_mode(target_type),
                    "target_collection_id": None,
                    "target_import_list_id": None,
                    "card_count": len(cards),
                    "total_quantity": sum(card["quantity"] for card in cards),
                    "mapped_count": sum(1 for card in cards if card["scryfall_id"] is not None),
                    "error_count": len(errors),
                    "warning_count": len(attribute_changes) + len(plain_warnings),
                    "errors": errors,
                    "warnings": sorted(set(warnings)),
                    "attribute_changes": attribute_changes,
                    "cards": cards,
                }
            )

        return {
            "source": {
                "kind": "delver-lens-dlens",
                **_metadata(connection),
            },
            "default_player_id": preferred_player_id,
            "entities": entities,
        }
    finally:
        connection.close()


def _source_category_label(category: int) -> str:
    if category == 1:
        return "Delver list"
    if category == 2:
        return "Delver deck"
    if category == 3:
        return "Delver wishlist"
    return f"Delver category {category}"


def _default_target_collection_mode(target_type: ImportTargetType) -> TargetCollectionMode | None:
    if target_type in {"collection", "wishlist"}:
        return "new"
    return None


def create_delver_lens_import_session(path: Path, filename: str, db: Session) -> dict:
    cleanup_old_import_sessions()
    parsed = _parse_preview(path, db)
    session_id = uuid4().hex
    session_path = _session_database_path(session_id)
    connection = sqlite3.connect(session_path)
    try:
        connection.row_factory = sqlite3.Row
        _init_staging_database(connection)
        now = _now()
        source = parsed["source"]
        connection.execute(
            """
            insert into import_session (
                id, kind, source_filename, status, source_version, source_timestamp,
                default_player_id, created_at, updated_at, completed_at
            )
            values (?, ?, ?, 'draft', ?, ?, ?, ?, ?, null)
            """,
            (
                session_id,
                source["kind"],
                filename,
                source.get("version"),
                source.get("timestamp"),
                parsed["default_player_id"],
                now,
                now,
            ),
        )
        for entity in parsed["entities"]:
            _insert_staging_entity(connection, entity)
            for card in entity["cards"]:
                _insert_staging_item(connection, entity["source_list_id"], card)
        connection.commit()
    except Exception:
        connection.rollback()
        session_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    return get_import_session_preview(session_id, db)


def get_import_session_preview(session_id: str, db: Session) -> dict:
    _ = db
    connection = _connect_staging_session(session_id)
    try:
        return _staging_preview(connection)
    finally:
        connection.close()


def update_import_session_entity(
    session_id: str,
    entity_id: int,
    *,
    target_type: ImportTargetType,
    name: str,
    note: str | None,
    player_id: int,
    created_at: int,
    target_collection_ref_type: TargetCollectionMode | None,
    target_collection_ref_id: int | None,
    db: Session,
) -> dict:
    _ = db
    connection = _connect_staging_session(session_id)
    try:
        _ensure_session_is_draft(connection)
        if target_collection_ref_type not in {None, "new", "existing", "import"}:
            raise DelverLensImportError("Target collection is invalid")
        entity = _staging_entity(connection, entity_id)
        if entity is None:
            raise DelverLensImportError("Import entity was not found")
        connection.execute(
            """
            update import_entities
            set target_type = ?,
                name = ?,
                note = ?,
                player_id = ?,
                created_at = ?,
                target_collection_ref_type = ?,
                target_collection_ref_id = ?
            where id = ?
            """,
            (
                target_type,
                name.strip(),
                note,
                player_id,
                created_at,
                target_collection_ref_type,
                target_collection_ref_id,
                entity_id,
            ),
        )
        _touch_session(connection)
        connection.commit()
        return _staging_preview(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_import_session_entity(session_id: str, entity_id: int, db: Session) -> dict:
    _ = db
    connection = _connect_staging_session(session_id)
    try:
        _ensure_session_is_draft(connection)
        if _staging_entity(connection, entity_id) is None:
            raise DelverLensImportError("Import entity was not found")
        connection.execute(
            """
            update import_entities
            set target_collection_ref_type = null,
                target_collection_ref_id = null
            where target_collection_ref_type = 'import'
                and target_collection_ref_id = ?
            """,
            (entity_id,),
        )
        connection.execute("delete from import_items where entity_id = ?", (entity_id,))
        connection.execute("delete from import_entities where id = ?", (entity_id,))
        _touch_session(connection)
        connection.commit()
        return _staging_preview(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def merge_import_session_entity(
    session_id: str,
    source_entity_id: int,
    *,
    target_entity_id: int,
    merge_section: MergeSection,
    db: Session,
) -> dict:
    _ = db
    connection = _connect_staging_session(session_id)
    try:
        _ensure_session_is_draft(connection)
        if source_entity_id == target_entity_id:
            raise DelverLensImportError("Cannot merge an import entity into itself")
        source = _staging_entity(connection, source_entity_id)
        target = _staging_entity(connection, target_entity_id)
        if source is None or target is None:
            raise DelverLensImportError("Import entity was not found")
        if target["target_type"] in {"deck", "wishdeck"}:
            if merge_section not in {"keep", "main", "side", "maybe", "commander"}:
                raise DelverLensImportError("Merge section is invalid")
            if merge_section == "keep" and (
                source["target_type"] not in {"deck", "wishdeck"}
                or target["target_type"] not in {"deck", "wishdeck"}
            ):
                raise DelverLensImportError("Keep sections is available only for deck merges")
        elif merge_section not in {"keep", "main", "side", "maybe", "commander"}:
            raise DelverLensImportError("Merge section is invalid")

        for item in _staging_items_for_entity(connection, source_entity_id):
            moved = dict(item)
            moved["entity_id"] = target_entity_id
            if target["target_type"] in {"deck", "wishdeck"}:
                moved["section"] = (
                    _valid_section(moved["section"]) if merge_section == "keep" else merge_section
                )
            _upsert_staging_item(connection, target["target_type"], moved)

        connection.execute(
            """
            update import_entities
            set target_collection_ref_id = ?
            where target_collection_ref_type = 'import'
                and target_collection_ref_id = ?
            """,
            (target_entity_id, source_entity_id),
        )
        connection.execute("delete from import_items where entity_id = ?", (source_entity_id,))
        connection.execute("delete from import_entities where id = ?", (source_entity_id,))
        _touch_session(connection)
        connection.commit()
        return _staging_preview(connection, selected_entity_id=target_entity_id)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def apply_import_session(session_id: str, db: Session) -> dict:
    connection = _connect_staging_session(session_id)
    try:
        _ensure_session_is_draft(connection)
        preview = _staging_preview(connection)
        edited_entities = preview["entities"]
        errors = _validate_apply_entities(db, edited_entities)
        if errors:
            raise DelverLensImportError("; ".join(errors))
        result = _apply_entities(edited_entities, db)
        now = _now()
        connection.execute(
            "update import_session set status = 'completed', updated_at = ?, completed_at = ?",
            (now, now),
        )
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        db.rollback()
        raise
    finally:
        connection.close()


def _connect_staging_session(session_id: str) -> sqlite3.Connection:
    path = _session_database_path(session_id)
    if not path.is_file():
        raise DelverLensImportError("Import session was not found")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    return connection


def _init_staging_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        pragma foreign_keys = on;

        create table import_session (
            id text primary key,
            kind text not null,
            source_filename text not null,
            status text not null check(status in ('draft', 'completed')),
            source_version text,
            source_timestamp text,
            default_player_id integer not null,
            created_at integer not null,
            updated_at integer not null,
            completed_at integer
        );

        create table import_entities (
            id integer primary key,
            source_list_id integer not null unique,
            source_category integer not null,
            source_category_label text not null,
            target_type text not null check(target_type in ('collection', 'wishlist', 'deck', 'wishdeck')),
            name text not null,
            note text,
            player_id integer not null,
            created_at integer not null,
            target_collection_ref_type text check(target_collection_ref_type in ('new', 'existing', 'import')),
            target_collection_ref_id integer
        );

        create table import_items (
            id integer primary key autoincrement,
            entity_id integer not null references import_entities(id) on delete cascade,
            source_card_id integer not null,
            delver_card_id integer not null,
            printing_id integer,
            scryfall_id text,
            oracle_id text,
            name text not null,
            set_code text,
            collector_number text,
            mana_cost text not null,
            type text not null,
            quantity integer not null,
            section text not null check(section in ('main', 'side', 'maybe', 'commander')),
            condition_code text,
            language_code text,
            language text,
            finish_id integer,
            finish text,
            attribute_changes_json text not null,
            warnings_json text not null,
            errors_json text not null
        );

        create index idx_import_items_entity on import_items(entity_id);
        create index idx_import_items_physical on import_items(
            entity_id, scryfall_id, finish_id, language_code, condition_code, section
        );
        create index idx_import_items_wish on import_items(entity_id, oracle_id, section);
        """
    )


def _insert_staging_entity(connection: sqlite3.Connection, entity: dict) -> None:
    connection.execute(
        """
        insert into import_entities (
            id, source_list_id, source_category, source_category_label, target_type,
            name, note, player_id, created_at, target_collection_ref_type, target_collection_ref_id
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity["source_list_id"],
            entity["source_list_id"],
            entity["source_category"],
            entity["source_category_label"],
            entity["target_type"],
            entity["name"],
            entity["note"],
            entity["player_id"],
            entity["created_at"],
            entity["target_collection_mode"],
            entity["target_collection_id"] or entity["target_import_list_id"],
        ),
    )


def _insert_staging_item(connection: sqlite3.Connection, entity_id: int, card: dict) -> None:
    connection.execute(
        """
        insert into import_items (
            entity_id, source_card_id, delver_card_id, printing_id, scryfall_id, oracle_id,
            name, set_code, collector_number, mana_cost, type, quantity, section,
            condition_code, language_code, language, finish_id, finish,
            attribute_changes_json, warnings_json, errors_json
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_id,
            card["source_card_id"],
            card["delver_card_id"],
            card["printing_id"],
            card["scryfall_id"],
            card["oracle_id"],
            card["name"],
            card["set_code"],
            card["collector_number"],
            card["mana_cost"],
            card["type"],
            card["quantity"],
            _valid_section(card["section"]),
            card["condition_code"],
            card["language_code"],
            card["language"],
            card["finish_id"],
            card["finish"],
            _json_dump(card["attribute_changes"]),
            _json_dump(card["warnings"]),
            _json_dump(card["errors"]),
        ),
    )


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load_list(value: str | None) -> list:
    if not value:
        return []
    loaded = json.loads(value)
    return loaded if isinstance(loaded, list) else []


def _valid_section(section: object) -> str:
    return str(section) if section in {"main", "side", "maybe", "commander"} else "main"


def _ensure_session_is_draft(connection: sqlite3.Connection) -> None:
    row = connection.execute("select status from import_session").fetchone()
    if row is None:
        raise DelverLensImportError("Import session is invalid")
    if row["status"] != "draft":
        raise DelverLensImportError("Import session is already completed")


def _touch_session(connection: sqlite3.Connection) -> None:
    connection.execute("update import_session set updated_at = ?", (_now(),))


def _staging_entity(connection: sqlite3.Connection, entity_id: int) -> sqlite3.Row | None:
    return connection.execute("select * from import_entities where id = ?", (entity_id,)).fetchone()


def _staging_items_for_entity(connection: sqlite3.Connection, entity_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        "select * from import_items where entity_id = ? order by section, name, id",
        (entity_id,),
    ).fetchall()


def _staging_preview(connection: sqlite3.Connection, selected_entity_id: int | None = None) -> dict:
    session = connection.execute("select * from import_session").fetchone()
    if session is None:
        raise DelverLensImportError("Import session is invalid")
    entities = []
    for entity in connection.execute("select * from import_entities order by id").fetchall():
        cards = [_staging_card_read(row, entity) for row in _staging_items_for_entity(connection, entity["id"])]
        errors = [error for card in cards for error in card["errors"]]
        warnings = [warning for card in cards for warning in card["warnings"]]
        attribute_changes = [
            {
                **change,
                "source_card_id": card["source_card_id"],
                "source_list_id": entity["source_list_id"],
                "container_name": entity["name"],
                "card_name": card["name"],
                "quantity": card["quantity"],
            }
            for card in cards
            for change in card["attribute_changes"]
        ]
        attribute_change_reasons = {
            change["reason"] for change in attribute_changes if change.get("reason")
        }
        plain_warnings = [warning for warning in set(warnings) if warning not in attribute_change_reasons]
        target_collection_ref_type = entity["target_collection_ref_type"]
        target_collection_ref_id = entity["target_collection_ref_id"]
        entities.append(
            {
                "id": entity["id"],
                "source_list_id": entity["source_list_id"],
                "source_category": entity["source_category"],
                "source_category_label": entity["source_category_label"],
                "target_type": entity["target_type"],
                "target_type_label": TARGET_LABELS[entity["target_type"]],
                "name": entity["name"],
                "note": entity["note"],
                "player_id": entity["player_id"],
                "created_at": entity["created_at"],
                "target_collection_mode": target_collection_ref_type,
                "target_collection_id": (
                    target_collection_ref_id if target_collection_ref_type == "existing" else None
                ),
                "target_import_list_id": (
                    target_collection_ref_id if target_collection_ref_type == "import" else None
                ),
                "card_count": len(cards),
                "total_quantity": sum(card["quantity"] for card in cards),
                "mapped_count": sum(1 for card in cards if card["scryfall_id"] is not None),
                "error_count": len(errors),
                "warning_count": len(attribute_changes) + len(plain_warnings),
                "errors": errors,
                "warnings": sorted(set(warnings)),
                "attribute_changes": attribute_changes,
                "cards": cards,
            }
        )
    return {
        "session_id": session["id"],
        "status": session["status"],
        "source_filename": session["source_filename"],
        "source": {
            "kind": session["kind"],
            "version": session["source_version"],
            "timestamp": session["source_timestamp"],
        },
        "default_player_id": session["default_player_id"],
        "selected_entity_id": selected_entity_id,
        "entities": entities,
    }


def _staging_card_read(row: sqlite3.Row, entity: sqlite3.Row) -> dict:
    attribute_changes = _json_load_list(row["attribute_changes_json"])
    return {
        "id": row["id"],
        "source_card_id": row["source_card_id"],
        "source_list_id": entity["source_list_id"],
        "delver_card_id": row["delver_card_id"],
        "printing_id": row["printing_id"],
        "scryfall_id": row["scryfall_id"],
        "oracle_id": row["oracle_id"],
        "name": row["name"],
        "set_code": row["set_code"],
        "collector_number": row["collector_number"],
        "mana_cost": row["mana_cost"],
        "type": row["type"],
        "quantity": row["quantity"],
        "section": row["section"],
        "condition_code": row["condition_code"],
        "language_code": row["language_code"],
        "language": row["language"],
        "finish_id": row["finish_id"],
        "finish": row["finish"],
        "attribute_changes": attribute_changes,
        "warnings": _json_load_list(row["warnings_json"]),
        "errors": _json_load_list(row["errors_json"]),
    }


def _upsert_staging_item(connection: sqlite3.Connection, target_type: str, item: dict) -> None:
    existing = _matching_staging_item(connection, target_type, item)
    if existing is None:
        _insert_staging_item(connection, item["entity_id"], _staging_item_to_card(item))
        return
    connection.execute(
        """
        update import_items
        set quantity = quantity + ?,
            warnings_json = ?,
            errors_json = ?,
            attribute_changes_json = ?
        where id = ?
        """,
        (
            item["quantity"],
            _merge_json_lists(existing["warnings_json"], item["warnings_json"]),
            _merge_json_lists(existing["errors_json"], item["errors_json"]),
            _merge_json_lists(existing["attribute_changes_json"], item["attribute_changes_json"]),
            existing["id"],
        ),
    )


def _staging_item_to_card(item: dict) -> dict:
    return {
        "source_card_id": item["source_card_id"],
        "delver_card_id": item["delver_card_id"],
        "printing_id": item["printing_id"],
        "scryfall_id": item["scryfall_id"],
        "oracle_id": item["oracle_id"],
        "name": item["name"],
        "set_code": item["set_code"],
        "collector_number": item["collector_number"],
        "mana_cost": item["mana_cost"],
        "type": item["type"],
        "quantity": item["quantity"],
        "section": item["section"],
        "condition_code": item["condition_code"],
        "language_code": item["language_code"],
        "language": item["language"],
        "finish_id": item["finish_id"],
        "finish": item["finish"],
        "attribute_changes": _json_load_list(item["attribute_changes_json"]),
        "warnings": _json_load_list(item["warnings_json"]),
        "errors": _json_load_list(item["errors_json"]),
    }


def _matching_staging_item(
    connection: sqlite3.Connection,
    target_type: str,
    item: dict,
) -> sqlite3.Row | None:
    if target_type == "wishdeck" and item["oracle_id"] is not None:
        return connection.execute(
            """
            select * from import_items
            where entity_id = ? and oracle_id = ? and section = ?
            """,
            (item["entity_id"], item["oracle_id"], item["section"]),
        ).fetchone()
    if target_type in {"collection", "wishlist"} and item["scryfall_id"] is not None:
        return connection.execute(
            """
            select * from import_items
            where entity_id = ?
                and scryfall_id = ?
                and finish_id is ?
                and language_code is ?
                and condition_code is ?
            """,
            (
                item["entity_id"],
                item["scryfall_id"],
                item["finish_id"],
                item["language_code"],
                item["condition_code"],
            ),
        ).fetchone()
    if target_type == "deck" and item["scryfall_id"] is not None:
        return connection.execute(
            """
            select * from import_items
            where entity_id = ?
                and scryfall_id = ?
                and finish_id is ?
                and language_code is ?
                and condition_code is ?
                and section = ?
            """,
            (
                item["entity_id"],
                item["scryfall_id"],
                item["finish_id"],
                item["language_code"],
                item["condition_code"],
                item["section"],
            ),
        ).fetchone()
    return connection.execute(
        """
        select * from import_items
        where entity_id = ?
            and delver_card_id = ?
            and section = ?
            and coalesce(condition_code, '') = coalesce(?, '')
            and coalesce(language_code, '') = coalesce(?, '')
            and coalesce(finish_id, -1) = coalesce(?, -1)
        """,
        (
            item["entity_id"],
            item["delver_card_id"],
            item["section"],
            item["condition_code"],
            item["language_code"],
            item["finish_id"],
        ),
    ).fetchone()


def _merge_json_lists(left_json: str, right_json: str) -> str:
    merged: list = []
    seen: set[str] = set()
    for item in [*_json_load_list(left_json), *_json_load_list(right_json)]:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return _json_dump(merged)


def _apply_entities(edited_entities: list[dict], db: Session) -> dict:
    created_collections: list[Collection] = []
    updated_collections: list[Collection] = []
    created_decks: list[Deck] = []
    collection_targets: dict[int, Collection] = {}

    for entity in edited_entities:
        if entity["target_type"] not in {"collection", "wishlist"}:
            continue
        target, target_was_created = _collection_target_for_entity(db, entity)
        collection_targets[entity["source_list_id"]] = target
        if target_was_created:
            created_collections.append(target)
        else:
            updated_collections.append(target)
        _add_collection_cards(db, target, entity["cards"], entity["created_at"])

    for entity in edited_entities:
        if entity["target_type"] == "deck":
            deck = Deck(
                player_id=entity["player_id"],
                name=entity["name"],
                note=entity["note"],
                is_wish=False,
                created_at=entity["created_at"],
                updated_at=entity["created_at"],
            )
            db.add(deck)
            db.flush()
            created_decks.append(deck)
            target_collection = _physical_deck_target_collection(db, entity, collection_targets)
            for card in entity["cards"]:
                if not _has_collection_card_identity(card):
                    continue
                collection_item = _add_collection_card(
                    db,
                    target_collection,
                    card,
                    entity["created_at"],
                )
                _add_deck_item(db, deck, collection_item, card["section"], card["quantity"])
        elif entity["target_type"] == "wishdeck":
            deck = Deck(
                player_id=entity["player_id"],
                name=entity["name"],
                note=entity["note"],
                is_wish=True,
                created_at=entity["created_at"],
                updated_at=entity["created_at"],
            )
            db.add(deck)
            db.flush()
            created_decks.append(deck)
            for card in entity["cards"]:
                if not _has_wish_card_identity(card):
                    continue
                _add_wish_deck_item(db, deck, card, entity["created_at"])

    db.commit()
    for collection in created_collections + updated_collections:
        db.refresh(collection)
    for deck in created_decks:
        db.refresh(deck)

    attribute_changes = [
        {
            **change,
            "container_name": entity["name"],
            "target_type": entity["target_type"],
        }
        for entity in edited_entities
        for change in entity["attribute_changes"]
    ]

    return {
        "created_collections": [_collection_read(collection) for collection in created_collections],
        "updated_collections": [_collection_read(collection) for collection in updated_collections],
        "created_decks": [_deck_read(deck) for deck in created_decks],
        "attribute_changes": attribute_changes,
    }


def _collection_read(collection: Collection) -> dict:
    return {
        "id": collection.id,
        "player_id": collection.player_id,
        "name": collection.name,
        "note": collection.note,
        "is_default": collection.is_default,
        "is_wishlist": collection.is_wishlist,
        "created_at": collection.created_at,
    }


def _deck_read(deck: Deck) -> dict:
    return {
        "id": deck.id,
        "player_id": deck.player_id,
        "name": deck.name,
        "note": deck.note,
        "is_wish": deck.is_wish,
        "created_at": deck.created_at,
        "updated_at": deck.updated_at,
    }


def _validate_apply_entities(db: Session, entities: list[dict]) -> list[str]:
    errors: list[str] = []
    entity_by_id = {entity["source_list_id"]: entity for entity in entities}
    existing_collection_names: dict[int, set[str]] = {}
    existing_deck_names: dict[int, set[str]] = {}
    new_collection_names: set[tuple[int, str]] = set()
    new_deck_names: set[tuple[int, str]] = set()

    for entity in entities:
        if not entity["name"]:
            errors.append("Imported names cannot be empty")
        if entity["player_id"] is None:
            errors.append(f"{entity['name']} must have an owner")
        card_errors = [
            error
            for card in entity["cards"]
            for error in _blocking_card_errors(card, entity["target_type"])
        ]
        errors.extend(f"{entity['name']}: {error}" for error in card_errors)

        player_id = entity["player_id"]
        if player_id is not None and db.get(Player, player_id) is None:
            errors.append(f"{entity['name']} has an unknown owner")

        target_type = entity["target_type"]
        if target_type in {"collection", "wishlist"}:
            _validate_collection_target(db, entity, errors)
            if entity["target_collection_mode"] == "new":
                key = (player_id, entity["name"].casefold())
                if key in new_collection_names:
                    errors.append(f"Duplicate imported collection name: {entity['name']}")
                new_collection_names.add(key)
                if player_id is not None:
                    names = existing_collection_names.setdefault(
                        player_id,
                        {
                            name.casefold()
                            for name in db.scalars(
                                select(Collection.name).where(Collection.player_id == player_id)
                            )
                        },
                    )
                    if entity["name"].casefold() in names:
                        errors.append(f"Collection already exists: {entity['name']}")
        else:
            key = (player_id, entity["name"].casefold())
            if key in new_deck_names:
                errors.append(f"Duplicate imported deck name: {entity['name']}")
            new_deck_names.add(key)
            if player_id is not None:
                names = existing_deck_names.setdefault(
                    player_id,
                    {
                        name.casefold()
                        for name in db.scalars(select(Deck.name).where(Deck.player_id == player_id))
                    },
                )
                if entity["name"].casefold() in names:
                    errors.append(f"Deck already exists: {entity['name']}")

        if target_type == "deck":
            mode = entity["target_collection_mode"]
            if mode not in {"existing", "import"}:
                errors.append(f"{entity['name']} must target a regular collection")
            if mode == "existing":
                target = db.get(Collection, entity["target_collection_id"])
                if target is None or target.is_wishlist:
                    errors.append(f"{entity['name']} must target an existing regular collection")
            if mode == "import":
                imported = entity_by_id.get(entity["target_import_list_id"])
                if imported is None or imported["target_type"] != "collection":
                    errors.append(f"{entity['name']} must target an imported collection")
                elif imported["target_collection_mode"] != "new":
                    errors.append(
                        f"{entity['name']} targets {imported['name']}, but that collection is merged elsewhere"
                    )
        elif target_type == "wishdeck":
            pass

    return errors


def _blocking_card_errors(card: dict, target_type: ImportTargetType) -> list[str]:
    errors = [error for error in card["errors"] if not _is_non_blocking_card_error(error)]
    if target_type == "wishdeck":
        ignored_prefixes = (
            "Unknown Delver condition:",
            "No legal finish is available",
        )
        return [
            error
            for error in errors
            if not any(error.startswith(prefix) for prefix in ignored_prefixes)
        ]
    return errors


def _is_non_blocking_card_error(error: str) -> bool:
    return any(error.startswith(prefix) for prefix in NON_BLOCKING_CARD_ERROR_PREFIXES) and any(
        fragment in error for fragment in NON_BLOCKING_CARD_ERROR_FRAGMENTS
    )


def _validate_collection_target(db: Session, entity: dict, errors: list[str]) -> None:
    target_type = entity["target_type"]
    mode = entity["target_collection_mode"]
    if mode not in {"new", "existing"}:
        errors.append(f"{entity['name']} must choose a collection target")
        return
    if mode == "existing":
        target = db.get(Collection, entity["target_collection_id"])
        if target is None:
            errors.append(f"{entity['name']} targets an unknown collection")
        elif target_type == "wishlist" and not target.is_wishlist:
            errors.append(f"{entity['name']} can merge only into a wishlist collection")
        elif target_type == "collection" and target.is_wishlist:
            errors.append(f"{entity['name']} can merge only into a regular collection")


def _collection_target_for_entity(db: Session, entity: dict) -> tuple[Collection, bool]:
    is_wishlist = entity["target_type"] == "wishlist"
    if entity["target_collection_mode"] == "existing":
        collection = db.get(Collection, entity["target_collection_id"])
        if collection is None:
            raise DelverLensImportError("Target collection disappeared")
        collection.note = _merge_note(collection.note, entity["name"], entity["note"])
        db.flush()
        return collection, False
    collection = Collection(
        player_id=entity["player_id"],
        name=entity["name"],
        note=entity["note"],
        is_default=False,
        is_wishlist=is_wishlist,
        created_at=entity["created_at"],
    )
    db.add(collection)
    db.flush()
    return collection, True


def _merge_note(existing_note: str | None, source_name: str, source_note: str | None) -> str | None:
    if not source_note:
        return existing_note
    addition = f'Added during import from "{source_name}":\n{source_note}'
    if existing_note:
        return f"{existing_note}\n\n{addition}"
    return addition


def _physical_deck_target_collection(
    db: Session,
    entity: dict,
    collection_targets: dict[int, Collection],
) -> Collection:
    if entity["target_collection_mode"] == "existing":
        collection = db.get(Collection, entity["target_collection_id"])
        if collection is None:
            raise DelverLensImportError("Target collection disappeared")
        return collection
    collection = collection_targets.get(entity["target_import_list_id"])
    if collection is None:
        raise DelverLensImportError("Imported target collection is unavailable")
    return collection


def _add_collection_cards(
    db: Session,
    collection: Collection,
    cards: list[dict],
    created_at: int,
) -> None:
    for card in cards:
        if not _has_collection_card_identity(card):
            continue
        _add_collection_card(db, collection, card, created_at)


def _has_collection_card_identity(card: dict) -> bool:
    return all(
        card.get(key) is not None
        for key in ("scryfall_id", "finish_id", "language_code", "condition_code")
    )


def _has_wish_card_identity(card: dict) -> bool:
    return card.get("oracle_id") is not None and card.get("language_code") is not None


def _add_collection_card(
    db: Session,
    collection: Collection,
    card: dict,
    created_at: int | None = None,
) -> CollectionItem:
    scryfall_id = UUID(card["scryfall_id"]).bytes
    item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection.id,
            CollectionItem.scryfall_id == scryfall_id,
            CollectionItem.finish_id == card["finish_id"],
            CollectionItem.language_code == card["language_code"],
            CollectionItem.condition_code == card["condition_code"],
        )
    )
    if item is None:
        item = CollectionItem(
            collection_id=collection.id,
            scryfall_id=scryfall_id,
            finish_id=card["finish_id"],
            language_code=card["language_code"],
            condition_code=card["condition_code"],
            quantity=card["quantity"],
            created_at=created_at or collection.created_at,
        )
        db.add(item)
        db.flush()
    else:
        item.quantity += card["quantity"]
        db.flush()
    return item


def _add_deck_item(
    db: Session,
    deck: Deck,
    collection_item: CollectionItem,
    section: str,
    quantity: int,
) -> None:
    item = db.scalar(
        select(DeckItem).where(
            DeckItem.deck_id == deck.id,
            DeckItem.collection_item_id == collection_item.id,
            DeckItem.section == section,
        )
    )
    if item is None:
        db.add(
            DeckItem(
                deck_id=deck.id,
                collection_item_id=collection_item.id,
                section=section,
                is_commander=section == "commander",
                quantity=quantity,
            )
        )
    else:
        item.quantity += quantity


def _add_wish_deck_item(
    db: Session,
    deck: Deck,
    card: dict,
    created_at: int | None = None,
) -> None:
    oracle_id = UUID(card["oracle_id"]).bytes
    item = db.scalar(
        select(WishDeckItem).where(
            WishDeckItem.deck_id == deck.id,
            WishDeckItem.oracle_id == oracle_id,
            WishDeckItem.section == card["section"],
        )
    )
    if item is None:
        db.add(
            WishDeckItem(
                deck_id=deck.id,
                oracle_id=oracle_id,
                language_code=card["language_code"],
                section=card["section"],
                quantity=card["quantity"],
                created_at=created_at or deck.created_at,
            )
        )
    else:
        item.quantity += card["quantity"]
        item.language_code = card["language_code"]
