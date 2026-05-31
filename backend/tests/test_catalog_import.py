import shutil
import sqlite3
from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.db.app_data_base import AppDataBase
from app.models.app_data import APP_DATA_MODELS, AppSetting, CatalogImport
from app.services.catalog_import import import_catalog_source

SET_UUID = "10000000-0000-0000-0000-000000000001"
BOLT_UUID = "20000000-0000-0000-0000-000000000001"
FRONT_UUID = "30000000-0000-0000-0000-000000000001"
BACK_UUID = "30000000-0000-0000-0000-000000000002"
BOLT_SCRYFALL_ID = "40000000-0000-0000-0000-000000000001"
DFC_SCRYFALL_ID = "40000000-0000-0000-0000-000000000002"
BOLT_ORACLE_ID = "50000000-0000-0000-0000-000000000001"
DFC_ORACLE_ID = "50000000-0000-0000-0000-000000000002"
TOKEN_FRONT_UUID = "60000000-0000-0000-0000-000000000001"
TOKEN_BACK_UUID = "60000000-0000-0000-0000-000000000002"
TOKEN_ART_UUID = "60000000-0000-0000-0000-000000000003"
TOKEN_SCRYFALL_ID = "70000000-0000-0000-0000-000000000001"
TOKEN_ART_SCRYFALL_ID = "70000000-0000-0000-0000-000000000002"
TOKEN_ORACLE_ID = "80000000-0000-0000-0000-000000000001"
TOKEN_ART_ORACLE_ID = "80000000-0000-0000-0000-000000000002"


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


def _create_source(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table meta (date text, version text);
        insert into meta values ('2026-05-30', '5.3.0+test');

        create table sets (
            code text,
            name text,
            keyruneCode text,
            releaseDate text,
            type text,
            isOnlineOnly boolean
        );
        insert into sets values ('TST', 'Test Set', 'TST', '2026-05-30', 'expansion', 0);

        create table cards (
            uuid text,
            setCode text,
            number text,
            language text,
            name text,
            rarity text,
            layout text,
            side text,
            faceName text,
            manaCost text,
            manaValue real,
            type text,
            text text,
            colors text,
            colorIdentity text,
            keywords text,
            power text,
            toughness text,
            loyalty text,
            defense text,
            finishes text,
            isOnlineOnly boolean
        );
        create table cardIdentifiers (
            uuid text,
            scryfallId text,
            scryfallOracleId text
        );
        create table cardForeignData (
            uuid text,
            language text,
            name text,
            faceName text,
            type text,
            text text,
            flavorText text
        );
        create table tokens (
            uuid text,
            setCode text,
            number text,
            language text,
            name text,
            layout text,
            side text,
            faceName text,
            manaCost text,
            type text,
            text text,
            colors text,
            colorIdentity text,
            keywords text,
            power text,
            toughness text,
            finishes text
        );
        create table tokenIdentifiers (
            uuid text,
            scryfallId text,
            scryfallOracleId text
        );
        """
    )
    db.executemany(
        """
        insert into cards values (
            ?, 'TST', ?, 'English', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null, null, ?, 0
        )
        """,
        [
            (
                BOLT_UUID,
                "1",
                "Lightning Bolt",
                "common",
                "normal",
                None,
                None,
                "{R}",
                1,
                "Instant",
                "Lightning Bolt deals 3 damage to any target.",
                "R",
                "R",
                "",
                None,
                None,
                "nonfoil, foil",
            ),
            (
                FRONT_UUID,
                "2",
                "Front // Back",
                "rare",
                "transform",
                "a",
                "Front",
                "{1}{G}",
                2,
                "Creature",
                "Front text.",
                "G",
                "G",
                "Transform",
                "2",
                "2",
                "nonfoil",
            ),
            (
                BACK_UUID,
                "2",
                "Front // Back",
                "rare",
                "transform",
                "b",
                "Back",
                "",
                0,
                "Creature",
                "Back text.",
                "G",
                "G",
                "Transform",
                "4",
                "4",
                "nonfoil",
            ),
        ],
    )
    db.executemany(
        "insert into cardIdentifiers values (?, ?, ?)",
        [
            (BOLT_UUID, BOLT_SCRYFALL_ID, BOLT_ORACLE_ID),
            (FRONT_UUID, DFC_SCRYFALL_ID, DFC_ORACLE_ID),
            (BACK_UUID, DFC_SCRYFALL_ID, DFC_ORACLE_ID),
        ],
    )
    db.execute(
        "insert into cardForeignData values (?, 'Russian', 'Молния', null, 'Мгновенное заклинание', 'Текст молнии.', null)",
        (BOLT_UUID,),
    )
    db.executemany(
        "insert into tokens values (?, 'TTST', ?, 'English', ?, ?, ?, ?, '', ?, ?, ?, ?, null, ?, ?, ?)",
        [
            (
                TOKEN_FRONT_UUID,
                "1",
                "Human // Zombie",
                "double_faced_token",
                "a",
                "Human",
                "Token Creature - Human",
                "",
                "W",
                "W",
                "1",
                "1",
                "nonfoil, foil",
            ),
            (
                TOKEN_BACK_UUID,
                "1",
                "Human // Zombie",
                "double_faced_token",
                "b",
                "Zombie",
                "Token Creature - Zombie",
                "",
                "B",
                "B",
                "2",
                "2",
                "nonfoil, foil",
            ),
            (
                TOKEN_ART_UUID,
                "2",
                "Art Card",
                "art_series",
                None,
                None,
                "Card",
                "",
                "",
                "",
                None,
                None,
                "nonfoil",
            ),
        ],
    )
    db.executemany(
        "insert into tokenIdentifiers values (?, ?, ?)",
        [
            (TOKEN_FRONT_UUID, TOKEN_SCRYFALL_ID, TOKEN_ORACLE_ID),
            (TOKEN_BACK_UUID, TOKEN_SCRYFALL_ID, TOKEN_ORACLE_ID),
            (TOKEN_ART_UUID, TOKEN_ART_SCRYFALL_ID, TOKEN_ART_ORACLE_ID),
        ],
    )
    db.commit()
    db.close()


def test_catalog_import_builds_and_installs_catalog(workspace_tmp_path: Path) -> None:
    source_path = workspace_tmp_path / "AllPrintings.sqlite"
    catalog_path = workspace_tmp_path / "catalog.db"
    _create_source(source_path)
    catalog_path.write_bytes(b"previous catalog")
    session_factory = _create_session_factory(workspace_tmp_path / "app_data.db")
    with session_factory() as db:
        catalog_import = CatalogImport(
            source="MTGJSON AllPrintings.sqlite.xz",
            started_at=1_780_362_000,
            status="downloaded",
        )
        db.add(catalog_import)
        db.commit()
        db.refresh(catalog_import)
        catalog_import_id = catalog_import.id

    import_catalog_source(
        catalog_import_id,
        session_factory=session_factory,
        source_path=str(source_path),
        catalog_path=str(catalog_path),
    )

    catalog = sqlite3.connect(catalog_path)
    assert catalog.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert catalog.execute("select count(*) from card_printings").fetchone()[0] == 2
    assert catalog.execute("select count(*) from card_printing_faces").fetchone()[0] == 3
    assert catalog.execute("select count(*) from card_face_localizations").fetchone()[0] == 1
    assert catalog.execute("select count(*) from card_printing_finishes").fetchone()[0] == 3
    assert catalog.execute("select count(*) from token_printings").fetchone()[0] == 1
    assert catalog.execute("select count(*) from token_printing_faces").fetchone()[0] == 2
    assert catalog.execute("select count(*) from token_printing_finishes").fetchone()[0] == 2
    assert catalog.execute("select id, name from finishes order by id").fetchall() == [
        (0, "nonfoil"),
        (1, "foil"),
        (2, "etched"),
        (3, "signed"),
    ]
    assert catalog.execute(
        "select name from card_search_index where language_code = 'ru'"
    ).fetchall() == [("Молния",)]
    assert catalog.execute(
        """
        select name from card_search_index
        where oracle_id = ? and language_code = 'en'
        """,
        (UUID(DFC_ORACLE_ID).bytes,),
    ).fetchall() == [("Front // Back",)]
    assert catalog.execute(
        "select language_code, search_priority from card_search_index order by language_code"
    ).fetchall() == [("en", 0), ("en", 0), ("ru", 1)]
    catalog.close()

    assert (workspace_tmp_path / "catalog.previous.db").read_bytes() == b"previous catalog"
    with session_factory() as db:
        catalog_import = db.get(CatalogImport, catalog_import_id)
        source_version = db.get(AppSetting, "catalog.source_version")

    assert catalog_import is not None
    assert catalog_import.status == "completed"
    assert catalog_import.catalog_row_count == 2
    assert source_version is not None
    assert source_version.value == "5.3.0+test"
