from pathlib import Path

from app.core.config import settings
from app.db.app_data_base import AppDataBase
from app.db.app_data_session import app_data_engine
from app.models.app_data import APP_DATA_MODELS


def _ensure_sqlite_parent_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return

    database_path = Path(database_url.removeprefix(prefix))
    database_path.parent.mkdir(parents=True, exist_ok=True)


def init_app_data_db() -> None:
    _ = APP_DATA_MODELS
    _ensure_sqlite_parent_directory(settings.app_database_url)
    AppDataBase.metadata.create_all(bind=app_data_engine)
