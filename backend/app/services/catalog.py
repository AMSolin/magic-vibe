import re
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
    connection.create_function("unicode_casefold", 1, lambda value: value.casefold(), deterministic=True)
    try:
        yield connection
    finally:
        connection.close()


def _uuid_text(value: bytes) -> str:
    return str(UUID(bytes=value))


def search_card_names(query: str, *, exact: bool, limit: int = 15) -> list[dict]:
    return search_cards(query, field="name", exact=exact, limit=limit)


def search_cards(
    query: str,
    *,
    field: str = "name",
    exact: bool = False,
    limit: int = 15,
) -> list[dict]:
    normalized_query = query.casefold()
    if field not in {"name", "type", "text"}:
        raise ValueError("Unsupported search field")
    with catalog_connection() as catalog:
        columns = {
            row["name"]
            for row in catalog.execute("pragma table_info(card_search_index)")
        }
        normalized_field = (
            "normalized_name"
            if field == "name" and "normalized_name" in columns
            else "unicode_casefold(name)"
            if field == "name"
            else f"unicode_casefold({field})"
        )
        select_sql = """
            select
                oracle_id, min(face_order) as face_order, language_code, name,
                min(search_priority) as search_priority
            from card_search_index
            where {match}
            group by oracle_id, language_code, name
            order by
                search_priority,
                name collate nocase,
                language_code
            limit ?
        """
        if exact:
            rows = catalog.execute(
                select_sql.format(match=f"{normalized_field} = ?"),
                (normalized_query, limit),
            ).fetchall()
        elif field == "name":
            rows = catalog.execute(
                select_sql.format(match=f"{normalized_field} >= ? and {normalized_field} < ?"),
                (normalized_query, f"{normalized_query}\U0010ffff", limit),
            ).fetchall()
            if not rows:
                rows = catalog.execute(
                    select_sql.format(match=f"{normalized_field} like ?"),
                    (f"%{normalized_query}%", limit),
                ).fetchall()
        else:
            rows = catalog.execute(
                select_sql.format(match=f"{normalized_field} like ?"),
                (f"%{normalized_query}%", limit),
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


def oracle_ids_matching_deck_filters(
    *,
    colors: list[str],
    color_match: str,
    has_uncolored_mana: bool,
    has_colorless_mana: bool,
    has_generic_mana: bool,
    no_colors: bool,
) -> set[str]:
    selected_colors = {color.upper() for color in colors if color.upper() in {"W", "U", "B", "R", "G"}}
    if not (selected_colors or has_uncolored_mana or has_colorless_mana or has_generic_mana or no_colors):
        return set()

    with catalog_connection() as catalog:
        rows = catalog.execute(
            """
            select
                p.oracle_id,
                group_concat(distinct f.color_identity) as color_identities,
                group_concat(f.mana_cost, '') as mana_cost
            from card_printings as p
            join card_printing_faces as f on f.printing_id = p.id
            group by p.oracle_id
            """
        ).fetchall()

    matching_ids: set[str] = set()
    generic_mana_pattern = re.compile(r"\{(?:\d+|X)\}", re.IGNORECASE)
    for row in rows:
        identity = {
            color
            for color in (row["color_identities"] or "")
            if color in {"W", "U", "B", "R", "G"}
        }
        mana_cost = row["mana_cost"] or ""

        if no_colors and identity:
            continue
        has_colorless_symbol = "{C}" in mana_cost
        has_generic_symbol = generic_mana_pattern.search(mana_cost) is not None
        has_requested_mana_symbol = bool(
            (has_uncolored_mana and (has_colorless_symbol or has_generic_symbol))
            or (has_colorless_mana and has_colorless_symbol)
            or (has_generic_mana and has_generic_symbol)
        )
        needs_requested_mana_symbol = has_uncolored_mana or has_colorless_mana or has_generic_mana

        if selected_colors:
            if color_match == "includes_any":
                color_matches = bool(identity & selected_colors) or has_requested_mana_symbol
            elif color_match == "exactly":
                color_matches = identity == selected_colors and (
                    has_requested_mana_symbol if needs_requested_mana_symbol else True
                )
            else:
                color_matches = selected_colors <= identity and (
                    has_requested_mana_symbol if needs_requested_mana_symbol else True
                )
            if not color_matches:
                continue
        elif needs_requested_mana_symbol:
            if color_match == "exactly":
                color_matches = not identity and has_requested_mana_symbol
            else:
                color_matches = has_requested_mana_symbol
            if not color_matches:
                continue

        matching_ids.add(_uuid_text(row["oracle_id"]))
    return matching_ids


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
        localization_rows = catalog.execute(
            """
            select distinct f.printing_id, l.language_code as code, language.name
            from card_printing_faces as f
            join card_face_localizations as l on l.face_id = f.id
            join languages as language on language.code = l.language_code
            where f.printing_id in (
                select id from card_printings where oracle_id = ?
            )
            order by l.language_code
            """,
            (UUID(oracle_id).bytes,),
        ).fetchall()
    finishes: dict[int, list[dict[str, int | str]]] = {}
    for row in finish_rows:
        finishes.setdefault(row["printing_id"], []).append({"id": row["id"], "name": row["name"]})
    localizations: dict[int, list[dict[str, str]]] = {}
    for row in localization_rows:
        localizations.setdefault(row["printing_id"], []).append(
            {"code": row["code"], "name": row["name"]}
        )
    return [
        {
            **dict(row),
            "scryfall_id": _uuid_text(row["scryfall_id"]),
            "finishes": finishes.get(row["id"], []),
            "localizations": localizations.get(row["id"], []),
        }
        for row in rows
    ]


def get_printing(printing_id: int) -> dict | None:
    with catalog_connection() as catalog:
        row = catalog.execute(
            """
            select
                p.id, p.scryfall_id, p.oracle_id, p.set_code, p.collector_number,
                p.language_code, p.name, f.mana_cost, f.type
            from card_printings as p
            join card_printing_faces as f
                on f.printing_id = p.id
                and f.face_order = (
                    select min(face_order)
                    from card_printing_faces
                    where printing_id = p.id
                )
            where p.id = ?
            """,
            (printing_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        **dict(row),
        "scryfall_id": _uuid_text(row["scryfall_id"]),
        "oracle_id": _uuid_text(row["oracle_id"]),
    }


def get_printing_by_scryfall_id(scryfall_id: bytes) -> dict | None:
    with catalog_connection() as catalog:
        row = catalog.execute(
            """
            select
                p.id, p.scryfall_id, p.oracle_id, p.set_code, p.collector_number,
                p.language_code, p.name, p.rarity, f.mana_cost, f.type,
                l.name as language, s.keyrune_code, s.release_date
            from card_printings as p
            join card_printing_faces as f
                on f.printing_id = p.id
                and f.face_order = (
                    select min(face_order)
                    from card_printing_faces
                    where printing_id = p.id
                )
            join languages as l on l.code = p.language_code
            join sets as s on s.code = p.set_code
            where p.scryfall_id = ?
            """,
            (scryfall_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        **dict(row),
        "scryfall_id": _uuid_text(row["scryfall_id"]),
        "oracle_id": _uuid_text(row["oracle_id"]),
    }


def get_printings_by_scryfall_ids(scryfall_ids: list[bytes]) -> dict[bytes, dict]:
    if not scryfall_ids:
        return {}
    rows: list[sqlite3.Row] = []
    with catalog_connection() as catalog:
        for offset in range(0, len(scryfall_ids), 500):
            chunk = scryfall_ids[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                catalog.execute(
                    f"""
                    select
                        p.id, p.scryfall_id, p.oracle_id, p.set_code, p.collector_number,
                        p.language_code, p.name, p.rarity, f.mana_cost, f.mana_value, f.type,
                        l.name as language, s.keyrune_code, s.release_date
                    from card_printings as p
                    join card_printing_faces as f
                        on f.printing_id = p.id
                        and f.face_order = (
                            select min(face_order)
                            from card_printing_faces
                            where printing_id = p.id
                        )
                    join languages as l on l.code = p.language_code
                    join sets as s on s.code = p.set_code
                    where p.scryfall_id in ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            )
    return {
        row["scryfall_id"]: {
            **dict(row),
            "scryfall_id": _uuid_text(row["scryfall_id"]),
            "oracle_id": _uuid_text(row["oracle_id"]),
        }
        for row in rows
    }


def scryfall_ids_for_oracle_ids(oracle_ids: set[str]) -> set[bytes]:
    if not oracle_ids:
        return set()
    oracle_id_bytes = [UUID(oracle_id).bytes for oracle_id in oracle_ids]
    rows: list[sqlite3.Row] = []
    with catalog_connection() as catalog:
        for offset in range(0, len(oracle_id_bytes), 500):
            chunk = oracle_id_bytes[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                catalog.execute(
                    f"""
                    select scryfall_id
                    from card_printings
                    where oracle_id in ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            )
    return {row["scryfall_id"] for row in rows}


def get_localized_printing_faces_many(
    requests: list[tuple[int, str]],
) -> dict[tuple[int, str], list[dict]]:
    if not requests:
        return {}
    unique_requests = list(dict.fromkeys(requests))
    with catalog_connection() as catalog:
        catalog.execute(
            "create temporary table requested_faces (printing_id integer, language_code text)"
        )
        catalog.executemany("insert into requested_faces values (?, ?)", unique_requests)
        rows = catalog.execute(
            """
            select
                r.printing_id,
                r.language_code,
                f.face_order,
                coalesce(l.face_name, l.name, f.face_name, p.name) as name,
                coalesce(l.type, f.type) as type_line,
                coalesce(l.text, f.text) as oracle_text,
                l.flavor_text,
                f.mana_cost
            from requested_faces as r
            join card_printings as p on p.id = r.printing_id
            join card_printing_faces as f on f.printing_id = p.id
            left join card_face_localizations as l
                on l.face_id = f.id and l.language_code = coalesce(r.language_code, p.language_code)
            order by r.printing_id, r.language_code, f.face_order
            """
        ).fetchall()
    faces_by_request: dict[tuple[int, str], list[dict]] = {}
    for row in rows:
        face = dict(row)
        key = (face.pop("printing_id"), face.pop("language_code"))
        faces_by_request.setdefault(key, []).append(face)
    return faces_by_request


def get_localized_printing_faces(printing_id: int, language_code: str | None = None) -> list[dict]:
    with catalog_connection() as catalog:
        rows = catalog.execute(
            """
            select
                f.face_order,
                coalesce(l.face_name, l.name, f.face_name, p.name) as name,
                coalesce(l.type, f.type) as type_line,
                coalesce(l.text, f.text) as oracle_text,
                l.flavor_text,
                f.mana_cost
            from card_printings as p
            join card_printing_faces as f on f.printing_id = p.id
            left join card_face_localizations as l
                on l.face_id = f.id and l.language_code = coalesce(?, p.language_code)
            where p.id = ?
            order by f.face_order
            """,
            (language_code, printing_id),
        ).fetchall()
    return [dict(row) for row in rows]


def finish_names(finish_ids: list[int]) -> dict[int, str]:
    if not finish_ids:
        return {}
    placeholders = ",".join("?" for _ in finish_ids)
    with catalog_connection() as catalog:
        rows = catalog.execute(
            f"select id, name from finishes where id in ({placeholders})",
            finish_ids,
        ).fetchall()
    return {row["id"]: row["name"] for row in rows}


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


def printing_supports_language(printing_id: int, language_code: str) -> bool:
    with catalog_connection() as catalog:
        return (
            catalog.execute(
                """
                select 1
                from card_printings as p
                where
                    p.id = ?
                    and (
                        p.language_code = ?
                        or exists (
                            select 1
                            from card_printing_faces as f
                            join card_face_localizations as l on l.face_id = f.id
                            where f.printing_id = p.id and l.language_code = ?
                        )
                    )
                """,
                (printing_id, language_code, language_code),
            ).fetchone()
            is not None
        )


def language_name(language_code: str) -> str | None:
    with catalog_connection() as catalog:
        row = catalog.execute(
            "select name from languages where code = ?",
            (language_code,),
        ).fetchone()
    return row["name"] if row is not None else None


def language_names(language_codes: list[str]) -> dict[str, str]:
    if not language_codes:
        return {}
    placeholders = ",".join("?" for _ in language_codes)
    with catalog_connection() as catalog:
        rows = catalog.execute(
            f"select code, name from languages where code in ({placeholders})",
            language_codes,
        ).fetchall()
    return {row["code"]: row["name"] for row in rows}


def finish_name(finish_id: int) -> str | None:
    with catalog_connection() as catalog:
        row = catalog.execute("select name from finishes where id = ?", (finish_id,)).fetchone()
    return row["name"] if row is not None else None
