from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.card import Card
from app.models.collection import Collection, CollectionItem
from app.models.deck import DeckItem
from app.schemas.collection import (
    CollectionCreate,
    CollectionItemCreate,
    CollectionItemRead,
    CollectionItemUpdate,
    CollectionRead,
    CollectionUpdate,
)

router = APIRouter()


def _collection_item_statement(item_id: int):
    return (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card), selectinload(CollectionItem.deck_items))
        .where(CollectionItem.id == item_id)
    )


def _allocated_quantity_statement(collection_item_id: int):
    return select(func.coalesce(func.sum(DeckItem.quantity), 0)).where(
        DeckItem.collection_item_id == collection_item_id
    )


def _allocated_quantity(db: Session, collection_item_id: int) -> int:
    return db.scalar(_allocated_quantity_statement(collection_item_id)) or 0


def _ensure_card_exists(db: Session, card_uuid: str) -> None:
    if db.scalar(select(Card.card_uuid).where(Card.card_uuid == card_uuid)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")


def _create_or_increment_collection_item(
    collection_id: int,
    payload: CollectionItemCreate,
    db: Session,
) -> CollectionItem:
    _ensure_card_exists(db, payload.card_uuid)

    existing_item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.card_uuid == payload.card_uuid,
            CollectionItem.condition_code == payload.condition_code,
            CollectionItem.foil == payload.foil,
            CollectionItem.language == payload.language,
        )
    )
    if existing_item is None:
        item = CollectionItem(collection_id=collection_id, **payload.model_dump())
        db.add(item)
        db.commit()
        item_id = item.id
    else:
        existing_item.quantity += payload.quantity
        db.commit()
        item_id = existing_item.id

    created_or_updated_item = db.scalar(_collection_item_statement(item_id))
    if created_or_updated_item is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Collection item was not created",
        )

    return created_or_updated_item


def _update_collection_item(
    item: CollectionItem,
    payload: CollectionItemUpdate,
    db: Session,
) -> CollectionItem:
    update_data = payload.model_dump(exclude_unset=True)
    requested_quantity = update_data.get("quantity")
    allocated_quantity = _allocated_quantity(db, item.id)

    if requested_quantity is not None and requested_quantity < allocated_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection item quantity cannot be lower than allocated deck quantity",
        )

    if requested_quantity == 0:
        db.delete(item)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item removed")

    for field, value in update_data.items():
        setattr(item, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection item with this identity already exists",
        ) from exc

    updated_item = db.scalar(_collection_item_statement(item.id))
    if updated_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    return updated_item


def _delete_collection_item(item: CollectionItem, db: Session) -> None:
    if _allocated_quantity(db, item.id) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection item is allocated to a deck",
        )

    db.delete(item)
    db.commit()


@router.get("", response_model=list[CollectionRead])
def list_collections(db: Session = Depends(get_db)) -> list[Collection]:
    return list(db.scalars(select(Collection).order_by(Collection.created_at, Collection.name)))


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionCreate,
    db: Session = Depends(get_db),
) -> Collection:
    collection = Collection(**payload.model_dump())
    db.add(collection)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this name already exists",
        ) from exc

    db.refresh(collection)
    return collection


@router.patch("/{collection_id}", response_model=CollectionRead)
def update_collection(
    collection_id: int,
    payload: CollectionUpdate,
    db: Session = Depends(get_db),
) -> Collection:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(collection, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this name already exists",
        ) from exc

    db.refresh(collection)
    return collection


@router.get("/{collection_id}/items", response_model=list[CollectionItemRead])
def list_collection_items(
    collection_id: int,
    db: Session = Depends(get_db),
) -> list[CollectionItem]:
    if db.get(Collection, collection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    statement = (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card), selectinload(CollectionItem.deck_items))
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(statement))


@router.post(
    "/{collection_id}/items",
    response_model=CollectionItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_collection_item(
    collection_id: int,
    payload: CollectionItemCreate,
    db: Session = Depends(get_db),
) -> CollectionItem:
    if db.get(Collection, collection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    return _create_or_increment_collection_item(collection_id, payload, db)


@router.patch("/{collection_id}/items/{item_id}", response_model=CollectionItemRead)
def update_collection_item(
    collection_id: int,
    item_id: int,
    payload: CollectionItemUpdate,
    db: Session = Depends(get_db),
) -> CollectionItem:
    item = db.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    return _update_collection_item(item, payload, db)


@router.delete("/{collection_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_item(
    collection_id: int,
    item_id: int,
    db: Session = Depends(get_db),
) -> None:
    item = db.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    _delete_collection_item(item, db)
