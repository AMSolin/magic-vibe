from time import time
from urllib.error import URLError
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.user_data_session import get_user_data_db
from app.models.user_data import Collection, CollectionItem, Deck, DeckItem, Player, WishDeckItem
from app.schemas.workspace import (
    CardDetailsRead,
    CardSuggestionRead,
    PrintingOptionsRead,
    WorkspaceCollectionCreate,
    WorkspaceCollectionItemCreate,
    WorkspaceCollectionItemRead,
    WorkspaceCollectionItemUpdate,
    WorkspaceCollectionRead,
    WorkspaceCollectionUpdate,
    WorkspaceDeckCreate,
    WorkspaceDeckInventoryItemRead,
    WorkspaceDeckInventorySearchResultRead,
    WorkspaceDeckItemCreate,
    WorkspaceDeckItemRead,
    WorkspaceDeckItemUpdate,
    WorkspaceDeckRead,
    WorkspaceDeckUpdate,
    WorkspacePlayerCreate,
    WorkspacePlayerRead,
    WorkspacePlayerUpdate,
)
from app.services import catalog, scryfall

router = APIRouter()


def _catalog_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(error),
    )


def _scryfall_error(error: Exception) -> HTTPException:
    if isinstance(error, URLError):
        detail = "Scryfall is unavailable. Try again later or use already cached card data."
    else:
        detail = str(error)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
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
        oracle_id=printing["oracle_id"],
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


def _validated_item_identity(
    payload: WorkspaceCollectionItemCreate,
) -> tuple[bytes, str]:
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
    return UUID(printing["scryfall_id"]).bytes, selected_language_code


def _assign_replacement_default(
    db: Session,
    excluded_collection_id: int,
) -> Collection | None:
    replacement = db.scalar(
        select(Collection)
        .where(
            Collection.id != excluded_collection_id,
            Collection.is_wishlist.is_(False),
        )
        .order_by(Collection.created_at, Collection.id)
        .limit(1)
    )
    if replacement is not None:
        replacement.is_default = True
    return replacement


def _ensure_default_collection(db: Session, collection: Collection) -> None:
    if not collection.is_default:
        return
    if collection.is_wishlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wishlist collection cannot be primary",
        )
    for other_collection in db.scalars(
        select(Collection).where(
            Collection.id != collection.id,
            Collection.is_default.is_(True),
        )
    ):
        other_collection.is_default = False


def _commit_collection(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this name already exists",
        ) from error


def _ensure_default_player(db: Session, player: Player) -> None:
    if not player.is_default:
        return
    for other_player in db.scalars(
        select(Player).where(Player.id != player.id, Player.is_default.is_(True))
    ):
        other_player.is_default = False


def _make_default_player(db: Session, player: Player) -> None:
    for other_player in db.scalars(
        select(Player).where(Player.id != player.id, Player.is_default.is_(True))
    ):
        other_player.is_default = False
    db.flush()
    player.is_default = True


def _assign_replacement_default_player(db: Session, excluded_player_id: int) -> Player | None:
    replacement = db.scalar(
        select(Player)
        .where(Player.id != excluded_player_id)
        .order_by(Player.created_at, Player.id)
        .limit(1)
    )
    if replacement is not None:
        replacement.is_default = True
    return replacement


def _commit_player(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player with this name already exists",
        ) from error


def _commit_deck(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deck with this name already exists for this owner and deck type",
        ) from error


def _allocated_quantity(
    db: Session,
    collection_item_id: int,
    *,
    excluded_deck_item_id: int | None = None,
) -> int:
    statement = select(func.coalesce(func.sum(DeckItem.quantity), 0)).where(
        DeckItem.collection_item_id == collection_item_id
    )
    if excluded_deck_item_id is not None:
        statement = statement.where(DeckItem.id != excluded_deck_item_id)
    return db.scalar(statement) or 0


def _load_physical_deck_item(db: Session, deck_id: int, item_id: int) -> tuple[Deck, DeckItem]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_physical_deck(deck)
    item = db.scalar(
        select(DeckItem).where(
            DeckItem.id == item_id,
            DeckItem.deck_id == deck.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck item not found")
    return deck, item


def _allocation_breakdown(
    db: Session,
    collection_item_ids: list[int],
) -> dict[int, list[dict]]:
    if not collection_item_ids:
        return {}
    rows = db.execute(
        select(
            DeckItem.collection_item_id,
            DeckItem.deck_id,
            Deck.name,
            DeckItem.section,
            DeckItem.quantity,
        )
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(DeckItem.collection_item_id.in_(collection_item_ids))
        .order_by(Deck.name, DeckItem.section, DeckItem.id)
    ).all()
    breakdown: dict[int, list[dict]] = {}
    for collection_item_id, deck_id, deck_name, section, quantity in rows:
        breakdown.setdefault(collection_item_id, []).append(
            {
                "deck_id": deck_id,
                "deck_name": deck_name,
                "section": section,
                "quantity": quantity,
            }
        )
    return breakdown


def _inventory_item_read(
    item: CollectionItem,
    printing: dict,
    allocations: list[dict],
    display_language_code: str | None = None,
    display_name: str | None = None,
) -> WorkspaceDeckInventoryItemRead:
    try:
        finish = catalog.finish_name(item.finish_id)
        language = catalog.language_name(item.language_code)
        faces = catalog.get_localized_printing_faces(
            printing["id"],
            display_language_code or item.language_code,
        )
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if finish is None or language is None or not faces:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection item no longer resolves to the installed catalog",
        )
    allocated_quantity = sum(allocation["quantity"] for allocation in allocations)
    return WorkspaceDeckInventoryItemRead(
        collection_item_id=item.id,
        collection_id=item.collection_id,
        collection_name=item.collection.name,
        printing_id=printing["id"],
        release_date=printing["release_date"],
        name=display_name or faces[0]["name"],
        set_code=printing["set_code"],
        keyrune_code=printing["keyrune_code"],
        collector_number=printing["collector_number"],
        language_code=item.language_code,
        language=language,
        finish_id=item.finish_id,
        finish=finish,
        condition_code=item.condition_code,
        owned_quantity=item.quantity,
        allocated_quantity=allocated_quantity,
        available_quantity=max(0, item.quantity - allocated_quantity),
        allocations=allocations,
    )


def _deck_item_read(db: Session, item: DeckItem) -> WorkspaceDeckItemRead:
    try:
        printing = catalog.get_printing_by_scryfall_id(item.collection_item.scryfall_id)
        finish = catalog.finish_name(item.collection_item.finish_id)
        language = catalog.language_name(item.collection_item.language_code)
        faces = (
            catalog.get_localized_printing_faces(
                printing["id"],
                item.collection_item.language_code,
            )
            if printing
            else []
        )
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    if printing is None or finish is None or language is None or not faces:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deck item no longer resolves to the installed catalog",
        )
    allocated_quantity = _allocated_quantity(db, item.collection_item_id)
    return WorkspaceDeckItemRead(
        id=item.id,
        collection_item_id=item.collection_item_id,
        printing_id=printing["id"],
        release_date=printing["release_date"],
        language_code=item.collection_item.language_code,
        collection_id=item.collection_item.collection_id,
        collection_name=item.collection_item.collection.name,
        set_code=printing["set_code"],
        keyrune_code=printing["keyrune_code"],
        collector_number=printing["collector_number"],
        language=language,
        finish_id=item.collection_item.finish_id,
        finish=finish,
        condition_code=item.collection_item.condition_code,
        owned_quantity=item.collection_item.quantity,
        allocated_quantity=allocated_quantity,
        available_quantity=max(0, item.collection_item.quantity - allocated_quantity),
        section=item.section,
        quantity=item.quantity,
        name=faces[0]["name"],
        oracle_id=printing["oracle_id"],
    )


def _ensure_physical_deck(deck: Deck) -> None:
    if deck.is_wish:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wish deck items are not implemented yet",
        )


def _cached_oracle_image(
    printing: dict,
    *,
    version: str,
    face_order: int,
    language_code: str,
) -> tuple[object, str] | None:
    try:
        printings = catalog.list_printings(printing["oracle_id"])
    except (FileNotFoundError, ValueError):
        return None

    def priority(item: dict) -> tuple[int, int]:
        item_language = item["language_code"]
        if item_language == language_code:
            language_rank = 0
        elif item_language == "en":
            language_rank = 1
        else:
            language_rank = 2
        return language_rank, -int(item["release_date"])

    for candidate in sorted(printings, key=priority):
        cached_image = scryfall.get_cached_card_image(
            scryfall_id=candidate["scryfall_id"],
            version=version,
            face_order=face_order,
        )
        if cached_image is not None:
            return cached_image
    return None


@router.get("/players", response_model=list[WorkspacePlayerRead])
def list_players(db: Session = Depends(get_user_data_db)) -> list[Player]:
    return list(db.scalars(select(Player).order_by(Player.created_at, Player.name)))


@router.post("/players", response_model=WorkspacePlayerRead, status_code=status.HTTP_201_CREATED)
def create_player(
    payload: WorkspacePlayerCreate,
    db: Session = Depends(get_user_data_db),
) -> Player:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is required")
    requested_default = payload.is_default
    player = Player(
        name=name,
        is_default=False,
        created_at=payload.created_at if payload.created_at is not None else int(time()),
    )
    db.add(player)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player with this name already exists",
        ) from error
    should_be_default = requested_default or (
        db.scalar(select(Player.id).where(Player.id != player.id, Player.is_default.is_(True)))
        is None
    )
    if should_be_default:
        _make_default_player(db, player)
    _commit_player(db)
    db.refresh(player)
    return player


@router.patch("/players/{player_id}", response_model=WorkspacePlayerRead)
def update_player(
    player_id: int,
    payload: WorkspacePlayerUpdate,
    db: Session = Depends(get_user_data_db),
) -> Player:
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        update_data["name"] = update_data["name"].strip()
        if not update_data["name"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name is required",
            )
    was_default = player.is_default
    requested_default = update_data.pop("is_default", None)
    for field, value in update_data.items():
        setattr(player, field, value)
    if requested_default is True:
        _make_default_player(db, player)
    elif requested_default is False:
        if player.is_default:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose another preferred player before clearing this one",
            )
        player.is_default = False
    if was_default and not player.is_default:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose another preferred player before clearing this one",
        )
    _ensure_default_player(db, player)
    _commit_player(db)
    db.refresh(player)
    return player


@router.delete("/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_player(
    player_id: int,
    confirm_collection_owner_clear: bool = False,
    db: Session = Depends(get_user_data_db),
) -> None:
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    if db.scalar(select(Player.id).where(Player.id != player.id).limit(1)) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one player must remain",
        )
    affected_collections = list(
        db.scalars(
            select(Collection)
            .where(Collection.player_id == player.id)
            .order_by(Collection.created_at, Collection.name)
        )
    )
    affected_decks = list(
        db.scalars(
            select(Deck)
            .where(Deck.player_id == player.id)
            .order_by(Deck.created_at, Deck.name)
        )
    )
    if (affected_collections or affected_decks) and not confirm_collection_owner_clear:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Player owns collections or decks",
                "collections": [
                    {"id": collection.id, "name": collection.name}
                    for collection in affected_collections
                ],
                "decks": [{"id": deck.id, "name": deck.name} for deck in affected_decks],
            },
        )
    replacement = (
        db.scalar(
            select(Player)
            .where(Player.id != player.id)
            .order_by(Player.created_at, Player.id)
            .limit(1)
        )
        if player.is_default
        else None
    )
    for collection in affected_collections:
        collection.player_id = None
    for deck in affected_decks:
        deck.player_id = None
    db.delete(player)
    db.flush()
    if replacement is not None:
        replacement.is_default = True
    db.commit()


@router.get("/collections", response_model=list[WorkspaceCollectionRead])
def list_collections(db: Session = Depends(get_user_data_db)) -> list[Collection]:
    return list(db.scalars(select(Collection).order_by(Collection.created_at, Collection.name)))


@router.get("/decks", response_model=list[WorkspaceDeckRead])
def list_decks(db: Session = Depends(get_user_data_db)) -> list[Deck]:
    return list(db.scalars(select(Deck).order_by(Deck.created_at, Deck.name)))


@router.post("/decks", response_model=WorkspaceDeckRead, status_code=status.HTTP_201_CREATED)
def create_deck(
    payload: WorkspaceDeckCreate,
    db: Session = Depends(get_user_data_db),
) -> Deck:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is required")
    if payload.player_id is not None and db.get(Player, payload.player_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    created_at = payload.created_at if payload.created_at is not None else int(time())
    deck = Deck(
        player_id=payload.player_id,
        name=name,
        note=payload.note,
        is_wish=payload.is_wish,
        created_at=created_at,
        updated_at=int(time()),
    )
    db.add(deck)
    _commit_deck(db)
    db.refresh(deck)
    return deck


@router.patch("/decks/{deck_id}", response_model=WorkspaceDeckRead)
def update_deck(
    deck_id: int,
    payload: WorkspaceDeckUpdate,
    db: Session = Depends(get_user_data_db),
) -> Deck:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        update_data["name"] = update_data["name"].strip()
        if not update_data["name"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name is required",
            )
    if (
        "player_id" in update_data
        and update_data["player_id"] is not None
        and db.get(Player, update_data["player_id"]) is None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    for field, value in update_data.items():
        setattr(deck, field, value)
    deck.updated_at = int(time())
    _commit_deck(db)
    db.refresh(deck)
    return deck


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, db: Session = Depends(get_user_data_db)) -> None:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    db.delete(deck)
    db.commit()


@router.get("/decks/{deck_id}/items", response_model=list[WorkspaceDeckItemRead])
def list_deck_items(
    deck_id: int,
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceDeckItemRead]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    if deck.is_wish:
        items = list(
            db.scalars(
                select(WishDeckItem)
                .where(WishDeckItem.deck_id == deck.id)
                .order_by(WishDeckItem.section, WishDeckItem.id)
            )
        )
        return [
            WorkspaceDeckItemRead(
                id=item.id,
                section=item.section,
                quantity=item.quantity,
                name="Card",
                oracle_id=str(UUID(bytes=item.oracle_id)),
            )
            for item in items
        ]
    items = list(
        db.scalars(
            select(DeckItem)
            .where(DeckItem.deck_id == deck.id)
            .order_by(DeckItem.section, DeckItem.id)
        )
    )
    return [_deck_item_read(db, item) for item in items]


@router.get(
    "/decks/{deck_id}/items/search",
    response_model=list[WorkspaceDeckInventorySearchResultRead],
)
def search_physical_deck_inventory(
    deck_id: int,
    query: str = Query(default="", max_length=255),
    oracle_id: str | None = Query(default=None),
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceDeckInventorySearchResultRead]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_physical_deck(deck)
    search_text = query.strip()
    target_oracle_id = oracle_id.strip() if oracle_id else None
    if target_oracle_id:
        try:
            UUID(target_oracle_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid oracle_id",
            ) from error
    if not search_text and target_oracle_id is None:
        return []
    matching_language_by_oracle_id: dict[str, str] = {}
    matching_name_by_oracle_id: dict[str, str] = {}
    if target_oracle_id is None:
        try:
            suggestions = catalog.search_card_names(search_text, exact=False, limit=50)
        except FileNotFoundError as error:
            raise _catalog_error(error) from error
        for suggestion in suggestions:
            matching_language_by_oracle_id.setdefault(
                suggestion["oracle_id"],
                suggestion["language_code"],
            )
            matching_name_by_oracle_id.setdefault(suggestion["oracle_id"], suggestion["name"])
    matching_oracle_ids = (
        {target_oracle_id}
        if target_oracle_id is not None
        else set(matching_language_by_oracle_id)
    )
    if not matching_oracle_ids:
        return []
    items = list(
        db.scalars(
            select(CollectionItem)
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.is_wishlist.is_(False))
            .order_by(Collection.name, CollectionItem.created_at.desc(), CollectionItem.id.desc())
        )
    )
    try:
        printings = catalog.get_printings_by_scryfall_ids([item.scryfall_id for item in items])
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    allocations = _allocation_breakdown(db, [item.id for item in items])
    grouped: dict[str, WorkspaceDeckInventorySearchResultRead] = {}
    for item in items:
        printing = printings.get(item.scryfall_id)
        if printing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Collection item no longer resolves to the installed catalog",
            )
        if printing["oracle_id"] not in matching_oracle_ids:
            continue
        inventory_item = _inventory_item_read(
            item,
            printing,
            allocations.get(item.id, []),
            display_language_code=matching_language_by_oracle_id.get(printing["oracle_id"]),
            display_name=matching_name_by_oracle_id.get(printing["oracle_id"]),
        )
        result = grouped.get(printing["oracle_id"])
        if result is None:
            result = WorkspaceDeckInventorySearchResultRead(
                oracle_id=printing["oracle_id"],
                name=inventory_item.name,
                language_code=(
                    matching_language_by_oracle_id.get(printing["oracle_id"])
                    or inventory_item.language_code
                ),
                total_owned=0,
                total_available=0,
                items=[],
            )
            grouped[printing["oracle_id"]] = result
        result.total_owned += inventory_item.owned_quantity
        result.total_available += inventory_item.available_quantity
        result.items.append(inventory_item)
    return sorted(
        grouped.values(),
        key=lambda result: (result.name.casefold(), result.oracle_id),
    )[:50]


@router.post(
    "/decks/{deck_id}/items",
    response_model=WorkspaceDeckItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_deck_item(
    deck_id: int,
    payload: WorkspaceDeckItemCreate,
    db: Session = Depends(get_user_data_db),
) -> WorkspaceDeckItemRead:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_physical_deck(deck)
    collection_item = db.get(CollectionItem, payload.collection_item_id)
    if collection_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")
    if collection_item.collection.is_wishlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Physical decks can use only regular collection cards",
        )
    allocated_quantity = _allocated_quantity(db, collection_item.id)
    if allocated_quantity + payload.quantity > collection_item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough available copies in collection",
        )
    item = db.scalar(
        select(DeckItem).where(
            DeckItem.deck_id == deck.id,
            DeckItem.collection_item_id == collection_item.id,
            DeckItem.section == payload.section,
        )
    )
    if item is None:
        item = DeckItem(
            deck_id=deck.id,
            collection_item_id=collection_item.id,
            section=payload.section,
            quantity=payload.quantity,
        )
        db.add(item)
    else:
        item.quantity += payload.quantity
    deck.updated_at = int(time())
    db.commit()
    db.refresh(item)
    return _deck_item_read(db, item)


@router.patch(
    "/decks/{deck_id}/items/{item_id}",
    response_model=WorkspaceDeckItemRead,
)
def update_deck_item(
    deck_id: int,
    item_id: int,
    payload: WorkspaceDeckItemUpdate,
    db: Session = Depends(get_user_data_db),
) -> WorkspaceDeckItemRead:
    deck, item = _load_physical_deck_item(db, deck_id, item_id)
    update_data = payload.model_dump(exclude_unset=True)
    target_section = update_data.get("section", item.section)
    if target_section != item.section:
        move_quantity = update_data.get("quantity", item.quantity)
        if move_quantity > item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move more copies than the deck item contains",
            )
        target_item = db.scalar(
            select(DeckItem).where(
                DeckItem.deck_id == deck.id,
                DeckItem.collection_item_id == item.collection_item_id,
                DeckItem.section == target_section,
            )
        )
        if target_item is None:
            if move_quantity == item.quantity:
                item.section = target_section
                target_item = item
            else:
                item.quantity -= move_quantity
                target_item = DeckItem(
                    deck_id=deck.id,
                    collection_item_id=item.collection_item_id,
                    section=target_section,
                    quantity=move_quantity,
                )
                db.add(target_item)
        else:
            target_item.quantity += move_quantity
            if move_quantity == item.quantity:
                db.delete(item)
            else:
                item.quantity -= move_quantity
        item = target_item
    else:
        requested_quantity = update_data.get("quantity", item.quantity)
        allocated_elsewhere = _allocated_quantity(
            db,
            item.collection_item_id,
            excluded_deck_item_id=item.id,
        )
        if allocated_elsewhere + requested_quantity > item.collection_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not enough available copies in collection",
            )
        item.quantity = requested_quantity
    deck.updated_at = int(time())
    db.commit()
    db.refresh(item)
    return _deck_item_read(db, item)


@router.delete(
    "/decks/{deck_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_deck_item(
    deck_id: int,
    item_id: int,
    db: Session = Depends(get_user_data_db),
) -> None:
    deck, item = _load_physical_deck_item(db, deck_id, item_id)
    db.delete(item)
    deck.updated_at = int(time())
    db.commit()


@router.post(
    "/collections",
    response_model=WorkspaceCollectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_collection(
    payload: WorkspaceCollectionCreate,
    db: Session = Depends(get_user_data_db),
) -> Collection:
    if db.get(Player, payload.player_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    if payload.is_default and payload.is_wishlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wishlist collection cannot be primary",
        )
    collection_data = payload.model_dump()
    created_at = collection_data.pop("created_at")
    if created_at is None:
        created_at = int(time())
    collection = Collection(**collection_data, created_at=created_at)
    db.add(collection)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection with this name already exists",
        ) from error
    if (
        not collection.is_wishlist
        and db.scalar(
            select(Collection.id).where(
                Collection.id != collection.id,
                Collection.is_default.is_(True),
            )
        )
        is None
    ):
        collection.is_default = True
    _ensure_default_collection(db, collection)
    _commit_collection(db)
    db.refresh(collection)
    return collection


@router.patch("/collections/{collection_id}", response_model=WorkspaceCollectionRead)
def update_collection(
    collection_id: int,
    payload: WorkspaceCollectionUpdate,
    db: Session = Depends(get_user_data_db),
) -> Collection:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    update_data = payload.model_dump(exclude_unset=True)
    requested_player_id = update_data.get("player_id")
    if requested_player_id is not None and db.get(Player, requested_player_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    was_default = collection.is_default
    requested_default = update_data.pop("is_default", None)
    next_is_default = requested_default if requested_default is not None else collection.is_default
    next_is_wishlist = update_data.get("is_wishlist", collection.is_wishlist)
    if next_is_default and next_is_wishlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wishlist collection cannot be primary",
        )
    for field, value in update_data.items():
        setattr(collection, field, value)
    if was_default and requested_default is False:
        replacement = _assign_replacement_default(db, collection.id)
        if replacement is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot clear the only primary collection",
            )
    if requested_default is True:
        for other_collection in db.scalars(
            select(Collection).where(
                Collection.id != collection.id,
                Collection.is_default.is_(True),
            )
        ):
            other_collection.is_default = False
        db.flush()
        collection.is_default = True
    elif requested_default is False:
        collection.is_default = False
    _ensure_default_collection(db, collection)
    _commit_collection(db)
    db.refresh(collection)
    return collection


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: int,
    db: Session = Depends(get_user_data_db),
) -> None:
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
    if (
        db.scalar(
            select(CollectionItem.id)
            .join(DeckItem, DeckItem.collection_item_id == CollectionItem.id)
            .where(CollectionItem.collection_id == collection.id)
            .limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection contains cards allocated to a deck",
        )
    replacement = None
    if collection.is_default:
        replacement = db.scalar(
            select(Collection)
            .where(
                Collection.id != collection.id,
                Collection.is_wishlist.is_(False),
            )
            .order_by(Collection.created_at, Collection.id)
            .limit(1)
        )
        if replacement is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the only regular collection",
            )
    db.delete(collection)
    db.flush()
    if replacement is not None:
        replacement.is_default = True
    db.commit()


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
        raise _scryfall_error(error) from error
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
    cached_image = scryfall.get_cached_card_image(
        scryfall_id=printing["scryfall_id"],
        version=version,
        face_order=face_order,
    )
    if cached_image is not None:
        image_path, media_type = cached_image
        return FileResponse(image_path, media_type=media_type)
    requested_language_code = language_code or printing["language_code"]
    try:
        card = scryfall.get_card_json_for_image(
            printing["set_code"],
            printing["collector_number"],
            requested_language_code,
        )
        image_path, media_type = scryfall.get_card_image(
            card,
            scryfall_id=str(card.get("id") or printing["scryfall_id"]),
            version=version,
            face_order=face_order,
        )
    except Exception as error:
        cached_oracle_image = _cached_oracle_image(
            printing,
            version=version,
            face_order=face_order,
            language_code=requested_language_code,
        )
        if cached_oracle_image is not None:
            image_path, media_type = cached_oracle_image
            return FileResponse(image_path, media_type=media_type)
        raise _scryfall_error(error) from error
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
    scryfall_id, selected_language_code = _validated_item_identity(payload)
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


@router.patch(
    "/collections/{collection_id}/items/{item_id}",
    response_model=WorkspaceCollectionItemRead,
)
def update_collection_item(
    collection_id: int,
    item_id: int,
    payload: WorkspaceCollectionItemUpdate,
    db: Session = Depends(get_user_data_db),
) -> WorkspaceCollectionItemRead:
    item = db.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")
    scryfall_id, selected_language_code = _validated_item_identity(payload)
    matching_item = db.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.id != item.id,
            CollectionItem.scryfall_id == scryfall_id,
            CollectionItem.finish_id == payload.finish_id,
            CollectionItem.language_code == selected_language_code,
            CollectionItem.condition_code == payload.condition_code,
        )
    )
    if matching_item is None:
        item.scryfall_id = scryfall_id
        item.finish_id = payload.finish_id
        item.language_code = selected_language_code
        item.condition_code = payload.condition_code
        item.quantity = payload.quantity
    else:
        matching_item.quantity += payload.quantity
        db.delete(item)
        item = matching_item
    db.commit()
    db.refresh(item)
    return _item_read(item)


@router.delete(
    "/collections/{collection_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection_item(
    collection_id: int,
    item_id: int,
    db: Session = Depends(get_user_data_db),
) -> None:
    item = db.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")
    db.delete(item)
    db.commit()
