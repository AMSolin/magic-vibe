from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.card import Card


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    finish: Mapped[str] = mapped_column(String(32), default="nonfoil")
    language: Mapped[str | None] = mapped_column(String(16))
    condition: Mapped[str | None] = mapped_column(String(32))
    location: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    card: Mapped[Card] = relationship(back_populates="collection_items")
