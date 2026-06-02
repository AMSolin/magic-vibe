from pydantic import BaseModel, ConfigDict, Field


class WorkspacePlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_default: bool


class WorkspaceCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    player_id: int
    note: str | None = None
    is_default: bool = False
    is_wishlist: bool = False
    created_at: int | None = Field(default=None, ge=0)


class WorkspaceCollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    player_id: int | None = None
    note: str | None = None
    is_default: bool | None = None
    is_wishlist: bool | None = None
    created_at: int | None = Field(default=None, ge=0)


class WorkspaceCollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int
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


class WorkspaceCollectionItemUpdate(WorkspaceCollectionItemCreate):
    pass


class WorkspaceCollectionItemRead(BaseModel):
    id: int
    printing_id: int
    collection_id: int
    scryfall_id: str
    oracle_id: str
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
