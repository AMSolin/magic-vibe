from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.card import Card
    from app.models.deck import DeckItem


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_collections_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[int] = mapped_column(default=1)
    note: Mapped[str | None] = mapped_column(String(1024))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_wishlist: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["CollectionItem"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "card_uuid",
            "condition_code",
            "foil",
            "language",
            name="uq_collection_items_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    card_uuid: Mapped[str] = mapped_column(ForeignKey("cards.card_uuid"), index=True)
    condition_code: Mapped[str] = mapped_column(String(16), default="NM")
    foil: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(64), default="English")
    quantity: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    collection: Mapped[Collection] = relationship(back_populates="items")
    card: Mapped["Card"] = relationship(back_populates="collection_items")
    deck_items: Mapped[list["DeckItem"]] = relationship(back_populates="collection_item")

    @property
    def allocated_quantity(self) -> int:
        return sum(deck_item.quantity for deck_item in self.deck_items)

    @property
    def available_quantity(self) -> int:
        return self.quantity - self.allocated_quantity
