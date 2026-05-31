from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

app_data_engine = create_engine(
    settings.app_database_url,
    connect_args=(
        {"check_same_thread": False} if settings.app_database_url.startswith("sqlite") else {}
    ),
)
AppDataSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=app_data_engine)


def get_app_data_db() -> Generator[Session]:
    db = AppDataSessionLocal()
    try:
        yield db
    finally:
        db.close()
