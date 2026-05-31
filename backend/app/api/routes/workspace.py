from time import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.user_data_session import get_user_data_db
from app.models.user_data import Collection, CollectionItem
from app.schemas.workspace import (
    CardDetailsRead,
    CardSuggestionRead,
    PrintingOptionsRead,
    WorkspaceCollectionItemCreate,
    WorkspaceCollectionItemRead,
    WorkspaceCollectionRead,
)
from app.services import catalog, scryfall

router = APIRouter()


def _catalog_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(error),
    )


def _required_printing(printing_id: int) -> dict:
    try:
        printing = catalog.get_printing(printing_id)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if printing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printing not found")
    return printing


def _item_read(item: CollectionItem) -> WorkspaceCollectionItemRead:
    try:
        printing = catalog.get_printing_by_scryfall_id(item.scryfall_id)
        finish = catalog.finish_name(item.finish_id)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if printing is None or finish is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection item no longer resolves to the installed catalog",
        )
    return WorkspaceCollectionItemRead(
        id=item.id,
        collection_id=item.collection_id,
        scryfall_id=printing["scryfall_id"],
        name=printing["name"],
        set_code=printing["set_code"],
        collector_number=printing["collector_number"],
        language_code=printing["language_code"],
        language=printing["language"],
        finish_id=item.finish_id,
        finish=finish,
        condition_code=item.condition_code,
        quantity=item.quantity,
        mana_cost=printing["mana_cost"],
        type=printing["type"],
    )


@router.get("/collections", response_model=list[WorkspaceCollectionRead])
def list_collections(db: Session = Depends(get_user_data_db)) -> list[Collection]:
    return list(db.scalars(select(Collection).order_by(Collection.created_at, Collection.name)))


@router.get("/cards/suggest", response_model=list[CardSuggestionRead])
def suggest_cards(
    query: str = Query(min_length=1),
    exact: bool = False,
) -> list[dict]:
    try:
        return catalog.search_card_names(query, exact=exact)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error


@router.get("/cards/{oracle_id}/printings", response_model=PrintingOptionsRead)
def get_card_printings(
    oracle_id: str,
    preferred_language_code: str,
) -> PrintingOptionsRead:
    try:
        printings = catalog.list_printings(oracle_id)
    except (FileNotFoundError, ValueError) as error:
        raise _catalog_error(error) from error
    return PrintingOptionsRead(
        oracle_id=oracle_id,
        preferred_language_code=preferred_language_code,
        printings=printings,
    )


@router.get("/printings/{printing_id}/details", response_model=CardDetailsRead)
def get_printing_details(printing_id: int) -> CardDetailsRead:
    printing = _required_printing(printing_id)
    try:
        card = scryfall.get_card_json(
            printing["set_code"],
            printing["collector_number"],
            printing["language_code"],
        )
    except Exception as error:
        raise _catalog_error(error) from error
    return CardDetailsRead(
        printing_id=printing_id,
        image_normal_url=f"/api/workspace/printings/{printing_id}/images/normal",
        image_native_url=f"/api/workspace/printings/{printing_id}/images/png",
        card=card,
    )


@router.get("/printings/{printing_id}/images/{version}")
def get_printing_image(printing_id: int, version: str, face_order: int = 0) -> FileResponse:
    if version not in {"small", "normal", "large", "png"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image version not found")
    if face_order < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card face not found")
    printing = _required_printing(printing_id)
    try:
        card = scryfall.get_card_json(
            printing["set_code"],
            printing["collector_number"],
            printing["language_code"],
        )
        image_path, media_type = scryfall.get_card_image(
            card,
            scryfall_id=printing["scryfall_id"],
            version=version,
            face_order=face_order,
        )
    except Exception as error:
        raise _catalog_error(error) from error
    return FileResponse(image_path, media_type=media_type)


@router.get(
    "/collections/{collection_id}/items",
    response_model=list[WorkspaceCollectionItemRead],
)
def list_collection_items(
    collection_id: int,
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceCollectionItemRead]:
    if db.get(Collection, collection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    items = db.scalars(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.created_at.desc(), CollectionItem.id.desc())
    )
    return [_item_read(item) for item in items]


@router.post(
    "/collections/{collection_id}/items",
    response_model=WorkspaceCollectionItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_collection_item(
    collection_id: int,
    payload: WorkspaceCollectionItemCreate,
    db: Session = Depends(get_user_data_db),
) -> WorkspaceCollectionItemRead:
    if db.get(Collection, collection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    printing = _required_printing(payload.printing_id)
    try:
        finish_supported = catalog.printing_supports_finish(payload.printing_id, payload.finish_id)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if not finish_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Finish is not available for this printing",
        )

    scryfall_id = UUID(printing["scryfall_id"]).bytes
    item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.scryfall_id == scryfall_id,
            CollectionItem.finish_id == payload.finish_id,
            CollectionItem.language_code == printing["language_code"],
            CollectionItem.condition_code == payload.condition_code,
        )
    )
    if item is None:
        item = CollectionItem(
            collection_id=collection_id,
            scryfall_id=scryfall_id,
            finish_id=payload.finish_id,
            language_code=printing["language_code"],
            condition_code=payload.condition_code,
            quantity=payload.quantity,
            created_at=int(time()),
        )
        db.add(item)
    else:
        item.quantity += payload.quantity
    db.commit()
    db.refresh(item)
    return _item_read(item)
