from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.card import CardRead


class CollectionItemCreate(BaseModel):
    card_id: int
    quantity: int = Field(default=1, ge=1)
    finish: str = "nonfoil"
    language: str | None = None
    condition: str | None = None
    location: str | None = None


class CollectionItemRead(CollectionItemCreate):
    id: int
    created_at: datetime
    card: CardRead

    model_config = ConfigDict(from_attributes=True)
