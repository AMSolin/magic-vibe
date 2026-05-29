from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.init_db import DEV_CARDS
from app.db.session import get_db
from app.main import app
from app.models import MODELS
from app.models.card import Card
from app.models.collection import Collection
from app.models.deck import Deck


@pytest.fixture()
def client() -> Generator[TestClient]:
    _ = MODELS
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        default_collection = Collection(name="My collection", is_default=True)
        wishlist_collection = Collection(name="Wishlist", is_wishlist=True)
        db.add_all(Card(**card_data) for card_data in DEV_CARDS)
        db.add_all(
            [
                default_collection,
                wishlist_collection,
                Deck(name="Default deck", is_default=True),
                Deck(
                    name="Wish deck",
                    is_wishlist=True,
                    wishlist_collection=wishlist_collection,
                ),
            ]
        )
        db.commit()

    def override_get_db() -> Generator[Session]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_regular_collection_item(
    client: TestClient,
    quantity: int = 1,
    card_uuid: str = "00000000-0000-0000-0000-000000000001",
) -> dict:
    response = client.post(
        "/api/collections/1/items",
        json={"card_uuid": card_uuid, "quantity": quantity},
    )
    assert response.status_code == 201
    return response.json()


def _seed_wishlist_collection_item(
    client: TestClient,
    quantity: int = 1,
    card_uuid: str = "00000000-0000-0000-0000-000000000002",
) -> dict:
    response = client.post(
        "/api/collections/2/items",
        json={"card_uuid": card_uuid, "quantity": quantity},
    )
    assert response.status_code == 201
    return response.json()


def test_repeated_collection_add_increments_quantity(client: TestClient) -> None:
    first_response = client.post(
        "/api/collections/1/items",
        json={"card_uuid": "00000000-0000-0000-0000-000000000001", "quantity": 1},
    )
    second_response = client.post(
        "/api/collections/1/items",
        json={"card_uuid": "00000000-0000-0000-0000-000000000001", "quantity": 2},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert second_response.json()["id"] == first_response.json()["id"]
    assert second_response.json()["quantity"] == 3


def test_regular_deck_cannot_use_wishlist_collection_item(client: TestClient) -> None:
    wishlist_item = _seed_wishlist_collection_item(client)

    response = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": wishlist_item["id"], "quantity": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Regular deck items must come from a regular collection"


def test_wish_deck_cannot_use_unrelated_collection_item(client: TestClient) -> None:
    regular_item = _seed_regular_collection_item(client)

    response = client.post(
        "/api/decks/2/items",
        json={"collection_item_id": regular_item["id"], "quantity": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Wish deck items must come from the linked wishlist collection"


def test_deck_item_quantity_cannot_exceed_collection_item_quantity(client: TestClient) -> None:
    regular_item = _seed_regular_collection_item(client, quantity=1)
    first_response = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": regular_item["id"], "quantity": 1},
    )

    overflow_response = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": regular_item["id"], "quantity": 1},
    )

    assert first_response.status_code == 201
    assert overflow_response.status_code == 400
    assert overflow_response.json()["detail"] == "Not enough available copies in collection"


def test_allocated_collection_item_cannot_be_reduced_below_deck_quantity(
    client: TestClient,
) -> None:
    regular_item = _seed_regular_collection_item(client, quantity=2)
    deck_response = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": regular_item["id"], "quantity": 2},
    )
    assert deck_response.status_code == 201

    response = client.patch(
        f"/api/collections/1/items/{regular_item['id']}",
        json={"quantity": 1},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Collection item quantity cannot be lower than allocated deck quantity"
    )


def test_allocated_collection_item_cannot_be_deleted(client: TestClient) -> None:
    regular_item = _seed_regular_collection_item(client, quantity=1)
    deck_response = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": regular_item["id"], "quantity": 1},
    )
    assert deck_response.status_code == 201

    response = client.delete(f"/api/collections/1/items/{regular_item['id']}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Collection item is allocated to a deck"


def test_deck_management_updates_metadata_and_reassigns_primary_deck(client: TestClient) -> None:
    create_response = client.post(
        "/api/decks",
        json={"name": "Commander deck", "note": "First note", "is_default": True},
    )

    assert create_response.status_code == 201
    created_deck = create_response.json()
    assert created_deck["is_default"] is True

    decks_after_create = client.get("/api/decks").json()
    default_deck = next(deck for deck in decks_after_create if deck["name"] == "Default deck")
    assert default_deck["is_default"] is False

    update_response = client.patch(
        f"/api/decks/{created_deck['id']}",
        json={"name": "Renamed commander deck", "owner_id": 2, "note": "Updated note"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Renamed commander deck"
    assert update_response.json()["owner_id"] == 2
    assert update_response.json()["note"] == "Updated note"

    decks_after_update = client.get("/api/decks").json()
    default_deck = next(deck for deck in decks_after_update if deck["name"] == "Default deck")
    assert default_deck["is_default"] is True

    delete_response = client.delete(f"/api/decks/{created_deck['id']}")

    assert delete_response.status_code == 204


def test_only_deck_cannot_be_deleted(client: TestClient) -> None:
    assert client.delete("/api/decks/2").status_code == 204

    response = client.delete("/api/decks/1")

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot delete the only deck"


def test_deck_item_can_move_one_and_all_copies_between_sections(client: TestClient) -> None:
    regular_item = _seed_regular_collection_item(client, quantity=3)
    deck_item = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": regular_item["id"], "quantity": 3},
    ).json()

    move_one_response = client.post(
        f"/api/decks/1/items/{deck_item['id']}/move",
        json={"section": "side", "quantity": 1},
    )

    assert move_one_response.status_code == 200
    assert move_one_response.json()["section"] == "side"
    assert move_one_response.json()["quantity"] == 1

    items_after_move_one = client.get("/api/decks/1/items").json()
    main_item = next(item for item in items_after_move_one if item["section"] == "main")
    side_item = next(item for item in items_after_move_one if item["section"] == "side")
    assert main_item["quantity"] == 2
    assert side_item["quantity"] == 1

    move_all_response = client.post(
        f"/api/decks/1/items/{main_item['id']}/move",
        json={"section": "side"},
    )

    assert move_all_response.status_code == 200
    assert move_all_response.json()["section"] == "side"
    assert move_all_response.json()["quantity"] == 3
    assert len(client.get("/api/decks/1/items").json()) == 1


def test_deck_item_commander_flag_can_be_updated(client: TestClient) -> None:
    regular_item = _seed_regular_collection_item(client)
    deck_item = client.post(
        "/api/decks/1/items",
        json={"collection_item_id": regular_item["id"]},
    ).json()

    response = client.patch(
        f"/api/decks/1/items/{deck_item['id']}",
        json={"is_commander": True},
    )

    assert response.status_code == 200
    assert response.json()["is_commander"] is True
