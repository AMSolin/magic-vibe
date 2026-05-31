import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import time
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.app_data_session import AppDataSessionLocal
from app.models.app_data import AppSetting, CatalogImport

LOCAL_CATALOG_SOURCE_NAME = "Local MTGJSON AllPrintings.sqlite"
LANGUAGES = (
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese (Brazil)"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("ru", "Russian"),
    ("zhs", "Chinese Simplified"),
    ("zht", "Chinese Traditional"),
    ("he", "Hebrew"),
    ("la", "Latin"),
    ("grc", "Ancient Greek"),
    ("ar", "Arabic"),
    ("sa", "Sanskrit"),
    ("ph", "Phyrexian"),
    ("qya", "Quenya"),
)
FINISHES = ((0, "nonfoil"), (1, "foil"), (2, "etched"), (3, "signed"))

SCHEMA_SQL = """
create table sets (
    code          text primary key,
    name          text not null,
    keyrune_code  text not null,
    release_date  integer not null,
    type          text not null
);

create table languages (
    code  text primary key,
    name  text not null unique
);

create table finishes (
    id    integer primary key,
    name  text not null unique
);

create table card_printings (
    id                integer primary key,
    scryfall_id       blob not null unique check(length(scryfall_id) = 16),
    oracle_id         blob not null check(length(oracle_id) = 16),
    set_code          text not null references sets(code),
    collector_number  text not null,
    language_code     text not null references languages(code),
    name              text not null,
    rarity            text not null,
    layout            text not null
);

create table card_printing_finishes (
    printing_id  integer not null references card_printings(id) on delete cascade,
    finish_id    integer not null references finishes(id),
    primary key (printing_id, finish_id)
);

create table card_printing_faces (
    id              integer primary key,
    printing_id     integer not null references card_printings(id) on delete cascade,
    face_order      integer not null check(face_order >= 0),
    side            text,
    face_name       text,
    mana_cost       text not null,
    mana_value      real not null,
    type            text not null,
    text            text not null,
    colors          text not null,
    color_identity  text not null,
    keywords        text,
    power           text,
    toughness       text,
    loyalty         text,
    defense         text,
    unique (printing_id, face_order),
    unique (printing_id, side)
);

create table card_face_localizations (
    id             integer primary key,
    face_id        integer not null references card_printing_faces(id) on delete cascade,
    language_code  text not null references languages(code),
    name           text not null,
    face_name      text,
    type           text,
    text           text,
    flavor_text    text,
    unique (face_id, language_code)
);

create table card_search_index (
    id              integer primary key,
    oracle_id       blob not null check(length(oracle_id) = 16),
    face_order      integer not null check(face_order >= 0),
    language_code   text not null references languages(code),
    name            text not null collate nocase,
    type            text not null,
    text            text not null,
    mana_value      real not null,
    colors          text not null,
    color_identity  text not null,
    keywords        text,
    search_priority integer not null,
    unique (oracle_id, face_order, language_code, name, type, text)
);

create table token_printings (
    id                integer primary key,
    scryfall_id       blob not null unique check(length(scryfall_id) = 16),
    oracle_id         blob not null check(length(oracle_id) = 16),
    set_code          text not null,
    collector_number  text not null,
    language_code     text not null references languages(code),
    name              text not null,
    layout            text not null
);

create table token_printing_faces (
    id                 integer primary key,
    token_printing_id  integer not null references token_printings(id) on delete cascade,
    face_order         integer not null check(face_order >= 0),
    side               text,
    face_name          text,
    mana_cost          text not null,
    type               text not null,
    text               text not null,
    colors             text not null,
    color_identity     text not null,
    keywords           text,
    power              text,
    toughness          text,
    unique (token_printing_id, face_order),
    unique (token_printing_id, side)
);

create table token_printing_finishes (
    token_printing_id  integer not null references token_printings(id) on delete cascade,
    finish_id          integer not null references finishes(id),
    primary key (token_printing_id, finish_id)
);
"""

INDEX_SQL = """
create index idx_card_printings_oracle_id
    on card_printings (oracle_id);
create index idx_card_printings_set_number
    on card_printings (set_code, collector_number);
create index idx_card_printings_name
    on card_printings (name collate nocase);
create index idx_card_printing_finishes_finish
    on card_printing_finishes (finish_id, printing_id);
create index idx_card_printing_faces_printing
    on card_printing_faces (printing_id, face_order);
create index idx_card_printing_faces_face_name
    on card_printing_faces (face_name collate nocase);
create index idx_card_face_localizations_name
    on card_face_localizations (name collate nocase);
create index idx_card_face_localizations_language
    on card_face_localizations (language_code, face_id);
create index idx_card_search_name
    on card_search_index (name collate nocase);
create index idx_card_search_oracle
    on card_search_index (oracle_id);
create index idx_card_search_language
    on card_search_index (language_code);
create index idx_token_printings_oracle_id
    on token_printings (oracle_id);
create index idx_token_printings_set_number
    on token_printings (set_code, collector_number);
create index idx_token_printings_name
    on token_printings (name collate nocase);
create index idx_token_printing_faces_printing
    on token_printing_faces (token_printing_id, face_order);
create index idx_token_printing_finishes_finish
    on token_printing_finishes (finish_id, token_printing_id);
"""


def _uuid_blob(value: str) -> bytes:
    return UUID(value).bytes


def _language_code(name: str) -> str:
    codes = {language_name: code for code, language_name in LANGUAGES}
    try:
        return codes[name]
    except KeyError as error:
        raise ValueError(f"Unsupported MTGJSON language: {name}") from error


def _face_order(side: str | None) -> int:
    return 0 if side is None else ord(side) - ord("a")


def _unix_date(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def _set_setting(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting is None:
        db.add(AppSetting(key=key, value=value))
        return
    setting.value = value


def _create_catalog(source_path: Path, catalog_path: Path) -> int:
    catalog_path.unlink(missing_ok=True)
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    catalog = sqlite3.connect(catalog_path)
    catalog.execute("pragma foreign_keys = on")
    catalog.execute("pragma journal_mode = off")
    catalog.execute("pragma synchronous = off")
    try:
        catalog.executescript(SCHEMA_SQL)
        catalog.executemany("insert into languages (code, name) values (?, ?)", LANGUAGES)
        catalog.executemany("insert into finishes (id, name) values (?, ?)", FINISHES)

        physical_sets = source.execute(
            """
            select code, name, keyruneCode, releaseDate, type
            from sets
            where coalesce(isOnlineOnly, 0) = 0
            """
        )
        catalog.executemany(
            "insert into sets (code, name, keyrune_code, release_date, type) values (?, ?, ?, ?, ?)",
            (
                (code, name, keyrune_code, _unix_date(release_date), set_type)
                for code, name, keyrune_code, release_date, set_type in physical_sets
            ),
        )

        card_rows = list(
            source.execute(
                """
                select
                    c.uuid,
                    i.scryfallId,
                    i.scryfallOracleId,
                    c.setCode,
                    c.number,
                    c.language,
                    c.name,
                    c.rarity,
                    c.layout,
                    c.side,
                    c.faceName,
                    c.manaCost,
                    c.manaValue,
                    c.type,
                    c.text,
                    c.colors,
                    c.colorIdentity,
                    c.keywords,
                    c.power,
                    c.toughness,
                    c.loyalty,
                    c.defense,
                    c.finishes
                from cards as c
                join cardIdentifiers as i on i.uuid = c.uuid
                join sets as s on s.code = c.setCode
                where
                    coalesce(c.isOnlineOnly, 0) = 0
                    and coalesce(s.isOnlineOnly, 0) = 0
                order by i.scryfallId, c.side
                """
            )
        )
        if not card_rows:
            raise ValueError("MTGJSON source does not contain physical cards")

        printing_ids: dict[str, int] = {}
        printing_properties: dict[str, tuple[str, ...]] = {}
        for row in card_rows:
            (
                _,
                scryfall_id,
                oracle_id,
                set_code,
                collector_number,
                language,
                name,
                rarity,
                layout,
                *_,
            ) = row
            if not scryfall_id or not oracle_id:
                raise ValueError("Physical MTGJSON card is missing a Scryfall identifier")
            properties = (
                oracle_id,
                set_code,
                collector_number,
                language,
                name,
                rarity,
                layout,
            )
            if scryfall_id in printing_properties:
                if printing_properties[scryfall_id] != properties:
                    raise ValueError(f"Inconsistent printing properties for Scryfall ID {scryfall_id}")
                continue
            printing_properties[scryfall_id] = properties
            cursor = catalog.execute(
                """
                insert into card_printings (
                    scryfall_id, oracle_id, set_code, collector_number,
                    language_code, name, rarity, layout
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _uuid_blob(scryfall_id),
                    _uuid_blob(oracle_id),
                    set_code,
                    collector_number,
                    _language_code(language),
                    name,
                    rarity,
                    layout,
                ),
            )
            printing_ids[scryfall_id] = cursor.lastrowid

        finish_ids = {name: finish_id for finish_id, name in FINISHES}
        face_ids_by_uuid: dict[str, int] = {}
        face_keys: set[tuple[int, int]] = set()
        for row in card_rows:
            (
                mtgjson_uuid,
                scryfall_id,
                _,
                _,
                _,
                _,
                _,
                _,
                _,
                side,
                face_name,
                mana_cost,
                mana_value,
                card_type,
                text,
                colors,
                color_identity,
                keywords,
                power,
                toughness,
                loyalty,
                defense,
                finishes,
            ) = row
            printing_id = printing_ids[scryfall_id]
            order = _face_order(side)
            face_key = (printing_id, order)
            if face_key in face_keys:
                raise ValueError(f"Duplicate face order for Scryfall ID {scryfall_id}")
            face_keys.add(face_key)
            cursor = catalog.execute(
                """
                insert into card_printing_faces (
                    printing_id, face_order, side, face_name, mana_cost,
                    mana_value, type, text, colors, color_identity, keywords,
                    power, toughness, loyalty, defense
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    printing_id,
                    order,
                    side,
                    face_name,
                    mana_cost,
                    mana_value,
                    card_type,
                    text,
                    colors,
                    color_identity,
                    keywords,
                    power,
                    toughness,
                    loyalty,
                    defense,
                ),
            )
            face_ids_by_uuid[mtgjson_uuid] = cursor.lastrowid
            for finish in finishes.split(", "):
                try:
                    finish_id = finish_ids[finish]
                except KeyError as error:
                    raise ValueError(f"Unsupported MTGJSON finish: {finish}") from error
                catalog.execute(
                    """
                    insert or ignore into card_printing_finishes (printing_id, finish_id)
                    values (?, ?)
                    """,
                    (printing_id, finish_id),
                )

        localized_rows = source.execute(
            """
            select uuid, language, name, faceName, type, text, flavorText
            from cardForeignData
            """
        )
        localization_rows: list[tuple[int, str, str, str | None, str | None, str | None, str | None]] = []
        for mtgjson_uuid, language, name, face_name, card_type, text, flavor_text in localized_rows:
            face_id = face_ids_by_uuid.get(mtgjson_uuid)
            if face_id is None:
                continue
            localization_rows.append(
                (
                    face_id,
                    _language_code(language),
                    name,
                    face_name,
                    card_type,
                    text,
                    flavor_text,
                )
            )
        catalog.executemany(
            """
            insert into card_face_localizations (
                face_id, language_code, name, face_name, type, text, flavor_text
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            localization_rows,
        )

        catalog.execute(
            """
            insert or ignore into card_search_index (
                oracle_id, face_order, language_code, name, type, text,
                mana_value, colors, color_identity, keywords, search_priority
            )
            select
                p.oracle_id,
                f.face_order,
                p.language_code,
                coalesce(f.face_name, p.name),
                f.type,
                f.text,
                f.mana_value,
                f.colors,
                f.color_identity,
                f.keywords,
                1
            from card_printing_faces as f
            join card_printings as p on p.id = f.printing_id
            """
        )
        catalog.execute(
            """
            insert or ignore into card_search_index (
                oracle_id, face_order, language_code, name, type, text,
                mana_value, colors, color_identity, keywords, search_priority
            )
            select
                p.oracle_id,
                f.face_order,
                l.language_code,
                coalesce(l.face_name, l.name),
                coalesce(l.type, f.type),
                coalesce(l.text, f.text),
                f.mana_value,
                f.colors,
                f.color_identity,
                f.keywords,
                2
            from card_face_localizations as l
            join card_printing_faces as f on f.id = l.face_id
            join card_printings as p on p.id = f.printing_id
            """
        )

        token_rows = list(
            source.execute(
                """
                select
                    t.uuid,
                    i.scryfallId,
                    i.scryfallOracleId,
                    t.setCode,
                    t.number,
                    t.language,
                    t.name,
                    t.layout,
                    t.side,
                    t.faceName,
                    t.manaCost,
                    t.type,
                    t.text,
                    t.colors,
                    t.colorIdentity,
                    t.keywords,
                    t.power,
                    t.toughness,
                    t.finishes
                from tokens as t
                join tokenIdentifiers as i on i.uuid = t.uuid
                where t.layout <> 'art_series'
                order by i.scryfallId, t.side
                """
            )
        )
        token_printing_ids: dict[str, int] = {}
        token_printing_properties: dict[str, tuple[str, ...]] = {}
        for row in token_rows:
            (
                _,
                scryfall_id,
                oracle_id,
                set_code,
                collector_number,
                language,
                name,
                layout,
                *_,
            ) = row
            if not scryfall_id or not oracle_id:
                raise ValueError("MTGJSON token is missing a Scryfall identifier")
            properties = (oracle_id, set_code, collector_number, language, name, layout)
            if scryfall_id in token_printing_properties:
                if token_printing_properties[scryfall_id] != properties:
                    raise ValueError(f"Inconsistent token properties for Scryfall ID {scryfall_id}")
                continue
            token_printing_properties[scryfall_id] = properties
            cursor = catalog.execute(
                """
                insert into token_printings (
                    scryfall_id, oracle_id, set_code, collector_number,
                    language_code, name, layout
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _uuid_blob(scryfall_id),
                    _uuid_blob(oracle_id),
                    set_code,
                    collector_number,
                    _language_code(language),
                    name,
                    layout,
                ),
            )
            token_printing_ids[scryfall_id] = cursor.lastrowid

        token_face_keys: set[tuple[int, int]] = set()
        for row in token_rows:
            (
                _,
                scryfall_id,
                _,
                _,
                _,
                _,
                _,
                _,
                side,
                face_name,
                mana_cost,
                token_type,
                text,
                colors,
                color_identity,
                keywords,
                power,
                toughness,
                finishes,
            ) = row
            token_printing_id = token_printing_ids[scryfall_id]
            order = _face_order(side)
            face_key = (token_printing_id, order)
            if face_key in token_face_keys:
                raise ValueError(f"Duplicate token face order for Scryfall ID {scryfall_id}")
            token_face_keys.add(face_key)
            catalog.execute(
                """
                insert into token_printing_faces (
                    token_printing_id, face_order, side, face_name, mana_cost,
                    type, text, colors, color_identity, keywords, power, toughness
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_printing_id,
                    order,
                    side,
                    face_name,
                    mana_cost or "",
                    token_type or "",
                    text or "",
                    colors or "",
                    color_identity or "",
                    keywords,
                    power,
                    toughness,
                ),
            )
            for finish in finishes.split(", "):
                try:
                    finish_id = finish_ids[finish]
                except KeyError as error:
                    raise ValueError(f"Unsupported MTGJSON token finish: {finish}") from error
                catalog.execute(
                    """
                    insert or ignore into token_printing_finishes (token_printing_id, finish_id)
                    values (?, ?)
                    """,
                    (token_printing_id, finish_id),
                )

        catalog.executescript(INDEX_SQL)
        catalog.commit()

        if catalog.execute("pragma foreign_key_check").fetchall():
            raise ValueError("Catalog foreign key validation failed")
        if catalog.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise ValueError("Catalog integrity validation failed")
        unresolved_search_rows = catalog.execute(
            """
            select count(*)
            from card_search_index as si
            where not exists (
                select 1 from card_printings as p where p.oracle_id = si.oracle_id
            )
            """
        ).fetchone()[0]
        if unresolved_search_rows:
            raise ValueError("Catalog search index contains unresolved oracle IDs")

        return len(printing_ids)
    finally:
        catalog.close()
        source.close()


def _install_catalog(next_path: Path, catalog_path: Path) -> None:
    previous_path = catalog_path.with_name("catalog.previous.db")
    if catalog_path.exists():
        shutil.copy2(catalog_path, previous_path)
    os.replace(next_path, catalog_path)


def import_catalog_source(
    catalog_import_id: int,
    *,
    session_factory: sessionmaker[Session] = AppDataSessionLocal,
    source_path: str = settings.catalog_source_path,
    catalog_path: str = settings.catalog_database_path,
) -> None:
    source = Path(source_path)
    catalog = Path(catalog_path)
    next_catalog = catalog.with_name("catalog.next.db")
    try:
        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is None:
                raise ValueError("Catalog import record does not exist")
            catalog_import.status = "importing"
            db.commit()

        catalog.parent.mkdir(parents=True, exist_ok=True)
        row_count = _create_catalog(source, next_catalog)
        _install_catalog(next_catalog, catalog)

        source_db = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        try:
            source_date, source_version = source_db.execute("select date, version from meta").fetchone()
        finally:
            source_db.close()

        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is None:
                raise ValueError("Catalog import record does not exist")
            catalog_import.source_updated_at = _unix_date(source_date)
            catalog_import.finished_at = int(time())
            catalog_import.status = "completed"
            catalog_import.catalog_row_count = row_count
            catalog_import.source_file_size = source.stat().st_size
            _set_setting(db, "catalog.path", str(catalog))
            _set_setting(db, "catalog.source_version", source_version)
            db.commit()
    except Exception as error:
        next_catalog.unlink(missing_ok=True)
        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is not None:
                catalog_import.finished_at = int(time())
                catalog_import.status = "failed"
                catalog_import.error_message = str(error)
                db.commit()


def rebuild_catalog_from_local_source(
    catalog_import_id: int,
    *,
    session_factory: sessionmaker[Session] = AppDataSessionLocal,
) -> None:
    with session_factory() as db:
        setting = db.get(AppSetting, "catalog.pending_source_path")
        if setting is None or setting.value is None:
            source_path = None
        else:
            source_path = setting.value

    if source_path is None:
        with session_factory() as db:
            catalog_import = db.get(CatalogImport, catalog_import_id)
            if catalog_import is not None:
                catalog_import.finished_at = int(time())
                catalog_import.status = "failed"
                catalog_import.error_message = "Local MTGJSON source file is not available"
                db.commit()
        return

    import_catalog_source(
        catalog_import_id,
        session_factory=session_factory,
        source_path=source_path,
    )
