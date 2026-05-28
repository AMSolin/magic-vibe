from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.card import Card
from app.models.collection import Collection, CollectionItem
from app.schemas.collection import CollectionItemCreate, CollectionItemRead, CollectionItemUpdate

router = APIRouter()


def _default_collection(db: Session) -> Collection:
    collection = db.scalar(
        select(Collection).where(Collection.is_default.is_(True), Collection.is_wishlist.is_(False))
    )
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default collection was not initialized",
        )

    return collection


def _collection_item_statement(item_id: int):
    return (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card))
        .where(CollectionItem.id == item_id)
    )


@router.get("", response_model=list[CollectionItemRead])
def list_collection(db: Session = Depends(get_db)) -> list[CollectionItem]:
    collection = _default_collection(db)
    statement = (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card))
        .where(CollectionItem.collection_id == collection.id)
        .order_by(CollectionItem.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(statement))


@router.post("", response_model=CollectionItemRead, status_code=status.HTTP_201_CREATED)
def add_collection_item(
    payload: CollectionItemCreate,
    db: Session = Depends(get_db),
) -> CollectionItem:
    collection = _default_collection(db)
    if db.scalar(select(Card.card_uuid).where(Card.card_uuid == payload.card_uuid)) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    existing_item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection.id,
            CollectionItem.card_uuid == payload.card_uuid,
            CollectionItem.condition_code == payload.condition_code,
            CollectionItem.foil == payload.foil,
            CollectionItem.language == payload.language,
        )
    )
    if existing_item is None:
        item = CollectionItem(collection_id=collection.id, **payload.model_dump())
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


@router.patch("/{item_id}", response_model=CollectionItemRead)
def update_collection_item(
    item_id: int,
    payload: CollectionItemUpdate,
    db: Session = Depends(get_db),
) -> CollectionItem:
    item = db.get(CollectionItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("quantity") == 0:
        db.delete(item)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item removed")

    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    updated_item = db.scalar(_collection_item_statement(item_id))
    if updated_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    return updated_item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(CollectionItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    db.delete(item)
    db.commit()
