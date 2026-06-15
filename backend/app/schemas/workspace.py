from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DeckSection = Literal["main", "side", "maybe", "commander"]


class WorkspacePlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_default: bool
    created_at: int


class WorkspacePlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_default: bool = False
    created_at: int | None = Field(default=None, ge=0)


class WorkspacePlayerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_default: bool | None = None
    created_at: int | None = Field(default=None, ge=0)


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
    player_id: int | None
    name: str
    is_default: bool
    is_wishlist: bool
    note: str | None
    created_at: int


class WorkspaceDeckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int | None
    name: str
    is_wish: bool
    note: str | None
    created_at: int
    updated_at: int


class WorkspaceDeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    player_id: int | None = None
    note: str | None = None
    is_wish: bool = False
    created_at: int | None = Field(default=None, ge=0)


class WorkspaceDeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    player_id: int | None = None
    note: str | None = None
    created_at: int | None = Field(default=None, ge=0)


class WorkspaceDeckItemRead(BaseModel):
    id: int
    collection_item_id: int | None = None
    printing_id: int | None = None
    release_date: int | None = None
    language_code: str | None = None
    collection_id: int | None = None
    collection_name: str | None = None
    set_code: str | None = None
    keyrune_code: str | None = None
    collector_number: str | None = None
    language: str | None = None
    finish_id: int | None = None
    finish: str | None = None
    condition_code: str | None = None
    owned_quantity: int | None = None
    allocated_quantity: int | None = None
    available_quantity: int | None = None
    section: str
    quantity: int
    name: str
    oracle_id: str


class WorkspaceDeckItemCreate(BaseModel):
    collection_item_id: int
    section: DeckSection = "main"
    quantity: int = Field(default=1, ge=1)


class WorkspaceDeckItemUpdate(BaseModel):
    section: DeckSection | None = None
    quantity: int | None = Field(default=None, ge=1)


class WorkspaceDeckItemAllocationRead(BaseModel):
    deck_item_id: int
    deck_id: int
    deck_name: str
    section: str
    quantity: int


class WorkspaceDeckInventoryItemRead(BaseModel):
    collection_item_id: int
    collection_id: int
    collection_name: str
    printing_id: int
    release_date: int
    name: str
    set_code: str
    keyrune_code: str
    collector_number: str
    language_code: str
    language: str
    finish_id: int
    finish: str
    condition_code: str
    owned_quantity: int
    allocated_quantity: int
    available_quantity: int
    allocations: list[WorkspaceDeckItemAllocationRead]


class WorkspaceDeckInventorySearchResultRead(BaseModel):
    oracle_id: str
    name: str
    language_code: str
    total_owned: int
    total_available: int
    items: list[WorkspaceDeckInventoryItemRead]


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


class WorkspaceDeckItemAllocationRemoval(BaseModel):
    deck_item_id: int
    quantity: int = Field(ge=1)


class WorkspaceCollectionItemAttributeUpdate(BaseModel):
    available_quantity: int = Field(default=0, ge=0)
    allocation_selections: list[WorkspaceDeckItemAllocationRemoval] = Field(default_factory=list)
    source_quantity: int = Field(ge=1)
    allocation_signature: str


class WorkspaceCollectionItemUpdate(WorkspaceCollectionItemCreate):
    allocation_removals: list[WorkspaceDeckItemAllocationRemoval] = Field(default_factory=list)
    attribute_update: WorkspaceCollectionItemAttributeUpdate | None = None


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
    allocated_quantity: int
    available_quantity: int
    allocations: list[WorkspaceDeckItemAllocationRead]
    mana_cost: str
    type: str
