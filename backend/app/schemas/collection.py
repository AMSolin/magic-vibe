from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.card import CardRead


class CollectionRead(BaseModel):
    id: int
    name: str
    owner_id: int
    note: str | None = None
    is_default: bool
    is_wishlist: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CollectionItemCreate(BaseModel):
    card_uuid: str
    quantity: int = Field(default=1, ge=1)
    condition_code: str = "NM"
    foil: bool = False
    language: str = "English"


class CollectionItemUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=0)
    condition_code: str | None = None
    foil: bool | None = None
    language: str | None = None


class CollectionItemRead(BaseModel):
    id: int
    collection_id: int
    card_uuid: str
    quantity: int
    condition_code: str
    foil: bool
    language: str
    created_at: datetime
    card: CardRead

    model_config = ConfigDict(from_attributes=True)
