from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.user_data import (
    USER_DATA_MODELS,
    CardCondition,
    Collection,
    CollectionItem,
    Deck,
    DeckItem,
    Player,
)
from app.services import user_data


@pytest.fixture()
def user_data_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker[Session]:
    _ = USER_DATA_MODELS
    database_path = tmp_path / "user_data.db"
    engine = create_engine(f"sqlite:///{database_path}")

    def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("pragma foreign_keys = on")
        cursor.close()

    event.listen(engine, "connect", enable_foreign_keys)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(user_data.settings, "user_database_url", f"sqlite:///{database_path}")
    monkeypatch.setattr(user_data, "user_data_engine", engine)
    monkeypatch.setattr(user_data, "UserDataSessionLocal", testing_session)
    user_data.recreate_user_data_db()
    return testing_session


def test_user_data_tables_are_created_with_seed_data(
    user_data_database: sessionmaker[Session],
) -> None:
    engine = user_data_database.kw["bind"]
    assert set(inspect(engine).get_table_names()) == {
        "card_conditions",
        "collection_items",
        "collections",
        "deck_items",
        "decks",
        "players",
    }

    with user_data_database() as db:
        player = db.scalar(select(Player))
        conditions = list(db.scalars(select(CardCondition).order_by(CardCondition.sort_order)))
        collections = list(db.scalars(select(Collection).order_by(Collection.id)))
        decks = list(db.scalars(select(Deck).order_by(Deck.id)))

    assert player is not None
    assert player.name == "Player"
    assert player.is_default is True
    assert [condition.code for condition in conditions] == ["NM", "SP", "MP", "HP", "D"]
    assert [(collection.name, collection.is_default, collection.is_wishlist) for collection in collections] == [
        ("My collection", True, False),
        ("Wishlist", False, True),
    ]
    assert [(deck.name, deck.is_default, deck.is_wishlist) for deck in decks] == [
        ("Default deck", True, False),
        ("Wish deck", False, True),
    ]
    assert decks[1].wishlist_collection_id == collections[1].id


def test_recreate_user_data_db_discards_existing_rows(
    user_data_database: sessionmaker[Session],
) -> None:
    with user_data_database() as db:
        db.add(Player(name="Temporary", created_at=1))
        db.commit()

    user_data.recreate_user_data_db()

    with user_data_database() as db:
        assert list(db.scalars(select(Player.name).order_by(Player.id))) == ["Player"]


def test_collection_item_requires_positive_quantity_and_known_condition(
    user_data_database: sessionmaker[Session],
) -> None:
    with user_data_database() as db:
        collection_id = db.scalar(select(Collection.id).where(Collection.name == "My collection"))
        assert collection_id is not None
        db.add(
            CollectionItem(
                collection_id=collection_id,
                scryfall_id=b"a" * 16,
                finish_id=0,
                language_code="en",
                condition_code="UNKNOWN",
                quantity=0,
                created_at=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_deck_item_rejects_unknown_section(
    user_data_database: sessionmaker[Session],
) -> None:
    with user_data_database() as db:
        collection_id = db.scalar(select(Collection.id).where(Collection.name == "My collection"))
        deck_id = db.scalar(select(Deck.id).where(Deck.name == "Default deck"))
        assert collection_id is not None
        assert deck_id is not None
        collection_item = CollectionItem(
            collection_id=collection_id,
            scryfall_id=b"a" * 16,
            finish_id=0,
            language_code="en",
            condition_code="NM",
            quantity=1,
            created_at=1,
        )
        db.add(collection_item)
        db.flush()
        db.add(
            DeckItem(
                deck_id=deck_id,
                collection_item_id=collection_item.id,
                section="invalid",
                quantity=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
