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


class UserDataStatusRead(BaseModel):
    exists: bool
    file_size: int | None
    modified_at: int | None


class ScryfallSymbolsStatusRead(BaseModel):
    exists: bool
    symbol_count: int
    updated_at: int | None


class GeneratedTestCollectionRead(BaseModel):
    id: int
    name: str
    language_code: str
    rows: int
    unique_scryfall_ids: int
    total_quantity: int


class GeneratedTestCollectionsRead(BaseModel):
    collections: list[GeneratedTestCollectionRead]
