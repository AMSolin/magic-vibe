from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.collection import CollectionItem
from app.models.deck import Deck, DeckItem
from app.schemas.deck import DeckItemCreate, DeckItemRead, DeckRead

router = APIRouter()


@router.get("", response_model=list[DeckRead])
def list_decks(db: Session = Depends(get_db)) -> list[Deck]:
    return list(db.scalars(select(Deck).order_by(Deck.created_at, Deck.name)))


@router.get("/{deck_id}/items", response_model=list[DeckItemRead])
def list_deck_items(deck_id: int, db: Session = Depends(get_db)) -> list[DeckItem]:
    if db.get(Deck, deck_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")

    statement = (
        select(DeckItem)
        .options(selectinload(DeckItem.collection_item).selectinload(CollectionItem.card))
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

    collection_item = db.get(CollectionItem, payload.collection_item_id)
    if collection_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

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

    existing_item = db.scalar(
        select(DeckItem).where(
            DeckItem.deck_id == deck_id,
            DeckItem.collection_item_id == payload.collection_item_id,
            DeckItem.section == payload.section,
        )
    )
    existing_quantity = existing_item.quantity if existing_item is not None else 0
    allocated_statement = select(func.coalesce(func.sum(DeckItem.quantity), 0)).where(
        DeckItem.collection_item_id == payload.collection_item_id
    )
    if existing_item is not None:
        allocated_statement = allocated_statement.where(DeckItem.id != existing_item.id)

    allocated_elsewhere = db.scalar(allocated_statement)
    requested_total = allocated_elsewhere + existing_quantity + payload.quantity
    if requested_total > collection_item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough available copies in collection",
        )

    if existing_item is None:
        item = DeckItem(deck_id=deck_id, **payload.model_dump())
        db.add(item)
        db.commit()
        item_id = item.id
    else:
        existing_item.quantity += payload.quantity
        db.commit()
        item_id = existing_item.id

    statement = (
        select(DeckItem)
        .options(selectinload(DeckItem.collection_item).selectinload(CollectionItem.card))
        .where(DeckItem.id == item_id)
    )
    created_or_updated_item = db.scalar(statement)
    if created_or_updated_item is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deck item was not created",
        )

    return created_or_updated_item
