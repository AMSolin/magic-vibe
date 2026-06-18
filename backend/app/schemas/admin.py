from pydantic import BaseModel, ConfigDict


class CatalogImportRead(BaseModel):
    id: int
    source: str
    source_updated_at: int | None
    started_at: int
    finished_at: int | None
    status: str
    error_message: str | None
    catalog_row_count: int | None
    source_file_size: int | None
    source_sha256: str | None

    model_config = ConfigDict(from_attributes=True)


class CatalogStatusRead(BaseModel):
    latest_import: CatalogImportRead | None
    latest_successful_import: CatalogImportRead | None
    latest_source_index_updated_at: int | None
    installed_source_index_updated_at: int | None
    source_index_status: str
    source_index_error: str | None


class UserDataStatusRead(BaseModel):
    exists: bool
    file_size: int | None
    modified_at: int | None


class ScryfallSymbolsStatusRead(BaseModel):
    exists: bool
    symbol_count: int
    updated_at: int | None


class DelverLensMappingStatusRead(BaseModel):
    exists: bool
    database_path: str
    database_file_size: int | None
    database_modified_at: int | None
    row_count: int | None
    unique_scryfall_ids: int | None
    apk_exists: bool
    apk_path: str
    apk_file_size: int | None
    apk_modified_at: int | None
    source_url: str | None
    apk_url: str | None
    source_app_version: str | None
    source_release_date: int | None
    latest_source_app_version: str | None
    latest_source_release_date: int | None
    source_status: str
    source_status_error: str | None
    source_db_member: str | None
    source_table: str | None
    updated_at: int | None
    last_error: str | None


class GeneratedTestCollectionRead(BaseModel):
    id: int
    name: str
    language_code: str
    rows: int
    unique_scryfall_ids: int
    total_quantity: int


class GeneratedTestCollectionsRead(BaseModel):
    collections: list[GeneratedTestCollectionRead]
