from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.collection import CollectionItem


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    scryfall_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    mana_cost: Mapped[str | None] = mapped_column(String(64))
    type_line: Mapped[str | None] = mapped_column(String(255))
    oracle_text: Mapped[str | None] = mapped_column(Text)
    image_small: Mapped[str | None] = mapped_column(String(512))
    image_normal: Mapped[str | None] = mapped_column(String(512))

    collection_items: Mapped[list["CollectionItem"]] = relationship(back_populates="card")
