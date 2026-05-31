import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from app.core.config import settings


def catalog_database_path() -> Path:
    return Path(settings.catalog_database_path)


@contextmanager
def catalog_connection() -> Iterator[sqlite3.Connection]:
    path = catalog_database_path()
    if not path.is_file():
        raise FileNotFoundError("Catalog database is not installed")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _uuid_text(value: bytes) -> str:
    return str(UUID(bytes=value))


def search_card_names(query: str, *, exact: bool, limit: int = 15) -> list[dict]:
    operator = "=" if exact else "like"
    value = query if exact else f"%{query}%"
    prefix = query if exact else f"{query}%"
    with catalog_connection() as catalog:
        rows = catalog.execute(
            f"""
            select
                oracle_id, min(face_order) as face_order, language_code, name,
                min(search_priority) as search_priority
            from card_search_index
            where name {operator} ? collate nocase
            group by oracle_id, language_code, name
            order by
                search_priority,
                case when name like ? collate nocase then 0 else 1 end,
                name collate nocase,
                language_code
            limit ?
            """,
            (value, prefix, limit),
        ).fetchall()
        languages = {
            row["code"]: row["name"]
            for row in catalog.execute("select code, name from languages")
        }
    return [
        {
            "oracle_id": _uuid_text(row["oracle_id"]),
            "face_order": row["face_order"],
            "language_code": row["language_code"],
            "language": languages[row["language_code"]],
            "name": row["name"],
        }
        for row in rows
    ]


def list_printings(oracle_id: str) -> list[dict]:
    with catalog_connection() as catalog:
        rows = catalog.execute(
            """
            select
                p.id, p.scryfall_id, p.set_code, s.name as set_name,
                s.keyrune_code, s.release_date, p.collector_number,
                p.language_code, l.name as language, p.rarity
            from card_printings as p
            join sets as s on s.code = p.set_code
            join languages as l on l.code = p.language_code
            where p.oracle_id = ?
            order by s.release_date desc, p.set_code, p.collector_number, p.language_code
            """,
            (UUID(oracle_id).bytes,),
        ).fetchall()
        finish_rows = catalog.execute(
            """
            select pf.printing_id, f.id, f.name
            from card_printing_finishes as pf
            join finishes as f on f.id = pf.finish_id
            where pf.printing_id in (
                select id from card_printings where oracle_id = ?
            )
            order by f.id
            """,
            (UUID(oracle_id).bytes,),
        ).fetchall()
    finishes: dict[int, list[dict[str, int | str]]] = {}
    for row in finish_rows:
        finishes.setdefault(row["printing_id"], []).append({"id": row["id"], "name": row["name"]})
    return [
        {
            **dict(row),
            "scryfall_id": _uuid_text(row["scryfall_id"]),
            "finishes": finishes.get(row["id"], []),
        }
        for row in rows
    ]


def get_printing(printing_id: int) -> dict | None:
    with catalog_connection() as catalog:
        row = catalog.execute(
            """
            select
                p.id, p.scryfall_id, p.set_code, p.collector_number,
                p.language_code, p.name, f.mana_cost, f.type
            from card_printings as p
            join card_printing_faces as f on f.printing_id = p.id and f.face_order = 0
            where p.id = ?
            """,
            (printing_id,),
        ).fetchone()
    if row is None:
        return None
    return {**dict(row), "scryfall_id": _uuid_text(row["scryfall_id"])}


def get_printing_by_scryfall_id(scryfall_id: bytes) -> dict | None:
    with catalog_connection() as catalog:
        row = catalog.execute(
            """
            select
                p.id, p.scryfall_id, p.set_code, p.collector_number,
                p.language_code, p.name, f.mana_cost, f.type,
                l.name as language
            from card_printings as p
            join card_printing_faces as f on f.printing_id = p.id and f.face_order = 0
            join languages as l on l.code = p.language_code
            where p.scryfall_id = ?
            """,
            (scryfall_id,),
        ).fetchone()
    if row is None:
        return None
    return {**dict(row), "scryfall_id": _uuid_text(row["scryfall_id"])}


def printing_supports_finish(printing_id: int, finish_id: int) -> bool:
    with catalog_connection() as catalog:
        return (
            catalog.execute(
                """
                select 1 from card_printing_finishes
                where printing_id = ? and finish_id = ?
                """,
                (printing_id, finish_id),
            ).fetchone()
            is not None
        )


def finish_name(finish_id: int) -> str | None:
    with catalog_connection() as catalog:
        row = catalog.execute("select name from finishes where id = ?", (finish_id,)).fetchone()
    return row["name"] if row is not None else None
