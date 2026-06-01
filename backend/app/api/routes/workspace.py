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


@router.get("/symbols")
def list_symbols() -> dict:
    manifest = scryfall.get_symbols_manifest()
    return {
        symbol: {
            "image_url": f"/api/workspace/symbols/svg/{item['file']}",
            "label": item["english"],
        }
        for symbol, item in manifest["symbols"].items()
    }


@router.get("/symbols/svg/{filename}")
def get_symbol_svg(filename: str) -> FileResponse:
    path = scryfall.get_symbol_file(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Symbol not found")
    return FileResponse(path, media_type="image/svg+xml")


def _required_printing(printing_id: int) -> dict:
    try:
        printing = catalog.get_printing(printing_id)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if printing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printing not found")
    return printing


def _localized_card_details(printing_id: int, card: dict, language_code: str | None = None) -> dict:
    faces = catalog.get_localized_printing_faces(printing_id, language_code)
    if len(faces) == 1:
        face = faces[0]
        card.update(
            {
                "printed_name": face["name"],
                "mana_cost": face["mana_cost"],
                "printed_type_line": face["type_line"],
                "printed_text": face["oracle_text"],
                "flavor_text": face["flavor_text"],
            }
        )
        return card

    card_faces = card.get("card_faces")
    if isinstance(card_faces, list):
        for face, localized_face in zip(card_faces, faces, strict=False):
            face.update(
                {
                    "printed_name": localized_face["name"],
                    "mana_cost": localized_face["mana_cost"],
                    "printed_type_line": localized_face["type_line"],
                    "printed_text": localized_face["oracle_text"],
                    "flavor_text": localized_face["flavor_text"],
                }
            )
    return card


def _item_read(item: CollectionItem) -> WorkspaceCollectionItemRead:
    try:
        printing = catalog.get_printing_by_scryfall_id(item.scryfall_id)
        finish = catalog.finish_name(item.finish_id)
        language = catalog.language_name(item.language_code)
        faces = catalog.get_localized_printing_faces(printing["id"], item.language_code) if printing else []
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if printing is None or finish is None or language is None or not faces:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection item no longer resolves to the installed catalog",
        )
    return WorkspaceCollectionItemRead(
        id=item.id,
        printing_id=printing["id"],
        collection_id=item.collection_id,
        scryfall_id=printing["scryfall_id"],
        name=faces[0]["name"],
        set_code=printing["set_code"],
        keyrune_code=printing["keyrune_code"],
        rarity=printing["rarity"],
        collector_number=printing["collector_number"],
        language_code=item.language_code,
        language=language,
        finish_id=item.finish_id,
        finish=finish,
        condition_code=item.condition_code,
        quantity=item.quantity,
        mana_cost=printing["mana_cost"],
        type=faces[0]["type_line"],
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
def get_printing_details(
    printing_id: int,
    language_code: str | None = Query(default=None, min_length=2, max_length=3),
) -> CardDetailsRead:
    printing = _required_printing(printing_id)
    requested_language_code = language_code or printing["language_code"]
    try:
        card = scryfall.get_card_json(
            printing["set_code"],
            printing["collector_number"],
            printing["language_code"],
        )
        card = _localized_card_details(printing_id, card, requested_language_code)
    except Exception as error:
        raise _catalog_error(error) from error
    language_query = f"?language_code={requested_language_code}"
    return CardDetailsRead(
        printing_id=printing_id,
        image_normal_url=f"/api/workspace/printings/{printing_id}/images/normal{language_query}",
        image_native_url=f"/api/workspace/printings/{printing_id}/images/png{language_query}",
        card=card,
    )


@router.get("/printings/{printing_id}/images/{version}")
def get_printing_image(
    printing_id: int,
    version: str,
    face_order: int = 0,
    language_code: str | None = Query(default=None, min_length=2, max_length=3),
) -> FileResponse:
    if version not in {"small", "normal", "large", "png"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image version not found")
    if face_order < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card face not found")
    printing = _required_printing(printing_id)
    try:
        card = scryfall.get_card_json_for_image(
            printing["set_code"],
            printing["collector_number"],
            language_code or printing["language_code"],
        )
        image_path, media_type = scryfall.get_card_image(
            card,
            scryfall_id=str(card.get("id") or printing["scryfall_id"]),
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
    selected_language_code = payload.language_code or printing["language_code"]
    try:
        finish_supported = catalog.printing_supports_finish(payload.printing_id, payload.finish_id)
        language_supported = catalog.printing_supports_language(
            payload.printing_id,
            selected_language_code,
        )
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if not finish_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Finish is not available for this printing",
        )
    if not language_supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Language is not available for this printing",
        )

    scryfall_id = UUID(printing["scryfall_id"]).bytes
    item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.scryfall_id == scryfall_id,
            CollectionItem.finish_id == payload.finish_id,
            CollectionItem.language_code == selected_language_code,
            CollectionItem.condition_code == payload.condition_code,
        )
    )
    if item is None:
        item = CollectionItem(
            collection_id=collection_id,
            scryfall_id=scryfall_id,
            finish_id=payload.finish_id,
            language_code=selected_language_code,
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
