from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.app_data_base import AppDataBase
from app.models.app_data import APP_DATA_MODELS, AppSetting, CatalogImport


def test_app_data_tables_are_created_in_separate_metadata() -> None:
    _ = APP_DATA_MODELS
    engine = create_engine("sqlite://", poolclass=StaticPool)

    AppDataBase.metadata.create_all(bind=engine)

    assert set(inspect(engine).get_table_names()) == {"app_settings", "catalog_imports"}


def test_app_data_tables_store_settings_and_catalog_import_history() -> None:
    _ = APP_DATA_MODELS
    engine = create_engine("sqlite://", poolclass=StaticPool)
    AppDataBase.metadata.create_all(bind=engine)

    with Session(engine) as db:
        db.add(AppSetting(key="catalog.source", value="MTGJSON AllPrintings.sqlite"))
        db.add(
            CatalogImport(
                source="MTGJSON AllPrintings.sqlite",
                source_updated_at=1_780_272_000,
                started_at=1_780_275_600,
                finished_at=1_780_275_720,
                status="completed",
                catalog_row_count=81_939,
                source_file_size=284_491_776,
                source_sha256="a" * 64,
            )
        )
        db.commit()

        setting = db.get(AppSetting, "catalog.source")
        catalog_import = db.scalar(select(CatalogImport))

    assert setting is not None
    assert setting.value == "MTGJSON AllPrintings.sqlite"
    assert catalog_import is not None
    assert catalog_import.status == "completed"
    assert catalog_import.source_updated_at == 1_780_272_000
    assert catalog_import.catalog_row_count == 81_939
