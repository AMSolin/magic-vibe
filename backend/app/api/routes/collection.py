from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.collection import Collection, CollectionItem
from app.api.routes.collections import (
    _create_or_increment_collection_item,
    _delete_collection_item,
    _update_collection_item,
)
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
        .options(selectinload(CollectionItem.card), selectinload(CollectionItem.deck_items))
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
    return _create_or_increment_collection_item(collection.id, payload, db)


@router.patch("/{item_id}", response_model=CollectionItemRead)
def update_collection_item(
    item_id: int,
    payload: CollectionItemUpdate,
    db: Session = Depends(get_db),
) -> CollectionItem:
    item = db.get(CollectionItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    return _update_collection_item(item, payload, db)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(CollectionItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    _delete_collection_item(item, db)
