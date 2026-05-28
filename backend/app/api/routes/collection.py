from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.card import Card
from app.models.collection import CollectionItem
from app.schemas.collection import CollectionItemCreate, CollectionItemRead

router = APIRouter()


@router.get("", response_model=list[CollectionItemRead])
def list_collection(db: Session = Depends(get_db)) -> list[CollectionItem]:
    statement = (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card))
        .order_by(CollectionItem.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(statement))


@router.post("", response_model=CollectionItemRead, status_code=status.HTTP_201_CREATED)
def add_collection_item(
    payload: CollectionItemCreate,
    db: Session = Depends(get_db),
) -> CollectionItem:
    if db.get(Card, payload.card_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    item = CollectionItem(**payload.model_dump())
    db.add(item)
    db.commit()

    statement = (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card))
        .where(CollectionItem.id == item.id)
    )
    created_item = db.scalar(statement)
    if created_item is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Collection item was not created",
        )

    return created_item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(CollectionItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")

    db.delete(item)
    db.commit()
