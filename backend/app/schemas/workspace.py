from pydantic import BaseModel, Field


class WorkspaceCollectionRead(BaseModel):
    id: int
    name: str
    is_default: bool
    is_wishlist: bool
    note: str | None
    created_at: int


class CardSuggestionRead(BaseModel):
    oracle_id: str
    face_order: int
    language_code: str
    language: str
    name: str


class PrintingRead(BaseModel):
    id: int
    scryfall_id: str
    set_code: str
    set_name: str
    keyrune_code: str
    release_date: int
    collector_number: str
    language_code: str
    language: str
    rarity: str
    finishes: list[dict[str, int | str]]
    localizations: list[dict[str, str]]


class PrintingOptionsRead(BaseModel):
    oracle_id: str
    preferred_language_code: str
    printings: list[PrintingRead]


class CardDetailsRead(BaseModel):
    printing_id: int
    image_normal_url: str | None
    image_native_url: str | None
    card: dict


class WorkspaceCollectionItemCreate(BaseModel):
    printing_id: int
    finish_id: int
    language_code: str | None = Field(default=None, min_length=2, max_length=3)
    condition_code: str = "NM"
    quantity: int = Field(default=1, ge=1)


class WorkspaceCollectionItemRead(BaseModel):
    id: int
    printing_id: int
    collection_id: int
    scryfall_id: str
    name: str
    set_code: str
    keyrune_code: str
    rarity: str
    collector_number: str
    language_code: str
    language: str
    finish_id: int
    finish: str
    condition_code: str
    quantity: int
    mana_cost: str
    type: str
