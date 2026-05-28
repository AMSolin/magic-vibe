from pydantic import BaseModel, ConfigDict, Field

from app.schemas.collection import CollectionItemRead


class DeckRead(BaseModel):
    id: int
    name: str
    owner_id: int
    note: str | None = None
    is_wishlist: bool
    wishlist_collection_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class DeckItemCreate(BaseModel):
    collection_item_id: int
    quantity: int = Field(default=1, ge=1)
    section: str = "main"
    is_commander: bool = False


class DeckItemRead(DeckItemCreate):
    id: int
    deck_id: int
    collection_item: CollectionItemRead

    model_config = ConfigDict(from_attributes=True)
