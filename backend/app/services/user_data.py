from pathlib import Path
import sqlite3
from time import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.user_data_base import UserDataBase
from app.db.user_data_session import UserDataSessionLocal, user_data_engine
from app.models.user_data import CardCondition, Collection, Deck, Player, USER_DATA_MODELS

CARD_CONDITIONS = (
    ("NM", "Near Mint", 1),
    ("SP", "Slightly Played", 2),
    ("MP", "Moderately Played", 3),
    ("HP", "Heavily Played", 4),
    ("D", "Damaged", 5),
)


def _sqlite_database_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("User database initialization currently supports SQLite only")
    return Path(database_url.removeprefix(prefix))


def user_data_database_path() -> Path:
    return _sqlite_database_path(settings.user_database_url)


def user_data_database_exists() -> bool:
    return user_data_database_path().is_file()


def ensure_user_data_schema_compatibility() -> None:
    database_path = user_data_database_path()
    if not database_path.is_file():
        return
    with sqlite3.connect(database_path) as connection:
        collection_indexes = {
            row[1] for row in connection.execute("pragma index_list(collections)").fetchall()
        }
        deck_columns = {
            row[1]: row for row in connection.execute("pragma table_info(decks)").fetchall()
        }
        needs_deck_schema_rebuild = bool(deck_columns) and (
            "is_wish" not in deck_columns
            or "updated_at" not in deck_columns
            or "is_default" in deck_columns
            or "is_wishlist" in deck_columns
            or "wishlist_collection_id" in deck_columns
        )

        default_collection_ids = [
            row[0]
            for row in connection.execute(
                """
                select id
                from collections
                where is_default = 1
                order by
                    case when player_id is null then 1 else 0 end,
                    created_at desc,
                    id desc
                """
            ).fetchall()
        ]
        if len(default_collection_ids) > 1:
            keeper_id = default_collection_ids[0]
            connection.execute(
                "update collections set is_default = 0 where is_default = 1 and id != ?",
                (keeper_id,),
            )

        if "uq_collections_player_default" in collection_indexes:
            connection.execute("drop index if exists uq_collections_player_default")
        connection.execute(
            """
            create unique index if not exists uq_collections_default
                on collections (is_default)
                where is_default = 1
            """
        )

        if needs_deck_schema_rebuild:
            connection.execute("pragma foreign_keys = off")
            connection.executescript(
                """
                drop table if exists wish_deck_items;
                drop table if exists deck_items;
                drop table if exists decks;
                """
            )
            connection.execute("pragma foreign_keys = on")

    UserDataBase.metadata.create_all(bind=user_data_engine)


def _seed_user_data(db: Session) -> None:
    created_at = int(time())
    player = Player(name="Player", is_default=True, created_at=created_at)
    collection = Collection(
        player=player,
        name="My collection",
        is_default=True,
        created_at=created_at,
    )
    wishlist = Collection(
        player=player,
        name="Wishlist",
        is_wishlist=True,
        created_at=created_at,
    )
    db.add_all(
        [
            *(CardCondition(code=code, name=name, sort_order=sort_order) for code, name, sort_order in CARD_CONDITIONS),
            player,
            collection,
            wishlist,
            Deck(
                player=player,
                name="Default deck",
                created_at=created_at,
                updated_at=created_at,
            ),
            Deck(
                player=player,
                name="Wish deck",
                is_wish=True,
                created_at=created_at,
                updated_at=created_at,
            ),
        ]
    )
    db.commit()


def recreate_user_data_db() -> None:
    _ = USER_DATA_MODELS
    database_path = user_data_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    user_data_engine.dispose()
    database_path.unlink(missing_ok=True)
    UserDataBase.metadata.create_all(bind=user_data_engine)
    with UserDataSessionLocal() as db:
        _seed_user_data(db)
