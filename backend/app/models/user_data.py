from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.user_data_base import UserDataBase

if TYPE_CHECKING:
    from collections.abc import Sequence


class Player(UserDataBase):
    __tablename__ = "players"
    __table_args__ = (
        Index(
            "uq_players_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    created_at: Mapped[int] = mapped_column(Integer)

    collections: Mapped[list["Collection"]] = relationship(back_populates="player")
    decks: Mapped[list["Deck"]] = relationship(back_populates="player")


class CardCondition(UserDataBase):
    __tablename__ = "card_conditions"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)


class Collection(UserDataBase):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("player_id", "name", name="uq_collections_player_name"),
        CheckConstraint(
            "not (is_default = 1 and is_wishlist = 1)",
            name="ck_collections_default_not_wishlist",
        ),
        Index(
            "uq_collections_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    is_wishlist: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    created_at: Mapped[int] = mapped_column(Integer)

    player: Mapped[Player | None] = relationship(back_populates="collections")
    items: Mapped[list["CollectionItem"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
    )


class CollectionItem(UserDataBase):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "scryfall_id",
            "finish_id",
            "language_code",
            "condition_code",
            name="uq_collection_items_identity",
        ),
        CheckConstraint("length(scryfall_id) = 16", name="ck_collection_items_scryfall_id_length"),
        CheckConstraint("quantity > 0", name="ck_collection_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        index=True,
    )
    scryfall_id: Mapped[bytes] = mapped_column(LargeBinary(16), index=True)
    finish_id: Mapped[int] = mapped_column(Integer)
    language_code: Mapped[str] = mapped_column(String(16))
    condition_code: Mapped[str] = mapped_column(ForeignKey("card_conditions.code"))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer)

    collection: Mapped[Collection] = relationship(back_populates="items")
    deck_items: Mapped[list["DeckItem"]] = relationship(back_populates="collection_item")


class Deck(UserDataBase):
    __tablename__ = "decks"
    __table_args__ = (
        UniqueConstraint("player_id", "is_wish", "name", name="uq_decks_player_type_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    is_wish: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)

    player: Mapped[Player | None] = relationship(back_populates="decks")
    items: Mapped[list["DeckItem"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
    )
    wish_items: Mapped[list["WishDeckItem"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
    )


class DeckItem(UserDataBase):
    __tablename__ = "deck_items"
    __table_args__ = (
        UniqueConstraint("deck_id", "collection_item_id", "section", name="uq_deck_items_identity"),
        CheckConstraint(
            "section in ('main', 'side', 'maybe', 'commander')",
            name="ck_deck_items_section",
        ),
        CheckConstraint("quantity > 0", name="ck_deck_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    collection_item_id: Mapped[int] = mapped_column(ForeignKey("collection_items.id"), index=True)
    section: Mapped[str] = mapped_column(String(32), default="main")
    is_commander: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    quantity: Mapped[int] = mapped_column(Integer)

    deck: Mapped[Deck] = relationship(back_populates="items")
    collection_item: Mapped[CollectionItem] = relationship(back_populates="deck_items")


class WishDeckItem(UserDataBase):
    __tablename__ = "wish_deck_items"
    __table_args__ = (
        UniqueConstraint(
            "deck_id",
            "oracle_id",
            "section",
            name="uq_wish_deck_items_identity",
        ),
        CheckConstraint("length(oracle_id) = 16", name="ck_wish_deck_items_oracle_id_length"),
        CheckConstraint(
            "section in ('main', 'side', 'maybe', 'commander')",
            name="ck_wish_deck_items_section",
        ),
        CheckConstraint("quantity > 0", name="ck_wish_deck_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    oracle_id: Mapped[bytes] = mapped_column(LargeBinary(16), index=True)
    language_code: Mapped[str] = mapped_column(String(16))
    section: Mapped[str] = mapped_column(String(32), default="main")
    quantity: Mapped[int] = mapped_column(Integer)
    linked_collection_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_items.id", ondelete="SET NULL"),
        index=True,
    )
    created_at: Mapped[int] = mapped_column(Integer)

    deck: Mapped[Deck] = relationship(back_populates="wish_items")
    linked_collection_item: Mapped[CollectionItem | None] = relationship()


USER_DATA_MODELS: "Sequence[type[UserDataBase]]" = (
    Player,
    CardCondition,
    Collection,
    CollectionItem,
    Deck,
    DeckItem,
    WishDeckItem,
)
