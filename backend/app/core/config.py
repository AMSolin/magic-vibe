from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Magic Explorer"
    database_url: str = "sqlite:///./magic_explorer.db"
    app_database_url: str = "sqlite:///./data/app_data.db"
    catalog_source_url: str = "https://mtgjson.com/api/v5/AllPrintings.sqlite.xz"
    catalog_source_path: str = "./data/import/AllPrintings.sqlite"
    catalog_database_path: str = "./data/catalog.db"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
