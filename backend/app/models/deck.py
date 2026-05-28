from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.collection import Collection, CollectionItem


class Deck(Base):
    __tablename__ = "decks"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_decks_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[int] = mapped_column(default=1)
    note: Mapped[str | None] = mapped_column(String(1024))
    is_wishlist: Mapped[bool] = mapped_column(Boolean, default=False)
    wishlist_collection_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    wishlist_collection: Mapped["Collection | None"] = relationship()
    items: Mapped[list["DeckItem"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
    )


class DeckItem(Base):
    __tablename__ = "deck_items"
    __table_args__ = (
        UniqueConstraint("deck_id", "collection_item_id", "section", name="uq_deck_items_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id"), index=True)
    collection_item_id: Mapped[int] = mapped_column(ForeignKey("collection_items.id"), index=True)
    section: Mapped[str] = mapped_column(String(32), default="main")
    is_commander: Mapped[bool] = mapped_column(Boolean, default=False)
    quantity: Mapped[int] = mapped_column(default=1)

    deck: Mapped[Deck] = relationship(back_populates="items")
    collection_item: Mapped["CollectionItem"] = relationship(back_populates="deck_items")
