from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.collection import Collection, CollectionItem
from app.models.deck import Deck, DeckItem
from app.schemas.deck import (
    DeckCreate,
    DeckItemCreate,
    DeckItemMove,
    DeckItemRead,
    DeckItemUpdate,
    DeckRead,
    DeckUpdate,
)

router = APIRouter()


def _validate_wishlist_settings(
    db: Session,
    is_wishlist: bool,
    wishlist_collection_id: int | None,
) -> None:
    if is_wishlist:
        if wishlist_collection_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wish deck must reference a wishlist collection",
            )

        wishlist_collection = db.get(Collection, wishlist_collection_id)
        if wishlist_collection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wishlist collection not found",
            )
        if not wishlist_collection.is_wishlist:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wish deck must reference a wishlist collection",
            )
    elif wishlist_collection_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Regular deck cannot reference a wishlist collection",
        )


def _ensure_default_deck(db: Session, deck: Deck) -> None:
    if not deck.is_default:
        return

    other_default_decks = db.scalars(
        select(Deck).where(
            Deck.owner_id == deck.owner_id,
            Deck.id != deck.id,
            Deck.is_default.is_(True),
        )
    )
    for other_deck in other_default_decks:
        other_deck.is_default = False


def _assign_replacement_default(db: Session, owner_id: int, excluded_deck_id: int) -> Deck | None:
    replacement_deck = db.scalar(
        select(Deck)
        .where(Deck.owner_id == owner_id, Deck.id != excluded_deck_id)
        .order_by(Deck.created_at, Deck.id)
        .limit(1)
    )
    if replacement_deck is not None:
        replacement_deck.is_default = True
    return replacement_deck


def _validate_existing_items_for_deck(deck: Deck) -> None:
    for item in deck.items:
        _validate_deck_collection_item(deck, item.collection_item)


def _deck_item_statement(item_id: int):
    return (
        select(DeckItem)
        .options(
            selectinload(DeckItem.collection_item).selectinload(CollectionItem.card),
            selectinload(DeckItem.collection_item).selectinload(CollectionItem.deck_items),
        )
        .where(DeckItem.id == item_id)
    )


def _validate_deck_collection_item(deck: Deck, collection_item: CollectionItem) -> None:
    if deck.is_wishlist:
        if collection_item.collection_id != deck.wishlist_collection_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wish deck items must come from the linked wishlist collection",
            )
    elif collection_item.collection.is_wishlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Regular deck items must come from a regular collection",
        )


def _ensure_available_quantity(
    collection_item: CollectionItem,
    requested_item_quantity: int,
    db: Session,
    excluded_deck_item_id: int | None = None,
) -> None:
    allocated_statement = select(func.coalesce(func.sum(DeckItem.quantity), 0)).where(
        DeckItem.collection_item_id == collection_item.id
    )
    if excluded_deck_item_id is not None:
        allocated_statement = allocated_statement.where(DeckItem.id != excluded_deck_item_id)

    allocated_elsewhere = db.scalar(allocated_statement) or 0
    requested_total = allocated_elsewhere + requested_item_quantity
    if requested_total > collection_item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough available copies in collection",
        )


def _load_deck_item(item_id: int, deck_id: int, db: Session) -> DeckItem:
    item = db.get(DeckItem, item_id)
    if item is None or item.deck_id != deck_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck item not found")

    return item


def _create_deck_item(
    deck: Deck,
    payload: DeckItemCreate,
    db: Session,
) -> DeckItem:
    collection_item = db.get(CollectionItem, payload.collection_item_id)
    if collection_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    _validate_deck_collection_item(deck, collection_item)

    existing_item = db.scalar(
        select(DeckItem).where(
            DeckItem.deck_id == deck.id,
            DeckItem.collection_item_id == payload.collection_item_id,
            DeckItem.section == payload.section,
        )
    )
    existing_quantity = existing_item.quantity if existing_item is not None else 0
    excluded_item_id = existing_item.id if existing_item is not None else None
    _ensure_available_quantity(
        collection_item,
        existing_quantity + payload.quantity,
        db,
        excluded_item_id,
    )

    if existing_item is None:
        item = DeckItem(deck_id=deck.id, **payload.model_dump())
        db.add(item)
        db.commit()
        item_id = item.id
    else:
        existing_item.quantity += payload.quantity
        existing_item.is_commander = payload.is_commander
        db.commit()
        item_id = existing_item.id

    created_or_updated_item = db.scalar(_deck_item_statement(item_id))
    if created_or_updated_item is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deck item was not created",
        )

    return created_or_updated_item


@router.post("", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def create_deck(payload: DeckCreate, db: Session = Depends(get_db)) -> Deck:
    _validate_wishlist_settings(db, payload.is_wishlist, payload.wishlist_collection_id)

    deck = Deck(**payload.model_dump())
    db.add(deck)
    try:
        db.flush()
        if (
            db.scalar(
                select(Deck.id).where(
                    Deck.owner_id == deck.owner_id,
                    Deck.id != deck.id,
                    Deck.is_default.is_(True),
                )
            )
            is None
        ):
            deck.is_default = True
        _ensure_default_deck(db, deck)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deck with this name already exists",
        ) from exc

    db.refresh(deck)
    return deck


@router.patch("/{deck_id}", response_model=DeckRead)
def update_deck(
    deck_id: int,
    payload: DeckUpdate,
    db: Session = Depends(get_db),
) -> Deck:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    update_data = payload.model_dump(exclude_unset=True)
    previous_owner_id = deck.owner_id
    was_default = deck.is_default
    target_is_wishlist = update_data.get("is_wishlist", deck.is_wishlist)
    target_wishlist_collection_id = update_data.get(
        "wishlist_collection_id",
        deck.wishlist_collection_id,
    )
    if not target_is_wishlist:
        target_wishlist_collection_id = None
        update_data["wishlist_collection_id"] = None

    _validate_wishlist_settings(db, target_is_wishlist, target_wishlist_collection_id)

    for field, value in update_data.items():
        setattr(deck, field, value)

    if was_default and (not deck.is_default or deck.owner_id != previous_owner_id):
        replacement_deck = _assign_replacement_default(db, previous_owner_id, deck.id)
        if replacement_deck is None and deck.owner_id == previous_owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot clear the only primary deck",
            )
    _validate_existing_items_for_deck(deck)
    _ensure_default_deck(db, deck)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deck with this name already exists",
        ) from exc

    db.refresh(deck)
    return deck


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, db: Session = Depends(get_db)) -> None:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    remaining_decks = list(
        db.scalars(select(Deck).where(Deck.id != deck.id).order_by(Deck.created_at, Deck.id))
    )
    if not remaining_decks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only deck",
        )

    if deck.is_default:
        replacement_deck = next(
            (remaining_deck for remaining_deck in remaining_decks if remaining_deck.owner_id == deck.owner_id),
            remaining_decks[0],
        )
        replacement_deck.is_default = True

    db.delete(deck)
    db.commit()


@router.get("", response_model=list[DeckRead])
def list_decks(db: Session = Depends(get_db)) -> list[Deck]:
    return list(db.scalars(select(Deck).order_by(Deck.created_at, Deck.name)))


@router.get("/{deck_id}/items", response_model=list[DeckItemRead])
def list_deck_items(deck_id: int, db: Session = Depends(get_db)) -> list[DeckItem]:
    if db.get(Deck, deck_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    statement = (
        select(DeckItem)
        .options(
            selectinload(DeckItem.collection_item).selectinload(CollectionItem.card),
            selectinload(DeckItem.collection_item).selectinload(CollectionItem.deck_items),
        )
        .where(DeckItem.deck_id == deck_id)
        .order_by(DeckItem.section, DeckItem.id)
    )
    return list(db.scalars(statement))


@router.post("/{deck_id}/items", response_model=DeckItemRead, status_code=status.HTTP_201_CREATED)
def add_deck_item(
    deck_id: int,
    payload: DeckItemCreate,
    db: Session = Depends(get_db),
) -> DeckItem:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    return _create_deck_item(deck, payload, db)


@router.patch("/{deck_id}/items/{item_id}", response_model=DeckItemRead)
def update_deck_item(
    deck_id: int,
    item_id: int,
    payload: DeckItemUpdate,
    db: Session = Depends(get_db),
) -> DeckItem:
    if db.get(Deck, deck_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    item = _load_deck_item(item_id, deck_id, db)
    update_data = payload.model_dump(exclude_unset=True)
    requested_quantity = update_data.get("quantity", item.quantity)

    if requested_quantity == 0:
        db.delete(item)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck item removed")

    _ensure_available_quantity(
        item.collection_item,
        requested_quantity,
        db,
        excluded_deck_item_id=item.id,
    )

    for field, value in update_data.items():
        setattr(item, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deck item with this identity already exists",
        ) from exc

    updated_item = db.scalar(_deck_item_statement(item.id))
    if updated_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck item not found")

    return updated_item


@router.post("/{deck_id}/items/{item_id}/move", response_model=DeckItemRead)
def move_deck_item(
    deck_id: int,
    item_id: int,
    payload: DeckItemMove,
    db: Session = Depends(get_db),
) -> DeckItem:
    if db.get(Deck, deck_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    item = _load_deck_item(item_id, deck_id, db)
    move_quantity = payload.quantity or item.quantity
    if move_quantity > item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot move more copies than the deck item contains",
        )
    if payload.section == item.section:
        return db.scalar(_deck_item_statement(item.id)) or item

    target_item = db.scalar(
        select(DeckItem).where(
            DeckItem.deck_id == deck_id,
            DeckItem.collection_item_id == item.collection_item_id,
            DeckItem.section == payload.section,
        )
    )
    if target_item is None:
        target_item = DeckItem(
            deck_id=deck_id,
            collection_item_id=item.collection_item_id,
            section=payload.section,
            is_commander=item.is_commander,
            quantity=move_quantity,
        )
        db.add(target_item)
    else:
        target_item.quantity += move_quantity
        target_item.is_commander = target_item.is_commander or item.is_commander

    if move_quantity == item.quantity:
        db.delete(item)
    else:
        item.quantity -= move_quantity

    db.commit()
    moved_item = db.scalar(_deck_item_statement(target_item.id))
    if moved_item is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deck item was not moved",
        )

    return moved_item


@router.delete("/{deck_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck_item(
    deck_id: int,
    item_id: int,
    db: Session = Depends(get_db),
) -> None:
    if db.get(Deck, deck_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    item = _load_deck_item(item_id, deck_id, db)
    db.delete(item)
    db.commit()
