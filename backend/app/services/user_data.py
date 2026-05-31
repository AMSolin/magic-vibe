from pathlib import Path
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
            Deck(player=player, name="Default deck", is_default=True, created_at=created_at),
            Deck(
                player=player,
                name="Wish deck",
                is_wishlist=True,
                wishlist_collection=wishlist,
                created_at=created_at,
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
