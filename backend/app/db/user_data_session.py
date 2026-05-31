from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("pragma foreign_keys = on")
    cursor.close()


user_data_engine = create_engine(
    settings.user_database_url,
    connect_args=(
        {"check_same_thread": False} if settings.user_database_url.startswith("sqlite") else {}
    ),
)
if settings.user_database_url.startswith("sqlite"):
    event.listen(user_data_engine, "connect", _enable_sqlite_foreign_keys)

UserDataSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_data_engine)


def get_user_data_db() -> Generator[Session]:
    db = UserDataSessionLocal()
    try:
        yield db
    finally:
        db.close()
