import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.user_data_base import UserDataBase
from app.models.user_data import (
    CardCondition,
    Collection,
    CollectionItem,
    Deck,
    DeckItem,
    Player,
    USER_DATA_MODELS,
)
from app.services import catalog
from app.services.delver_lens_import import (
    apply_import_session,
    create_delver_lens_import_session,
    delete_import_session_entity,
    merge_import_session_entity,
    update_import_session_entity,
)

SCRYFALL_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
ORACLE_A = UUID("bbbbbbbb-0000-0000-0000-000000000001")
SCRYFALL_B = UUID("aaaaaaaa-0000-0000-0000-000000000002")
ORACLE_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")


@pytest.fixture()
def import_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, sessionmaker[Session]]:
    _ = USER_DATA_MODELS
    catalog_path = tmp_path / "catalog.db"
    mapping_path = tmp_path / "delver_lens_mapping.db"
    dlens_path = tmp_path / "sample.dlens"
    _create_catalog(catalog_path)
    _create_mapping(mapping_path)
    _create_dlens(dlens_path)
    monkeypatch.setattr(catalog.settings, "catalog_database_path", str(catalog_path))

    engine = create_engine(f"sqlite:///{tmp_path / 'user_data.db'}")

    def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("pragma foreign_keys = on")
        cursor.close()

    event.listen(engine, "connect", enable_foreign_keys)
    UserDataBase.metadata.create_all(engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with testing_session() as db:
        player = Player(name="Player", is_default=True, created_at=1)
        db.add_all(
            [
                CardCondition(code="NM", name="Near Mint", sort_order=1),
                CardCondition(code="SP", name="Slightly Played", sort_order=2),
                CardCondition(code="MP", name="Moderately Played", sort_order=3),
                CardCondition(code="HP", name="Heavily Played", sort_order=4),
                CardCondition(code="D", name="Damaged", sort_order=5),
                player,
                Collection(player=player, name="Existing", is_default=True, created_at=1),
                Collection(player=player, name="Existing wishlist", is_wishlist=True, created_at=1),
            ]
        )
        db.commit()
    return dlens_path, testing_session


def test_preview_maps_delver_lists_cards_and_fallbacks(
    import_environment: tuple[Path, sessionmaker[Session]],
) -> None:
    dlens_path, session_factory = import_environment
    with session_factory() as db:
        preview = create_delver_lens_import_session(dlens_path, "sample.dlens", db)

    assert preview["default_player_id"] == 1
    assert [(entity["source_list_id"], entity["target_type"]) for entity in preview["entities"]] == [
        (1, "collection"),
        (2, "deck"),
        (3, "wishlist"),
    ]
    collection = preview["entities"][0]
    card = collection["cards"][0]
    assert card["language_code"] == "en"
    assert card["finish"] == "nonfoil"
    finish_change = collection["attribute_changes"][0]
    assert finish_change["attribute"] == "finish"
    assert finish_change["before"] == "foil"
    assert finish_change["after"] == "nonfoil"
    assert collection["warning_count"] == 1


def test_apply_import_adds_physical_deck_cards_to_existing_collection(
    import_environment: tuple[Path, sessionmaker[Session]],
) -> None:
    dlens_path, session_factory = import_environment
    with session_factory() as db:
        preview = create_delver_lens_import_session(dlens_path, "sample.dlens", db)
        session_id = preview["session_id"]
        deck_entity = next(entity for entity in preview["entities"] if entity["source_list_id"] == 2)
        update_import_session_entity(
            session_id,
            deck_entity["id"],
            target_type="deck",
            name=deck_entity["name"],
            note=deck_entity["note"],
            player_id=deck_entity["player_id"],
            created_at=deck_entity["created_at"],
            target_collection_ref_type="existing",
            target_collection_ref_id=1,
            db=db,
        )

        result = apply_import_session(session_id, db)

    assert [collection["name"] for collection in result["created_collections"]] == [
        "Collection import",
        "Wishlist import",
    ]
    assert [deck["name"] for deck in result["created_decks"]] == ["Deck import"]
    assert result["attribute_changes"][0]["card_name"] == "Foil Trap"

    with session_factory() as db:
        existing_collection_id = db.scalar(select(Collection.id).where(Collection.name == "Existing"))
        assert existing_collection_id == 1
        existing_items = list(
            db.scalars(select(CollectionItem).where(CollectionItem.collection_id == existing_collection_id))
        )
        assert sum(item.quantity for item in existing_items) == 2
        deck = db.scalar(select(Deck).where(Deck.name == "Deck import"))
        assert deck is not None
        deck_items = list(db.scalars(select(DeckItem).where(DeckItem.deck_id == deck.id)))
        assert [(item.section, item.quantity) for item in deck_items] == [("commander", 2)]


def test_apply_import_ignores_unrecognized_cards(
    import_environment: tuple[Path, sessionmaker[Session]],
) -> None:
    dlens_path, session_factory = import_environment
    with sqlite3.connect(dlens_path) as dlens_db:
        dlens_db.execute(
            """
            insert into cards values (
                4, 57719, 0, 0.0, 1, null, 1781209502401, 1, '', '', '', 0, 0, 0, 0, '', '', 0.0, ''
            )
            """
        )
        dlens_db.commit()

    with session_factory() as db:
        preview = create_delver_lens_import_session(dlens_path, "sample.dlens", db)
        session_id = preview["session_id"]
        collection = preview["entities"][0]
        unrecognized_card = next(card for card in collection["cards"] if card["delver_card_id"] == 57719)
        assert unrecognized_card["errors"] == [
            "Delver card id 57719 is not mapped",
            "Delver card id 57719 does not resolve to catalog",
        ]
        for entity in preview["entities"]:
            if entity["source_list_id"] != 2:
                continue
            update_import_session_entity(
                session_id,
                entity["id"],
                target_type=entity["target_type"],
                name=entity["name"],
                note=entity["note"],
                player_id=entity["player_id"],
                created_at=entity["created_at"],
                target_collection_ref_type="existing",
                target_collection_ref_id=1,
                db=db,
            )

        result = apply_import_session(session_id, db)

    assert [collection["name"] for collection in result["created_collections"]] == [
        "Collection import",
        "Wishlist import",
    ]


def test_import_session_merge_physically_moves_and_sums_cards(
    import_environment: tuple[Path, sessionmaker[Session]],
) -> None:
    dlens_path, session_factory = import_environment
    with sqlite3.connect(dlens_path) as dlens_db:
        dlens_db.execute(
            """
            insert into cards values (
                4, 10, 1, 0.0, 3, null, 1781209502401, 3, '', '', '', 0, 0, 0, 0, '', '', 0.0, ''
            )
            """
        )
        dlens_db.commit()

    with session_factory() as db:
        preview = create_delver_lens_import_session(dlens_path, "sample.dlens", db)
        session_id = preview["session_id"]
        result = merge_import_session_entity(
            session_id,
            3,
            target_entity_id=1,
            merge_section="main",
            db=db,
        )

    assert result["selected_entity_id"] == 1
    assert [entity["source_list_id"] for entity in result["entities"]] == [1, 2]
    collection = next(entity for entity in result["entities"] if entity["id"] == 1)
    assert collection["total_quantity"] == 5
    assert len(collection["cards"]) == 1
    assert collection["cards"][0]["quantity"] == 5


def test_import_session_delete_clears_dependent_physical_deck_target(
    import_environment: tuple[Path, sessionmaker[Session]],
) -> None:
    dlens_path, session_factory = import_environment
    with session_factory() as db:
        preview = create_delver_lens_import_session(dlens_path, "sample.dlens", db)
        session_id = preview["session_id"]
        update_import_session_entity(
            session_id,
            2,
            target_type="deck",
            name="Deck import",
            note="",
            player_id=1,
            created_at=1781209483,
            target_collection_ref_type="import",
            target_collection_ref_id=1,
            db=db,
        )
        result = delete_import_session_entity(session_id, 1, db)

    assert [entity["source_list_id"] for entity in result["entities"]] == [2, 3]
    deck = next(entity for entity in result["entities"] if entity["id"] == 2)
    assert deck["target_collection_mode"] is None
    assert deck["target_collection_id"] is None
    assert deck["target_import_list_id"] is None


def _create_catalog(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table sets (
            code text primary key, name text, keyrune_code text, release_date integer, type text
        );
        create table languages (code text primary key, name text);
        create table finishes (id integer primary key, name text);
        create table card_printings (
            id integer primary key, scryfall_id blob, oracle_id blob, set_code text,
            collector_number text, language_code text, name text, rarity text, layout text
        );
        create table card_printing_finishes (printing_id integer, finish_id integer);
        create table card_printing_faces (
            id integer primary key, printing_id integer, face_order integer, side text,
            face_name text, mana_cost text, mana_value real, type text, text text,
            colors text, color_identity text, keywords text, power text, toughness text,
            loyalty text, defense text
        );
        create table card_face_localizations (
            id integer primary key, face_id integer, language_code text, name text,
            face_name text, type text, text text, flavor_text text
        );
        insert into sets values ('TST', 'Test Set', 'tst', 1780099200, 'expansion');
        insert into languages values ('en', 'English');
        insert into languages values ('ru', 'Russian');
        insert into finishes values (0, 'nonfoil');
        insert into finishes values (1, 'foil');
        """
    )
    db.execute(
        "insert into card_printings values (1, ?, ?, 'TST', '1', 'en', 'Foil Trap', 'rare', 'normal')",
        (SCRYFALL_A.bytes, ORACLE_A.bytes),
    )
    db.execute("insert into card_printing_finishes values (1, 0)")
    db.execute(
        """
        insert into card_printing_faces values (
            1, 1, 0, null, null, '{1}{W}', 2, 'Instant', '', 'W', 'W', '', null, null, null, null
        )
        """
    )
    db.execute(
        "insert into card_printings values (2, ?, ?, 'TST', '2', 'en', 'Section Captain', 'rare', 'normal')",
        (SCRYFALL_B.bytes, ORACLE_B.bytes),
    )
    db.execute("insert into card_printing_finishes values (2, 0)")
    db.execute("insert into card_printing_finishes values (2, 1)")
    db.execute(
        """
        insert into card_printing_faces values (
            2, 2, 0, null, null, '{2}{U}', 3, 'Creature', '', 'U', 'U', '', '2', '2', null, null
        )
        """
    )
    db.commit()
    db.close()


def _create_mapping(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "create table cards (_id integer primary key, scryfall_id blob not null check(length(scryfall_id) = 16))"
    )
    db.execute("insert into cards values (10, ?)", (SCRYFALL_A.bytes,))
    db.execute("insert into cards values (20, ?)", (SCRYFALL_B.bytes,))
    db.commit()
    db.close()


def _create_dlens(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table delverlens (key text, value text);
        create table lists (
            _id integer, background integer, category integer, name text, creation numeric,
            tab integer, uuid text, note text
        );
        create table cards (
            _id integer, card integer, foil integer, price real, quantity integer, image blob,
            creation numeric, list integer, note text, condition text, language text,
            publish integer, tab integer, downloaded_img integer, general integer,
            img_uuid text, uuid text, price_acquired real, scryfall_id text
        );
        insert into delverlens values ('version', '6.98');
        insert into delverlens values ('timestamp', '20260617190150');
        insert into lists values (1, -1, 1, 'Collection import', 1781209483402, 0, '', '');
        insert into lists values (2, -1, 2, 'Deck import', 1781209483402, 0, '', '');
        insert into lists values (3, -1, 3, 'Wishlist import', 1781209483402, 0, '', '');
        """
    )
    db.execute(
        """
        insert into cards values (
            1, 10, 1, 0.0, 1, null, 1781209502401, 1, '', '', '', 0, 0, 0, 0, '', '', 0.0, ''
        )
        """
    )
    db.execute(
        """
        insert into cards values (
            2, 20, 0, 0.0, 2, null, 1781209502401, 2, '', 'Near Mint', 'English',
            0, 0, 0, 1, '', '', 0.0, ''
        )
        """
    )
    db.execute(
        """
        insert into cards values (
            3, 10, 0, 0.0, 1, null, 1781209502401, 3, '', '', '', 0, 0, 0, 0, '', '', 0.0, ''
        )
        """
    )
    db.commit()
    db.close()
