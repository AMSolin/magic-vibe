from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.card import Card
from app.models.collection import Collection, CollectionItem
from app.models.deck import Deck, DeckItem
from app.schemas.collection import (
    CollectionCreate,
    CollectionItemCreate,
    CollectionItemMove,
    CollectionItemRead,
    CollectionItemUpdate,
    CollectionRead,
    CollectionUpdate,
)

router = APIRouter()


def _ensure_default_collection(db: Session, collection: Collection) -> None:
    if not collection.is_default:
        return
    if collection.is_wishlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wishlist collection cannot be primary",
        )

    other_default_collections = db.scalars(
        select(Collection).where(
            Collection.owner_id == collection.owner_id,
            Collection.id != collection.id,
            Collection.is_default.is_(True),
        )
    )
    for other_collection in other_default_collections:
        other_collection.is_default = False


def _assign_replacement_default(
    db: Session,
    owner_id: int,
    excluded_collection_id: int,
) -> Collection | None:
    replacement_collection = db.scalar(
        select(Collection)
        .where(
            Collection.owner_id == owner_id,
            Collection.id != excluded_collection_id,
            Collection.is_wishlist.is_(False),
        )
        .order_by(Collection.created_at, Collection.id)
        .limit(1)
    )
    if replacement_collection is not None:
        replacement_collection.is_default = True
    return replacement_collection


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
        db.flush()
        if (
            not collection.is_wishlist
            and db.scalar(
                select(Collection.id).where(
                    Collection.owner_id == collection.owner_id,
                    Collection.id != collection.id,
                    Collection.is_default.is_(True),
                )
            )
            is None
        ):
            collection.is_default = True
        _ensure_default_collection(db, collection)
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

    update_data = payload.model_dump(exclude_unset=True)
    previous_owner_id = collection.owner_id
    was_default = collection.is_default

    for field, value in update_data.items():
        setattr(collection, field, value)

    if was_default and (not collection.is_default or collection.owner_id != previous_owner_id):
        replacement_collection = _assign_replacement_default(db, previous_owner_id, collection.id)
        if replacement_collection is None and collection.owner_id == previous_owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot clear the only primary collection",
            )
    _ensure_default_collection(db, collection)

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


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: int, db: Session = Depends(get_db)) -> None:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    remaining_collections = list(
        db.scalars(
            select(Collection)
            .where(Collection.id != collection.id)
            .order_by(Collection.created_at, Collection.id)
        )
    )
    if not remaining_collections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only collection",
        )
    if db.scalar(select(Deck.id).where(Deck.wishlist_collection_id == collection.id)) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection is linked to a wish deck",
        )
    allocated_item_id = db.scalar(
        select(CollectionItem.id)
        .join(DeckItem, DeckItem.collection_item_id == CollectionItem.id)
        .where(CollectionItem.collection_id == collection.id)
        .limit(1)
    )
    if allocated_item_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection contains cards allocated to a deck",
        )

    if collection.is_default:
        replacement_collection = next(
            (
                remaining_collection
                for remaining_collection in remaining_collections
                if remaining_collection.owner_id == collection.owner_id
                and not remaining_collection.is_wishlist
            ),
            next(
                (
                    remaining_collection
                    for remaining_collection in remaining_collections
                    if not remaining_collection.is_wishlist
                ),
                None,
            ),
        )
        if replacement_collection is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the only regular collection",
            )
        replacement_collection.is_default = True

    db.delete(collection)
    db.commit()


@router.get("/{collection_id}/items", response_model=list[CollectionItemRead])
def list_collection_items(
    collection_id: int,
    response: Response,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[CollectionItem]:
    if db.get(Collection, collection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    total_items = db.scalar(
        select(func.count()).select_from(CollectionItem).where(CollectionItem.collection_id == collection_id)
    )
    total_cards = db.scalar(
        select(func.coalesce(func.sum(CollectionItem.quantity), 0)).where(
            CollectionItem.collection_id == collection_id
        )
    )
    response.headers["X-Total-Count"] = str(total_items or 0)
    response.headers["X-Total-Cards"] = str(total_cards or 0)

    statement = (
        select(CollectionItem)
        .options(selectinload(CollectionItem.card), selectinload(CollectionItem.deck_items))
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.created_at.desc(), CollectionItem.id.desc())
        .offset(offset)
        .limit(limit)
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


@router.post("/{collection_id}/items/{item_id}/move", response_model=CollectionItemRead)
def move_collection_item(
    collection_id: int,
    item_id: int,
    payload: CollectionItemMove,
    db: Session = Depends(get_db),
) -> CollectionItem:
    item = db.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")
    if _allocated_quantity(db, item.id) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allocated collection item cannot be moved",
        )

    target_collection = db.get(Collection, payload.collection_id)
    if target_collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    if target_collection.id == item.collection_id:
        return db.scalar(_collection_item_statement(item.id)) or item

    target_item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == target_collection.id,
            CollectionItem.card_uuid == item.card_uuid,
            CollectionItem.condition_code == item.condition_code,
            CollectionItem.foil == item.foil,
            CollectionItem.language == item.language,
        )
    )
    if target_item is None:
        item.collection_id = target_collection.id
        moved_item_id = item.id
    else:
        target_item.quantity += item.quantity
        moved_item_id = target_item.id
        db.delete(item)

    db.commit()
    moved_item = db.scalar(_collection_item_statement(moved_item_id))
    if moved_item is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Collection item was not moved",
        )

    return moved_item
