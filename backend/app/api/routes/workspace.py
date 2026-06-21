import re
import sqlite3
from pathlib import Path
from time import time
from urllib.error import URLError
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
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
    WorkspaceWishDeckItemCreate,
    WorkspaceWishDeckItemRead,
    WorkspaceWishDeckItemUpdate,
    WorkspaceWishDeckSearchResultRead,
    WorkspacePlayerCreate,
    WorkspacePlayerRead,
    WorkspacePlayerUpdate,
)
from app.services import catalog, scryfall

router = APIRouter()


def _sqlite_path_from_url(url: str) -> str | None:
    if not url.startswith("sqlite:///"):
        return None
    path = url.removeprefix("sqlite:///")
    if path in {"", ":memory:"}:
        return None
    return path


def _attached_catalog_connection(db: Session) -> sqlite3.Connection | None:
    user_database_path = _sqlite_path_from_url(settings.user_database_url)
    if user_database_path is None:
        return None
    bind = db.get_bind()
    session_database_path = getattr(getattr(bind, "url", None), "database", None)
    if session_database_path is None:
        return None
    if Path(session_database_path).resolve() != Path(user_database_path).resolve():
        return None
    catalog_database_path = catalog.catalog_database_path()
    user_path = str(Path(user_database_path).resolve())
    catalog_path = str(catalog_database_path.resolve())
    connection = sqlite3.connect(user_path)
    connection.row_factory = sqlite3.Row
    connection.create_function(
        "unicode_casefold",
        1,
        lambda value: value.casefold(),
        deterministic=True,
    )
    connection.execute("attach database ? as catalog", (catalog_path,))
    return connection


def _can_use_attached_catalog(db: Session) -> bool:
    connection = _attached_catalog_connection(db)
    if connection is None:
        return False
    connection.close()
    return True


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


def _catalog_card_details(printing: dict, language_code: str | None = None) -> dict:
    faces = catalog.get_localized_printing_faces(printing["id"], language_code)
    if len(faces) == 1:
        face = faces[0]
        return {
            "id": printing["scryfall_id"],
            "name": printing["name"],
            "printed_name": face["name"],
            "mana_cost": face["mana_cost"],
            "type_line": face["type_line"],
            "printed_type_line": face["type_line"],
            "oracle_text": face["oracle_text"],
            "printed_text": face["oracle_text"],
            "flavor_text": face["flavor_text"],
        }
    return {
        "id": printing["scryfall_id"],
        "name": printing["name"],
        "card_faces": [
            {
                "name": face["name"],
                "printed_name": face["name"],
                "mana_cost": face["mana_cost"],
                "type_line": face["type_line"],
                "printed_type_line": face["type_line"],
                "oracle_text": face["oracle_text"],
                "printed_text": face["oracle_text"],
                "flavor_text": face["flavor_text"],
            }
            for face in faces
        ],
    }


def _item_read(db: Session, item: CollectionItem) -> WorkspaceCollectionItemRead:
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
    allocations = _allocation_breakdown(db, [item.id]).get(item.id, [])
    allocated_quantity = sum(allocation["quantity"] for allocation in allocations)
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
        allocated_quantity=allocated_quantity,
        available_quantity=max(0, item.quantity - allocated_quantity),
        allocations=allocations,
        mana_cost=printing["mana_cost"],
        type=faces[0]["type_line"],
    )


def _items_read(db: Session, items: list[CollectionItem]) -> list[WorkspaceCollectionItemRead]:
    if not items:
        return []
    try:
        printings = catalog.get_printings_by_scryfall_ids(
            list(dict.fromkeys(item.scryfall_id for item in items))
        )
        finishes = catalog.finish_names(list({item.finish_id for item in items}))
        languages = catalog.language_names(list({item.language_code for item in items}))
        face_requests = [
            (printing["id"], item.language_code)
            for item in items
            if (printing := printings.get(item.scryfall_id)) is not None
        ]
        faces_by_request = catalog.get_localized_printing_faces_many(face_requests)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error

    allocation_breakdown = _allocation_breakdown(db, [item.id for item in items])
    reads: list[WorkspaceCollectionItemRead] = []
    for item in items:
        printing = printings.get(item.scryfall_id)
        finish = finishes.get(item.finish_id)
        language = languages.get(item.language_code)
        faces = faces_by_request.get((printing["id"], item.language_code), []) if printing else []
        if printing is None or finish is None or language is None or not faces:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Collection item no longer resolves to the installed catalog",
            )
        item_allocations = allocation_breakdown.get(item.id, [])
        allocated_quantity = sum(allocation["quantity"] for allocation in item_allocations)
        reads.append(
            WorkspaceCollectionItemRead(
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
                allocated_quantity=allocated_quantity,
                available_quantity=max(0, item.quantity - allocated_quantity),
                allocations=item_allocations,
                mana_cost=printing["mana_cost"],
                type=faces[0]["type_line"],
            )
        )
    created_at_by_id = {item.id: item.created_at for item in items}
    reads.sort(
        key=lambda read: (
            read.name.casefold(),
            -created_at_by_id[read.id],
        )
    )
    return reads


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
            detail="Deck with this name already exists for this owner",
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


def _load_wish_deck_item(db: Session, deck_id: int, item_id: int) -> tuple[Deck, WishDeckItem]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_wish_deck(deck)
    item = db.scalar(
        select(WishDeckItem).where(
            WishDeckItem.id == item_id,
            WishDeckItem.deck_id == deck.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wish deck item not found")
    return deck, item


def _allocation_breakdown(
    db: Session,
    collection_item_ids: list[int],
) -> dict[int, list[dict]]:
    if not collection_item_ids:
        return {}
    rows = []
    for offset in range(0, len(collection_item_ids), 500):
        chunk = collection_item_ids[offset : offset + 500]
        rows.extend(
            db.execute(
                select(
                    DeckItem.collection_item_id,
                    DeckItem.id,
                    DeckItem.deck_id,
                    Deck.name,
                    DeckItem.section,
                    DeckItem.quantity,
                )
                .join(Deck, Deck.id == DeckItem.deck_id)
                .where(DeckItem.collection_item_id.in_(chunk))
                .order_by(Deck.name, DeckItem.section, DeckItem.id)
            ).all()
    )
    breakdown: dict[int, list[dict]] = {}
    for collection_item_id, deck_item_id, deck_id, deck_name, section, quantity in rows:
        breakdown.setdefault(collection_item_id, []).append(
            {
                "deck_item_id": deck_item_id,
                "deck_id": deck_id,
                "deck_name": deck_name,
                "section": section,
                "quantity": quantity,
            }
        )
    return breakdown


def _collection_allocation_summary(
    db: Session,
    collection_id: int,
) -> tuple[list[dict], str]:
    rows = db.execute(
        select(
            CollectionItem.id,
            CollectionItem.scryfall_id,
            DeckItem.id,
            DeckItem.deck_id,
            Deck.name,
            DeckItem.section,
            DeckItem.quantity,
        )
        .join(DeckItem, DeckItem.collection_item_id == CollectionItem.id)
        .join(Deck, Deck.id == DeckItem.deck_id)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.id, Deck.name, DeckItem.section, DeckItem.id)
    ).all()
    signature = "|".join(
        f"{deck_item_id}:{quantity}"
        for _item_id, _scryfall_id, deck_item_id, _deck_id, _deck_name, _section, quantity in sorted(
            rows,
            key=lambda row: row[2],
        )
    )
    if not rows:
        return [], signature
    try:
        printings = catalog.get_printings_by_scryfall_ids(
            list({scryfall_id for _item_id, scryfall_id, *_rest in rows})
        )
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    item_summaries: dict[int, dict] = {}
    for item_id, scryfall_id, deck_item_id, deck_id, deck_name, section, quantity in rows:
        item_summary = item_summaries.get(item_id)
        if item_summary is None:
            printing = printings.get(scryfall_id)
            if printing is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Collection item no longer resolves to the installed catalog",
                )
            item_summary = {
                "collection_item_id": item_id,
                "name": printing["name"],
                "allocations": [],
            }
            item_summaries[item_id] = item_summary
        item_summary["allocations"].append(
            {
                "deck_item_id": deck_item_id,
                "deck_id": deck_id,
                "deck_name": deck_name,
                "section": section,
                "quantity": quantity,
            }
        )
    return list(item_summaries.values()), signature


def _matches_color_filters(
    row: dict,
    *,
    selected_colors: list[str],
    color_match: str,
    has_uncolored_mana: bool,
    has_colorless_mana: bool,
    has_generic_mana: bool,
    no_colors: bool,
) -> bool:
    selected_color_set = {
        color.upper() for color in selected_colors if color.upper() in {"W", "U", "B", "R", "G"}
    }
    identity = {
        color
        for color in (row.get("oracle_color_identities") or "")
        if color in {"W", "U", "B", "R", "G"}
    }
    mana_cost = row.get("oracle_mana_cost") or ""
    if no_colors and identity:
        return False
    has_colorless_symbol = "{C}" in mana_cost
    has_generic_symbol = any(
        symbol.strip("{}").isdigit() or symbol.upper() == "{X}"
        for symbol in re.findall(r"\{[^}]+\}", mana_cost)
    )
    has_requested_mana_symbol = bool(
        (has_uncolored_mana and (has_colorless_symbol or has_generic_symbol))
        or (has_colorless_mana and has_colorless_symbol)
        or (has_generic_mana and has_generic_symbol)
    )
    needs_requested_mana_symbol = has_uncolored_mana or has_colorless_mana or has_generic_mana
    if selected_color_set:
        if color_match == "includes_any":
            color_matches = bool(identity & selected_color_set)
            return color_matches or has_requested_mana_symbol
        if color_match == "exactly":
            return identity == selected_color_set and (
                has_requested_mana_symbol if needs_requested_mana_symbol else True
            )
        return selected_color_set <= identity and (
            has_requested_mana_symbol if needs_requested_mana_symbol else True
        )
    if needs_requested_mana_symbol:
        if color_match == "exactly":
            return not identity and has_requested_mana_symbol
        return has_requested_mana_symbol
    return True


def _attached_inventory_item_read(
    row: dict,
    allocations: list[dict] | None = None,
    *,
    display_name: str | None = None,
) -> WorkspaceDeckInventoryItemRead:
    allocated_quantity = (
        int(row["allocated_quantity"])
        if "allocated_quantity" in row
        else sum(allocation["quantity"] for allocation in allocations or [])
    )
    return WorkspaceDeckInventoryItemRead(
        collection_item_id=row["collection_item_id"],
        collection_id=row["collection_id"],
        collection_name=row["collection_name"],
        printing_id=row["printing_id"],
        release_date=row["release_date"],
        name=display_name or row["localized_name"],
        set_code=row["set_code"],
        keyrune_code=row["keyrune_code"],
        collector_number=row["collector_number"],
        language_code=row["item_language_code"],
        language=row["language"],
        finish_id=row["finish_id"],
        finish=row["finish"],
        condition_code=row["condition_code"],
        owned_quantity=row["owned_quantity"],
        allocated_quantity=allocated_quantity,
        available_quantity=max(0, row["owned_quantity"] - allocated_quantity),
        allocations=allocations or [],
    )


def _attached_collection_item_read(
    row: dict,
    allocations: list[dict] | None = None,
) -> WorkspaceCollectionItemRead:
    allocated_quantity = int(row["allocated_quantity"])
    return WorkspaceCollectionItemRead(
        id=row["collection_item_id"],
        printing_id=row["printing_id"],
        collection_id=row["collection_id"],
        scryfall_id=row["scryfall_id"],
        oracle_id=row["oracle_id"],
        name=row["localized_name"],
        set_code=row["set_code"],
        keyrune_code=row["keyrune_code"],
        rarity=row["rarity"],
        collector_number=row["collector_number"],
        language_code=row["item_language_code"],
        language=row["language"],
        finish_id=row["finish_id"],
        finish=row["finish"],
        condition_code=row["condition_code"],
        quantity=row["owned_quantity"],
        allocated_quantity=allocated_quantity,
        available_quantity=max(0, row["owned_quantity"] - allocated_quantity),
        allocations=allocations or [],
        mana_cost=row["mana_cost"],
        type=row["type_line"],
    )


def _attached_deck_item_read(row: dict) -> WorkspaceDeckItemRead:
    allocated_quantity = int(row["allocated_quantity"])
    return WorkspaceDeckItemRead(
        id=row["deck_item_id"],
        collection_item_id=row["collection_item_id"],
        printing_id=row["printing_id"],
        release_date=row["release_date"],
        language_code=row["item_language_code"],
        collection_id=row["collection_id"],
        collection_name=row["collection_name"],
        set_code=row["set_code"],
        keyrune_code=row["keyrune_code"],
        collector_number=row["collector_number"],
        language=row["language"],
        finish_id=row["finish_id"],
        finish=row["finish"],
        condition_code=row["condition_code"],
        owned_quantity=row["owned_quantity"],
        allocated_quantity=allocated_quantity,
        available_quantity=max(0, row["owned_quantity"] - allocated_quantity),
        section=row["section"],
        quantity=row["deck_quantity"],
        name=row["localized_name"],
        oracle_id=row["oracle_id"],
    )


ATTACHED_ITEM_SELECT_BASE = """
    ci.id as collection_item_id,
    ci.collection_id,
    c.name as collection_name,
    ci.quantity as owned_quantity,
    ci.finish_id,
    ci.language_code as item_language_code,
    ci.condition_code,
    p.id as printing_id,
    p.scryfall_id,
    p.oracle_id,
    p.set_code,
    p.collector_number,
    p.language_code as printing_language_code,
    p.name as printing_name,
    p.rarity,
    f.mana_cost,
    f.mana_value,
    f.type as type_line,
    coalesce(l.face_name, l.name, f.face_name, p.name) as localized_name,
    s.keyrune_code,
    s.release_date,
    lang.name as language,
    fin.name as finish
"""


ATTACHED_CANDIDATE_SELECT_BASE = """
    ci.id as collection_item_id,
    ci.collection_id,
    c.name as collection_name,
    ci.quantity as owned_quantity,
    ci.finish_id,
    ci.language_code as item_language_code,
    ci.condition_code,
    p.id as printing_id,
    p.scryfall_id,
    p.oracle_id,
    p.set_code,
    p.collector_number,
    p.language_code as printing_language_code,
    p.name as printing_name,
    p.rarity,
    f.mana_cost,
    f.mana_value,
    f.type as type_line,
    s.keyrune_code,
    s.release_date
"""


ATTACHED_ORACLE_FILTER_SELECT = """
    oracle_filter.color_identities as oracle_color_identities,
    oracle_filter.mana_cost as oracle_mana_cost
"""


ATTACHED_ITEM_JOINS_BASIC = """
    join collections as c on c.id = ci.collection_id
    join catalog.card_printings as p on p.scryfall_id = ci.scryfall_id
    join catalog.card_printing_faces as f
        on f.printing_id = p.id
        and f.face_order = (
            select min(face_order)
            from catalog.card_printing_faces
            where printing_id = p.id
        )
    left join catalog.card_face_localizations as l
        on l.face_id = f.id and l.language_code = ci.language_code
    join catalog.sets as s on s.code = p.set_code
    join catalog.languages as lang on lang.code = ci.language_code
    join catalog.finishes as fin on fin.id = ci.finish_id
"""


ATTACHED_CANDIDATE_JOINS_BASIC = """
    join collections as c on c.id = ci.collection_id
    join catalog.card_printings as p on p.scryfall_id = ci.scryfall_id
    join catalog.card_printing_faces as f
        on f.printing_id = p.id
        and f.face_order = (
            select min(face_order)
            from catalog.card_printing_faces
            where printing_id = p.id
        )
    join catalog.sets as s on s.code = p.set_code
"""


ATTACHED_ORACLE_FILTER_JOIN = """
    join (
        select
            p2.oracle_id,
            group_concat(distinct f2.color_identity) as color_identities,
            group_concat(f2.mana_cost, '') as mana_cost
        from catalog.card_printings as p2
        join catalog.card_printing_faces as f2 on f2.printing_id = p2.id
        group by p2.oracle_id
    ) as oracle_filter on oracle_filter.oracle_id = p.oracle_id
"""


def _attached_inventory_candidates(
    db: Session,
    *,
    search_text: str = "",
    search_field: str = "name",
    rarities: set[str],
    mana_value_min: float | None,
    mana_value_max: float | None,
    selected_colors: list[str] | None = None,
    color_match: str = "includes_all",
    has_uncolored_mana: bool = False,
    has_colorless_mana: bool = False,
    has_generic_mana: bool = False,
    no_colors: bool = False,
) -> list[dict] | None:
    normalized_search_text = search_text.casefold()
    params: list[object] = []
    filters = ["c.is_wishlist = 0"]
    has_color_filter = bool(
        selected_colors
        or has_uncolored_mana
        or has_colorless_mana
        or has_generic_mana
        or no_colors
    )
    select_columns = ATTACHED_CANDIDATE_SELECT_BASE
    joins = ATTACHED_CANDIDATE_JOINS_BASIC
    if has_color_filter:
        select_columns = f"{ATTACHED_CANDIDATE_SELECT_BASE}, {ATTACHED_ORACLE_FILTER_SELECT}"
        joins = f"{ATTACHED_CANDIDATE_JOINS_BASIC} {ATTACHED_ORACLE_FILTER_JOIN}"
    if normalized_search_text:
        if search_field == "name":
            search_match = "unicode_casefold(name) >= ? and unicode_casefold(name) < ?"
            search_params = [normalized_search_text, f"{normalized_search_text}\U0010ffff"]
        else:
            search_match = f"unicode_casefold({search_field}) like ?"
            search_params = [f"%{normalized_search_text}%"]
        select_columns = (
            f"{select_columns}, "
            "search_match.matched_language_code, search_match.matched_name, "
            "search_match.matched_search_priority"
        )
        joins = f"""
            {joins}
            join (
                select
                    oracle_id,
                    language_code as matched_language_code,
                    name as matched_name,
                    search_priority as matched_search_priority
                from (
                    select
                        oracle_id,
                        language_code,
                        name,
                        search_priority,
                        row_number() over (
                            partition by oracle_id
                            order by search_priority, name collate nocase, language_code
                        ) as match_rank
                    from catalog.card_search_index
                    where {search_match}
                )
                where match_rank = 1
            ) as search_match on search_match.oracle_id = p.oracle_id
        """
        params.extend(search_params)
    if rarities:
        filters.append(f"unicode_casefold(p.rarity) in ({','.join('?' for _ in rarities)})")
        params.extend(sorted(rarities))
    if mana_value_min is not None:
        filters.append("f.mana_value >= ?")
        params.append(mana_value_min)
    if mana_value_max is not None:
        filters.append("f.mana_value <= ?")
        params.append(mana_value_max)
    selected_color_set = {
        color.upper() for color in selected_colors or [] if color.upper() in {"W", "U", "B", "R", "G"}
    }
    if selected_color_set and color_match in {"includes_all", "exactly"}:
        for color in sorted(selected_color_set):
            filters.append("instr(oracle_filter.color_identities, ?) > 0")
            params.append(color)
    elif (
        selected_color_set
        and color_match == "includes_any"
        and not (has_uncolored_mana or has_colorless_mana or has_generic_mana)
    ):
        filters.append(
            "("
            + " or ".join("instr(oracle_filter.color_identities, ?) > 0" for _ in selected_color_set)
            + ")"
        )
        params.extend(sorted(selected_color_set))
    if no_colors:
        filters.append("oracle_filter.color_identities = ''")
    if has_colorless_mana:
        filters.append("instr(oracle_filter.mana_cost, '{C}') > 0")

    connection: sqlite3.Connection | None = None
    try:
        connection = _attached_catalog_connection(db)
        if connection is None:
            return None
        rows = connection.execute(
            f"""
            select
                coalesce(a.allocated_quantity, 0) as allocated_quantity,
                {select_columns}
            from collection_items as ci
            {joins}
            left join (
                select collection_item_id, sum(quantity) as allocated_quantity
                from deck_items
                group by collection_item_id
            ) as a on a.collection_item_id = ci.id
            where {" and ".join(filters)}
            order by c.name, ci.created_at desc, ci.id desc
            """,
            params,
        ).fetchall()
    finally:
        if connection is not None:
            connection.close()

    candidates: list[dict] = []
    for row in rows:
        candidate = {
            **dict(row),
            "scryfall_id": str(UUID(bytes=row["scryfall_id"])),
            "oracle_id": str(UUID(bytes=row["oracle_id"])),
        }
        if has_color_filter and not _matches_color_filters(
            candidate,
            selected_colors=selected_colors or [],
            color_match=color_match,
            has_uncolored_mana=has_uncolored_mana,
            has_colorless_mana=has_colorless_mana,
            has_generic_mana=has_generic_mana,
            no_colors=no_colors,
        ):
            continue
        candidates.append(candidate)
    return candidates


def _collection_items_by_id(db: Session, item_ids: list[int]) -> dict[int, CollectionItem]:
    if not item_ids:
        return {}
    items: dict[int, CollectionItem] = {}
    for offset in range(0, len(item_ids), 500):
        chunk = item_ids[offset : offset + 500]
        for item in db.scalars(select(CollectionItem).where(CollectionItem.id.in_(chunk))):
            items[item.id] = item
    return items


def _attached_deck_items(db: Session, deck_id: int) -> list[WorkspaceDeckItemRead] | None:
    connection: sqlite3.Connection | None = None
    try:
        connection = _attached_catalog_connection(db)
        if connection is None:
            return None
        rows = connection.execute(
            f"""
            select
                di.id as deck_item_id,
                di.section,
                di.quantity as deck_quantity,
                coalesce(a.allocated_quantity, 0) as allocated_quantity,
                {ATTACHED_ITEM_SELECT_BASE}
            from deck_items as di
            join collection_items as ci on ci.id = di.collection_item_id
            {ATTACHED_ITEM_JOINS_BASIC}
            left join (
                select collection_item_id, sum(quantity) as allocated_quantity
                from deck_items
                group by collection_item_id
            ) as a on a.collection_item_id = ci.id
            where di.deck_id = ?
            order by di.section, di.id
            """,
            (deck_id,),
        ).fetchall()
    finally:
        if connection is not None:
            connection.close()
    return [
        _attached_deck_item_read(
            {
                **dict(row),
                "scryfall_id": str(UUID(bytes=row["scryfall_id"])),
                "oracle_id": str(UUID(bytes=row["oracle_id"])),
            }
        )
        for row in rows
    ]


def _attached_collection_items(
    db: Session,
    collection_id: int,
    *,
    search_text: str = "",
    search_field: str = "name",
) -> list[WorkspaceCollectionItemRead] | None:
    normalized_search_text = search_text.casefold()
    params: list[object] = []
    joins = ATTACHED_ITEM_JOINS_BASIC
    if normalized_search_text:
        search_column = "name" if search_field == "name" else "type"
        joins = f"""
            {joins}
            join (
                select distinct oracle_id
                from catalog.card_search_index
                where unicode_casefold({search_column}) like ?
            ) as search_match on search_match.oracle_id = p.oracle_id
        """
        params.append(f"%{normalized_search_text}%")
    params.append(collection_id)
    connection: sqlite3.Connection | None = None
    try:
        connection = _attached_catalog_connection(db)
        if connection is None:
            return None
        rows = connection.execute(
            f"""
            select
                coalesce(a.allocated_quantity, 0) as allocated_quantity,
                {ATTACHED_ITEM_SELECT_BASE}
            from collection_items as ci
            {joins}
            left join (
                select collection_item_id, sum(quantity) as allocated_quantity
                from deck_items
                group by collection_item_id
            ) as a on a.collection_item_id = ci.id
            where ci.collection_id = ?
            order by unicode_casefold(localized_name) asc, ci.created_at desc
            """,
            params,
        ).fetchall()
    finally:
        if connection is not None:
            connection.close()
    row_dicts = [
        {
            **dict(row),
            "scryfall_id": str(UUID(bytes=row["scryfall_id"])),
            "oracle_id": str(UUID(bytes=row["oracle_id"])),
        }
        for row in rows
    ]
    allocations = _allocation_breakdown(db, [row["collection_item_id"] for row in row_dicts])
    return [
        _attached_collection_item_read(
            row,
            allocations.get(row["collection_item_id"], []),
        )
        for row in row_dicts
    ]


def _attached_inventory_items_by_id(
    db: Session,
    item_ids: list[int],
) -> dict[int, dict] | None:
    if not item_ids:
        return {}
    rows: list[sqlite3.Row] = []
    connection: sqlite3.Connection | None = None
    try:
        connection = _attached_catalog_connection(db)
        if connection is None:
            return None
        for offset in range(0, len(item_ids), 500):
            chunk = item_ids[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                connection.execute(
                    f"""
                    select
                        {ATTACHED_ITEM_SELECT_BASE}
                    from collection_items as ci
                    {ATTACHED_ITEM_JOINS_BASIC}
                    where ci.id in ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            )
    finally:
        if connection is not None:
            connection.close()
    return {
        row["collection_item_id"]: {
            **dict(row),
            "scryfall_id": str(UUID(bytes=row["scryfall_id"])),
            "oracle_id": str(UUID(bytes=row["oracle_id"])),
        }
        for row in rows
    }


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
            detail="Use wish deck item endpoints for wish decks",
        )


def _ensure_wish_deck(deck: Deck) -> None:
    if not deck.is_wish:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wish deck item endpoints are only available for wish decks",
        )


def _wish_item_read(item: WishDeckItem, details: dict) -> WorkspaceWishDeckItemRead:
    return WorkspaceWishDeckItemRead(
        id=item.id,
        oracle_id=str(UUID(bytes=item.oracle_id)),
        language_code=item.language_code,
        language=details["language"],
        name=details["name"],
        type=details["type"],
        mana_cost=details["mana_cost"],
        printing_id=details["printing_id"],
        release_date=details["release_date"],
        section=item.section,
        quantity=item.quantity,
        linked_collection_item_id=item.linked_collection_item_id,
    )


def _wish_items_read(items: list[WishDeckItem]) -> list[WorkspaceWishDeckItemRead]:
    requests = [(str(UUID(bytes=item.oracle_id)), item.language_code) for item in items]
    try:
        details_by_key = catalog.wish_deck_card_details(requests)
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    reads: list[WorkspaceWishDeckItemRead] = []
    for item in items:
        key = (str(UUID(bytes=item.oracle_id)), item.language_code)
        details = details_by_key.get(key)
        if details is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Wish deck item no longer resolves to the installed catalog",
            )
        reads.append(_wish_item_read(item, details))
    return reads


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


def _card_image_response(image_path: Path, media_type: str) -> FileResponse:
    response = FileResponse(image_path, media_type=media_type)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


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
    fallback_owner = db.scalar(
        select(Player)
        .where(Player.id != player.id)
        .order_by(Player.is_default.desc(), Player.created_at, Player.id)
        .limit(1)
    )
    if fallback_owner is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose another player before deleting this one",
        )
    for collection in affected_collections:
        collection.player = fallback_owner
    for deck in affected_decks:
        deck.player = fallback_owner
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
    if db.get(Player, payload.player_id) is None:
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
    if "player_id" in update_data:
        if update_data["player_id"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Owner is required",
            )
        if db.get(Player, update_data["player_id"]) is None:
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
    _ensure_physical_deck(deck)
    attached_items = _attached_deck_items(db, deck.id)
    if attached_items is not None:
        return attached_items
    items = list(
        db.scalars(
            select(DeckItem)
            .where(DeckItem.deck_id == deck.id)
            .order_by(DeckItem.section, DeckItem.id)
        )
    )
    return [_deck_item_read(db, item) for item in items]


@router.get(
    "/decks/{deck_id}/wish-items/search",
    response_model=list[WorkspaceWishDeckSearchResultRead],
)
def search_wish_deck_cards(
    deck_id: int,
    response: Response,
    query: str = Query(default="", max_length=255),
    search_field: str = Query(default="name"),
    colors: list[str] = Query(default=[]),
    rarities: list[str] = Query(default=[]),
    mana_value_min: float | None = Query(default=None, ge=0),
    mana_value_max: float | None = Query(default=None, ge=0),
    color_match: str = Query(default="includes_all"),
    has_uncolored_mana: bool = False,
    has_colorless_mana: bool = False,
    has_generic_mana: bool = False,
    no_colors: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceWishDeckSearchResultRead]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_wish_deck(deck)
    search_text = query.strip()
    if search_field not in {"name", "type", "text"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid search_field",
        )
    selected_colors = [color.upper() for color in colors if color.upper() in {"W", "U", "B", "R", "G"}]
    selected_rarities = {rarity.casefold() for rarity in rarities if rarity.strip()}
    if color_match not in {"includes_all", "includes_any", "exactly"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid color_match",
        )
    if (
        mana_value_min is not None
        and mana_value_max is not None
        and mana_value_min > mana_value_max
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid mana value range",
        )
    has_filters = bool(
        selected_colors
        or selected_rarities
        or mana_value_min is not None
        or mana_value_max is not None
        or has_uncolored_mana
        or has_colorless_mana
        or has_generic_mana
        or no_colors
    )
    if not search_text and not has_filters:
        response.headers["X-Total-Count"] = "0"
        response.headers["X-Total-Items"] = "0"
        return []
    try:
        results, total_count = catalog.search_wish_deck_cards(
            search_text,
            field=search_field,
            colors=selected_colors,
            rarities=selected_rarities,
            mana_value_min=mana_value_min,
            mana_value_max=mana_value_max,
            color_match=color_match,
            has_uncolored_mana=has_uncolored_mana,
            has_colorless_mana=has_colorless_mana,
            has_generic_mana=has_generic_mana,
            no_colors=no_colors,
            offset=offset,
            limit=limit,
        )
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Total-Items"] = str(total_count)
    return [WorkspaceWishDeckSearchResultRead(**result) for result in results]


@router.get(
    "/decks/{deck_id}/wish-items",
    response_model=list[WorkspaceWishDeckItemRead],
)
def list_wish_deck_items(
    deck_id: int,
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceWishDeckItemRead]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_wish_deck(deck)
    items = list(
        db.scalars(
            select(WishDeckItem)
            .where(WishDeckItem.deck_id == deck.id)
            .order_by(WishDeckItem.section, WishDeckItem.id)
        )
    )
    return _wish_items_read(items)


@router.post(
    "/decks/{deck_id}/wish-items",
    response_model=WorkspaceWishDeckItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_wish_deck_item(
    deck_id: int,
    payload: WorkspaceWishDeckItemCreate,
    db: Session = Depends(get_user_data_db),
) -> WorkspaceWishDeckItemRead:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_wish_deck(deck)
    try:
        oracle_id = UUID(payload.oracle_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid oracle_id",
        ) from error
    try:
        details_by_key = catalog.wish_deck_card_details(
            [(str(oracle_id), payload.language_code)]
        )
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    details = details_by_key.get((str(oracle_id), payload.language_code))
    if details is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wish deck card not found in installed catalog",
        )
    item = db.scalar(
        select(WishDeckItem).where(
            WishDeckItem.deck_id == deck.id,
            WishDeckItem.oracle_id == oracle_id.bytes,
            WishDeckItem.section == payload.section,
        )
    )
    if item is None:
        item = WishDeckItem(
            deck_id=deck.id,
            oracle_id=oracle_id.bytes,
            language_code=payload.language_code,
            section=payload.section,
            quantity=payload.quantity,
            created_at=int(time()),
        )
        db.add(item)
    else:
        item.quantity += payload.quantity
        item.language_code = payload.language_code
    deck.updated_at = int(time())
    db.commit()
    db.refresh(item)
    return _wish_item_read(item, details)


@router.patch(
    "/decks/{deck_id}/wish-items/{item_id}",
    response_model=WorkspaceWishDeckItemRead,
)
def update_wish_deck_item(
    deck_id: int,
    item_id: int,
    payload: WorkspaceWishDeckItemUpdate,
    db: Session = Depends(get_user_data_db),
) -> WorkspaceWishDeckItemRead:
    deck, item = _load_wish_deck_item(db, deck_id, item_id)
    update_data = payload.model_dump(exclude_unset=True)
    target_section = update_data.get("section", item.section)
    if target_section != item.section:
        move_quantity = update_data.get("quantity", item.quantity)
        if move_quantity > item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move more copies than the wish deck item contains",
            )
        target_item = db.scalar(
            select(WishDeckItem).where(
                WishDeckItem.deck_id == deck.id,
                WishDeckItem.oracle_id == item.oracle_id,
                WishDeckItem.section == target_section,
            )
        )
        if target_item is None:
            if move_quantity == item.quantity:
                item.section = target_section
                target_item = item
            else:
                item.quantity -= move_quantity
                target_item = WishDeckItem(
                    deck_id=deck.id,
                    oracle_id=item.oracle_id,
                    language_code=item.language_code,
                    section=target_section,
                    quantity=move_quantity,
                    linked_collection_item_id=item.linked_collection_item_id,
                    created_at=int(time()),
                )
                db.add(target_item)
        else:
            target_item.quantity += move_quantity
            target_item.language_code = item.language_code
            if move_quantity == item.quantity:
                db.delete(item)
            else:
                item.quantity -= move_quantity
        item = target_item
    else:
        item.quantity = update_data.get("quantity", item.quantity)
    deck.updated_at = int(time())
    db.commit()
    db.refresh(item)
    return _wish_items_read([item])[0]


@router.delete(
    "/decks/{deck_id}/wish-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_wish_deck_item(
    deck_id: int,
    item_id: int,
    db: Session = Depends(get_user_data_db),
) -> None:
    deck, item = _load_wish_deck_item(db, deck_id, item_id)
    db.delete(item)
    deck.updated_at = int(time())
    db.commit()


@router.get(
    "/decks/{deck_id}/items/search",
    response_model=list[WorkspaceDeckInventorySearchResultRead],
)
def search_physical_deck_inventory(
    deck_id: int,
    response: Response,
    query: str = Query(default="", max_length=255),
    search_field: str = Query(default="name"),
    oracle_id: str | None = Query(default=None),
    colors: list[str] = Query(default=[]),
    rarities: list[str] = Query(default=[]),
    mana_value_min: float | None = Query(default=None, ge=0),
    mana_value_max: float | None = Query(default=None, ge=0),
    color_match: str = Query(default="includes_all"),
    has_uncolored_mana: bool = False,
    has_colorless_mana: bool = False,
    has_generic_mana: bool = False,
    no_colors: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceDeckInventorySearchResultRead]:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found")
    _ensure_physical_deck(deck)
    search_text = query.strip()
    target_oracle_id = oracle_id.strip() if oracle_id else None
    if search_field not in {"name", "type", "text"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid search_field",
        )
    selected_colors = [color.upper() for color in colors if color.upper() in {"W", "U", "B", "R", "G"}]
    selected_rarities = {rarity.casefold() for rarity in rarities if rarity.strip()}
    if color_match not in {"includes_all", "includes_any", "exactly"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid color_match",
        )
    if (
        mana_value_min is not None
        and mana_value_max is not None
        and mana_value_min > mana_value_max
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid mana value range",
        )
    has_color_filters = bool(
        selected_colors or has_uncolored_mana or has_colorless_mana or has_generic_mana or no_colors
    )
    has_mana_value_filter = mana_value_min is not None or mana_value_max is not None
    has_filters = bool(has_color_filters or selected_rarities or has_mana_value_filter)

    def empty_search_results() -> list[WorkspaceDeckInventorySearchResultRead]:
        response.headers["X-Total-Count"] = "0"
        response.headers["X-Total-Items"] = "0"
        return []

    if target_oracle_id:
        try:
            UUID(target_oracle_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid oracle_id",
            ) from error
    if not search_text and target_oracle_id is None and not has_filters:
        return empty_search_results()
    matching_language_by_oracle_id: dict[str, str] = {}
    matching_name_by_oracle_id: dict[str, str] = {}
    matching_priority_by_oracle_id: dict[str, int] = {}
    should_use_attached_filter_search = False
    if target_oracle_id is None and (search_text or has_filters):
        should_use_attached_filter_search = _can_use_attached_catalog(db)
    if target_oracle_id is None and search_text and not should_use_attached_filter_search:
        try:
            suggestions = catalog.search_cards(
                search_text,
                field=search_field,
                exact=False,
                limit=50,
            )
        except FileNotFoundError as error:
            raise _catalog_error(error) from error
        for suggestion in suggestions:
            matching_language_by_oracle_id.setdefault(
                suggestion["oracle_id"],
                suggestion["language_code"],
            )
            matching_name_by_oracle_id.setdefault(suggestion["oracle_id"], suggestion["name"])
            matching_priority_by_oracle_id.setdefault(
                suggestion["oracle_id"],
                int(suggestion["search_priority"]),
            )
    if target_oracle_id is not None:
        matching_oracle_ids = {target_oracle_id}
    else:
        matching_oracle_ids = (
            set(matching_language_by_oracle_id)
            if search_text and not should_use_attached_filter_search
            else None
        )
        if has_color_filters and (matching_oracle_ids is not None or not should_use_attached_filter_search):
            try:
                color_filtered_oracle_ids = catalog.oracle_ids_matching_deck_filters(
                    colors=selected_colors,
                    color_match=color_match,
                    has_uncolored_mana=has_uncolored_mana,
                    has_colorless_mana=has_colorless_mana,
                    has_generic_mana=has_generic_mana,
                    no_colors=no_colors,
                )
            except FileNotFoundError as error:
                raise _catalog_error(error) from error
            matching_oracle_ids = (
                color_filtered_oracle_ids
                if matching_oracle_ids is None
                else matching_oracle_ids & color_filtered_oracle_ids
            )
    if matching_oracle_ids is not None and not matching_oracle_ids:
        return empty_search_results()
    if matching_oracle_ids is None and (search_text or has_filters):
        try:
            attached_candidates = _attached_inventory_candidates(
                db,
                search_text=search_text,
                search_field=search_field,
                rarities=selected_rarities,
                mana_value_min=mana_value_min,
                mana_value_max=mana_value_max,
                selected_colors=selected_colors,
                color_match=color_match,
                has_uncolored_mana=has_uncolored_mana,
                has_colorless_mana=has_colorless_mana,
                has_generic_mana=has_generic_mana,
                no_colors=no_colors,
            )
        except FileNotFoundError as error:
            raise _catalog_error(error) from error
        if attached_candidates is not None:
            raw_groups: dict[str, dict] = {}
            for candidate in attached_candidates:
                group = raw_groups.get(candidate["oracle_id"])
                if group is None:
                    group = {
                        "oracle_id": candidate["oracle_id"],
                        "name": candidate.get("matched_name") or candidate["printing_name"],
                        "language_code": candidate.get("matched_language_code") or candidate["item_language_code"],
                        "search_priority": (
                            int(candidate["matched_search_priority"])
                            if search_text
                            else 999
                        ),
                        "total_owned": 0,
                        "total_available": 0,
                        "items": [],
                    }
                    raw_groups[candidate["oracle_id"]] = group
                group["total_owned"] += candidate["owned_quantity"]
                group["total_available"] += max(
                    0,
                    candidate["owned_quantity"] - candidate["allocated_quantity"],
                )
                group["items"].append(candidate)

            sorted_groups = sorted(
                raw_groups.values(),
                key=lambda group: (
                    group["search_priority"],
                    group["name"].casefold(),
                    group["oracle_id"],
                ),
            )
            response.headers["X-Total-Count"] = str(len(sorted_groups))
            response.headers["X-Total-Items"] = str(
                sum(len(group["items"]) for group in sorted_groups)
            )
            top_groups = sorted_groups[offset : offset + limit]
            top_item_ids = [
                candidate["collection_item_id"]
                for group in top_groups
                for candidate in group["items"]
            ]
            attached_items = _attached_inventory_items_by_id(db, top_item_ids)
            if attached_items is None:
                attached_items = {}
            allocations = _allocation_breakdown(db, top_item_ids)
            return [
                WorkspaceDeckInventorySearchResultRead(
                    oracle_id=group["oracle_id"],
                    name=group["name"],
                    language_code=group["language_code"],
                    total_owned=group["total_owned"],
                    total_available=group["total_available"],
                    items=[
                        _attached_inventory_item_read(
                            attached_items[candidate["collection_item_id"]],
                            allocations.get(candidate["collection_item_id"], []),
                        )
                        for candidate in group["items"]
                        if candidate["collection_item_id"] in attached_items
                    ],
                )
                for group in top_groups
            ]
    matching_scryfall_ids: set[bytes] | None = None
    if matching_oracle_ids is not None:
        try:
            matching_scryfall_ids = catalog.scryfall_ids_for_oracle_ids(matching_oracle_ids)
        except FileNotFoundError as error:
            raise _catalog_error(error) from error
        if not matching_scryfall_ids:
            return empty_search_results()
    item_statement = (
        select(CollectionItem)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.is_wishlist.is_(False))
        .order_by(Collection.name, CollectionItem.created_at.desc(), CollectionItem.id.desc())
    )
    if matching_scryfall_ids is not None:
        item_statement = item_statement.where(CollectionItem.scryfall_id.in_(matching_scryfall_ids))
    items = list(
        db.scalars(item_statement)
    )
    try:
        printings = catalog.get_printings_by_scryfall_ids([item.scryfall_id for item in items])
    except FileNotFoundError as error:
        raise _catalog_error(error) from error
    matching_items: list[tuple[CollectionItem, dict]] = []
    grouped: dict[str, WorkspaceDeckInventorySearchResultRead] = {}
    for item in items:
        printing = printings.get(item.scryfall_id)
        if printing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Collection item no longer resolves to the installed catalog",
            )
        if matching_oracle_ids is not None and printing["oracle_id"] not in matching_oracle_ids:
            continue
        if selected_rarities and printing["rarity"].casefold() not in selected_rarities:
            continue
        mana_value = float(printing["mana_value"])
        if mana_value_min is not None and mana_value < mana_value_min:
            continue
        if mana_value_max is not None and mana_value > mana_value_max:
            continue
        matching_items.append((item, printing))
    allocations = _allocation_breakdown(db, [item.id for item, _printing in matching_items])
    raw_groups: dict[str, dict] = {}
    for item, printing in matching_items:
        group = raw_groups.get(printing["oracle_id"])
        if group is None:
            group = {
                "oracle_id": printing["oracle_id"],
                "name": matching_name_by_oracle_id.get(printing["oracle_id"]) or printing["name"],
                "language_code": (
                    matching_language_by_oracle_id.get(printing["oracle_id"])
                    or item.language_code
                ),
                "search_priority": (
                    matching_priority_by_oracle_id[printing["oracle_id"]]
                    if search_text and target_oracle_id is None
                    else 999
                ),
                "total_owned": 0,
                "total_available": 0,
                "items": [],
            }
            raw_groups[printing["oracle_id"]] = group
        allocated_quantity = sum(allocation["quantity"] for allocation in allocations.get(item.id, []))
        group["total_owned"] += item.quantity
        group["total_available"] += max(0, item.quantity - allocated_quantity)
        group["items"].append((item, printing))

    top_groups = sorted(
        raw_groups.values(),
        key=lambda group: (
            group["search_priority"],
            group["name"].casefold(),
            group["oracle_id"],
        ),
    )
    response.headers["X-Total-Count"] = str(len(top_groups))
    response.headers["X-Total-Items"] = str(sum(len(group["items"]) for group in top_groups))
    top_groups = top_groups[offset : offset + limit]
    for group in top_groups:
        result = WorkspaceDeckInventorySearchResultRead(
            oracle_id=group["oracle_id"],
            name=group["name"],
            language_code=group["language_code"],
            total_owned=group["total_owned"],
            total_available=group["total_available"],
            items=[],
        )
        for item, printing in group["items"]:
            result.items.append(
                _inventory_item_read(
                    item,
                    printing,
                    allocations.get(item.id, []),
                )
            )
        grouped[group["oracle_id"]] = result
    return list(grouped.values())


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
    if "player_id" in update_data:
        if requested_player_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Owner is required",
            )
        if db.get(Player, requested_player_id) is None:
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
    remove_allocations: bool = Query(default=False),
    allocation_signature: str | None = Query(default=None),
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
    allocation_summary, current_allocation_signature = _collection_allocation_summary(db, collection.id)
    if allocation_summary and not remove_allocations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Collection contains cards allocated to decks",
                "allocation_signature": current_allocation_signature,
                "items": allocation_summary,
            },
        )
    if allocation_summary and allocation_signature != current_allocation_signature:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deck allocations changed. Refresh the collection and try again.",
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
    if remove_allocations:
        deck_items = list(
            db.scalars(
                select(DeckItem)
                .join(CollectionItem, CollectionItem.id == DeckItem.collection_item_id)
                .where(CollectionItem.collection_id == collection.id)
            )
        )
        for deck_item in deck_items:
            db.delete(deck_item)
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
    card = scryfall.get_cached_card_json(
        printing["set_code"],
        printing["collector_number"],
        printing["language_code"],
    )
    if card is None:
        card = scryfall.get_cached_card_json_by_scryfall_id(printing["scryfall_id"])
    if card is not None:
        card = _localized_card_details(printing_id, card, requested_language_code)
    else:
        card = _catalog_card_details(printing, requested_language_code)
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
        return _card_image_response(image_path, media_type)
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
            return _card_image_response(image_path, media_type)
        raise _scryfall_error(error) from error
    return _card_image_response(image_path, media_type)


@router.get(
    "/collections/{collection_id}/items",
    response_model=list[WorkspaceCollectionItemRead],
)
def list_collection_items(
    collection_id: int,
    query: str = Query(default="", max_length=255),
    search_field: str = Query(default="name"),
    db: Session = Depends(get_user_data_db),
) -> list[WorkspaceCollectionItemRead]:
    if db.get(Collection, collection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    search_text = query.strip()
    if search_field not in {"name", "type"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid search_field",
        )
    attached_items = _attached_collection_items(
        db,
        collection_id,
        search_text=search_text,
        search_field=search_field,
    )
    if attached_items is not None:
        return attached_items
    matching_scryfall_ids: set[bytes] | None = None
    if search_text:
        try:
            matching_oracle_ids = catalog.oracle_ids_matching_search(search_text, field=search_field)
            matching_scryfall_ids = catalog.scryfall_ids_for_oracle_ids(matching_oracle_ids)
        except FileNotFoundError as error:
            raise _catalog_error(error) from error
        if not matching_scryfall_ids:
            return []
    items = db.scalars(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
        .order_by(CollectionItem.created_at.desc(), CollectionItem.id.desc())
    )
    item_list = list(items)
    if matching_scryfall_ids is not None:
        item_list = [item for item in item_list if item.scryfall_id in matching_scryfall_ids]
    return _items_read(db, item_list)


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
    return _item_read(db, item)


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
    deck_items = list(
        db.scalars(
            select(DeckItem)
            .where(DeckItem.collection_item_id == item.id)
            .order_by(DeckItem.id)
        )
    )
    allocated_quantity = sum(deck_item.quantity for deck_item in deck_items)
    identity_changed = any(
        (
            item.scryfall_id != scryfall_id,
            item.finish_id != payload.finish_id,
            item.language_code != selected_language_code,
            item.condition_code != payload.condition_code,
        )
    )
    allocation_signature = "|".join(
        f"{deck_item.id}:{deck_item.quantity}"
        for deck_item in sorted(deck_items, key=lambda deck_item: deck_item.id)
    )
    if identity_changed:
        if payload.quantity != item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Save quantity changes separately before changing card attributes.",
            )
        if payload.attribute_update is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select copies to update",
            )
        if (
            payload.attribute_update.source_quantity != item.quantity
            or payload.attribute_update.allocation_signature != allocation_signature
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Card copies changed. Refresh the collection and try again.",
            )
        selection_quantities: dict[int, int] = {}
        for selection in payload.attribute_update.allocation_selections:
            selection_quantities[selection.deck_item_id] = (
                selection_quantities.get(selection.deck_item_id, 0) + selection.quantity
            )
        selected_allocated_quantity = sum(selection_quantities.values())
        selected_available_quantity = payload.attribute_update.available_quantity
        available_quantity = max(0, item.quantity - allocated_quantity)
        selected_quantity = selected_available_quantity + selected_allocated_quantity
        if selected_quantity < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select at least 1 copy to update.",
            )
        if selected_available_quantity > available_quantity or selected_quantity > item.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Card copies changed. Refresh the collection and try again.",
            )
        deck_items_by_id = {deck_item.id: deck_item for deck_item in deck_items}
        stale_copies_error = HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Card copies changed. Refresh the collection and try again.",
        )
        for deck_item_id, quantity in selection_quantities.items():
            deck_item = deck_items_by_id.get(deck_item_id)
            if deck_item is None or quantity > deck_item.quantity:
                raise stale_copies_error
        target_item = db.scalar(
            select(CollectionItem).where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.id != item.id,
                CollectionItem.scryfall_id == scryfall_id,
                CollectionItem.finish_id == payload.finish_id,
                CollectionItem.language_code == selected_language_code,
                CollectionItem.condition_code == payload.condition_code,
            )
        )
        if target_item is None:
            target_item = CollectionItem(
                collection_id=collection_id,
                scryfall_id=scryfall_id,
                finish_id=payload.finish_id,
                language_code=selected_language_code,
                condition_code=payload.condition_code,
                quantity=selected_quantity,
                created_at=int(time()),
            )
            db.add(target_item)
            db.flush()
        else:
            target_item.quantity += selected_quantity
        for deck_item_id, quantity in selection_quantities.items():
            deck_item = deck_items_by_id[deck_item_id]
            target_deck_item = db.scalar(
                select(DeckItem).where(
                    DeckItem.deck_id == deck_item.deck_id,
                    DeckItem.collection_item_id == target_item.id,
                    DeckItem.section == deck_item.section,
                )
            )
            if quantity == deck_item.quantity:
                if target_deck_item is None:
                    deck_item.collection_item_id = target_item.id
                else:
                    target_deck_item.quantity += quantity
                    db.delete(deck_item)
            else:
                deck_item.quantity -= quantity
                if target_deck_item is None:
                    db.add(
                        DeckItem(
                            deck_id=deck_item.deck_id,
                            collection_item_id=target_item.id,
                            section=deck_item.section,
                            quantity=quantity,
                        )
                    )
                else:
                    target_deck_item.quantity += quantity
        remaining_source_quantity = item.quantity - selected_quantity
        if remaining_source_quantity == 0:
            db.flush()
            db.delete(item)
            response_item = target_item
        else:
            item.quantity = remaining_source_quantity
            response_item = item
        db.commit()
        db.refresh(response_item)
        return _item_read(db, response_item)
    removal_quantities: dict[int, int] = {}
    for removal in payload.allocation_removals:
        removal_quantities[removal.deck_item_id] = (
            removal_quantities.get(removal.deck_item_id, 0) + removal.quantity
        )
    selected_removals = sum(removal_quantities.values())
    required_removals = max(0, allocated_quantity - payload.quantity)
    if selected_removals != required_removals:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Select exactly {required_removals} allocated copies to remove",
        )
    deck_items_by_id = {deck_item.id: deck_item for deck_item in deck_items}
    stale_allocations_error = HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Deck allocations changed. Refresh the collection and try again.",
    )
    for deck_item_id, quantity in removal_quantities.items():
        deck_item = deck_items_by_id.get(deck_item_id)
        if deck_item is None or quantity > deck_item.quantity:
            raise stale_allocations_error
        deck_item.quantity -= quantity
        if deck_item.quantity == 0:
            db.delete(deck_item)
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
    return _item_read(db, item)


@router.delete(
    "/collections/{collection_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection_item(
    collection_id: int,
    item_id: int,
    remove_allocations: bool = Query(default=False),
    db: Session = Depends(get_user_data_db),
) -> None:
    item = db.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection item not found")
    deck_items = list(db.scalars(select(DeckItem).where(DeckItem.collection_item_id == item.id)))
    if deck_items and not remove_allocations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection item is allocated to decks",
        )
    for deck_item in deck_items:
        db.delete(deck_item)
    db.delete(item)
    db.commit()
