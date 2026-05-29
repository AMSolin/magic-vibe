from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.collection import CollectionItemRead

DeckSection = Literal["main", "side", "maybe", "commander"]


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    owner_id: int = Field(default=1, ge=1)
    note: str | None = None
    is_default: bool = False
    is_wishlist: bool = False
    wishlist_collection_id: int | None = None


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    owner_id: int | None = Field(default=None, ge=1)
    note: str | None = None
    is_default: bool | None = None
    is_wishlist: bool | None = None
    wishlist_collection_id: int | None = None
    created_at: datetime | None = None


class DeckRead(BaseModel):
    id: int
    name: str
    owner_id: int
    note: str | None = None
    is_default: bool
    is_wishlist: bool
    wishlist_collection_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeckItemCreate(BaseModel):
    collection_item_id: int
    quantity: int = Field(default=1, ge=1)
    section: DeckSection = "main"
    is_commander: bool = False


class DeckItemUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=0)
    section: DeckSection | None = None
    is_commander: bool | None = None


class DeckItemMove(BaseModel):
    section: DeckSection
    quantity: int | None = Field(default=None, ge=1)


class DeckItemRead(DeckItemCreate):
    id: int
    deck_id: int
    collection_item: CollectionItemRead

    model_config = ConfigDict(from_attributes=True)
