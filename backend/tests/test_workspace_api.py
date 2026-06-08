import sqlite3
from collections.abc import Generator
from pathlib import Path
from urllib.error import HTTPError, URLError
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.user_data_base import UserDataBase
from app.db.user_data_session import get_user_data_db
from app.main import app
from app.models.user_data import CardCondition, Collection, Player, USER_DATA_MODELS
from app.services import catalog, scryfall

SCRYFALL_ID = "40000000-0000-0000-0000-000000000001"
ORACLE_ID = "50000000-0000-0000-0000-000000000001"


def _create_catalog(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table sets (
            code text primary key, name text, keyrune_code text, release_date integer, type text
        );
        create table languages (code text primary key, name text);
        create table finishes (id integer primary key, name text);
        create table card_printings (
            id integer primary key, scryfall_id blob, oracle_id blob, set_code text,
            collector_number text, language_code text, name text, rarity text, layout text
        );
        create table card_printing_finishes (printing_id integer, finish_id integer);
        create table card_printing_faces (
            id integer primary key, printing_id integer, face_order integer, side text,
            face_name text, mana_cost text, mana_value real, type text, text text,
            colors text, color_identity text, keywords text, power text, toughness text,
            loyalty text, defense text
        );
        create table card_face_localizations (
            id integer primary key, face_id integer, language_code text, name text,
            face_name text, type text, text text, flavor_text text
        );
        create table card_search_index (
            id integer primary key, oracle_id blob, face_order integer, language_code text,
            name text collate nocase, type text, text text, mana_value real, colors text,
            color_identity text, keywords text, search_priority integer
        );
        insert into sets values ('TST', 'Test Set', 'tst', 1780099200, 'expansion');
        insert into languages values ('en', 'English');
        insert into languages values ('ru', 'Russian');
        insert into finishes values (0, 'nonfoil');
        insert into finishes values (1, 'foil');
        """
    )
    db.execute(
        """
        insert into card_printings values (
            1, ?, ?, 'TST', '1', 'en', 'Swamp', 'common', 'normal'
        )
        """,
        (UUID(SCRYFALL_ID).bytes, UUID(ORACLE_ID).bytes),
    )
    db.execute("insert into card_printing_finishes values (1, 0)")
    db.execute("insert into card_printing_finishes values (1, 1)")
    db.execute(
        """
        insert into card_printing_faces values (
            1, 1, 0, null, null, '', 0, 'Basic Land - Swamp', '({T}: Add {B}.)',
            'B', 'B', '', null, null, null, null
        )
        """
    )
    db.execute(
        """
        insert into card_search_index values (
            1, ?, 0, 'en', 'Swamp', 'Basic Land - Swamp', '({T}: Add {B}.)',
            0, 'B', 'B', '', 1
        )
        """,
        (UUID(ORACLE_ID).bytes,),
    )
    db.execute(
        """
        insert into card_search_index values (
            3, ?, 0, 'ru', ?, ?, ?, 0, 'B', 'B', '', 1
        )
        """,
        (
            UUID(ORACLE_ID).bytes,
            "\u0411\u043e\u043b\u043e\u0442\u043e",
            "\u0411\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0435\u043c\u043b\u044f - \u0411\u043e\u043b\u043e\u0442\u043e",
            "({T}: \u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 {B}.)",
        ),
    )
    db.execute(
        """
        insert into card_face_localizations values (
            1, 1, 'ru', ?, null, ?, ?, null
        )
        """,
        (
            "\u0411\u043e\u043b\u043e\u0442\u043e",
            "\u0411\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0435\u043c\u043b\u044f - \u0411\u043e\u043b\u043e\u0442\u043e",
            "({T}: \u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 {B}.)",
        ),
    )
    db.execute(
        """
        insert into card_search_index values (
            2, ?, 0, 'ru', 'Болото', 'Базовая земля - Болото', '({T}: Добавьте {B}.)',
            0, 'B', 'B', '', 2
        )
        """,
        (UUID(ORACLE_ID).bytes,),
    )
    db.commit()
    db.close()


@pytest.fixture()
def workspace_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient]:
    _ = USER_DATA_MODELS
    catalog_path = tmp_path / "catalog.db"
    _create_catalog(catalog_path)
    monkeypatch.setattr(catalog.settings, "catalog_database_path", str(catalog_path))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserDataBase.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with testing_session() as db:
        player = Player(name="Player", is_default=True, created_at=1)
        db.add_all(
            [
                CardCondition(code="NM", name="Near Mint", sort_order=1),
                player,
                Collection(player=player, name="My collection", is_default=True, created_at=1),
            ]
        )
        db.commit()

    def override_get_user_data_db() -> Generator[Session]:
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_user_data_db] = override_get_user_data_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_workspace_search_and_printing_options(workspace_client: TestClient) -> None:
    response = workspace_client.get("/api/workspace/cards/suggest", params={"query": "s"})
    assert response.status_code == 200
    assert [suggestion["name"] for suggestion in response.json()] == ["Swamp"]

    exact_response = workspace_client.get(
        "/api/workspace/cards/suggest",
        params={"query": "s", "exact": "true"},
    )
    assert exact_response.json() == []

    russian_response = workspace_client.get(
        "/api/workspace/cards/suggest",
        params={"query": "\u0431\u043e\u043b\u043e\u0442\u043e"},
    )
    assert [suggestion["name"] for suggestion in russian_response.json()] == [
        "\u0411\u043e\u043b\u043e\u0442\u043e"
    ]

    options_response = workspace_client.get(
        f"/api/workspace/cards/{ORACLE_ID}/printings",
        params={"preferred_language_code": "en"},
    )
    assert options_response.status_code == 200
    assert options_response.json()["printings"][0]["finishes"] == [
        {"id": 0, "name": "nonfoil"},
        {"id": 1, "name": "foil"},
    ]
    assert options_response.json()["printings"][0]["localizations"] == [
        {"code": "ru", "name": "Russian"}
    ]


def test_workspace_collection_settings_crud(workspace_client: TestClient) -> None:
    players = workspace_client.get("/api/workspace/players")
    assert players.status_code == 200
    assert players.json() == [{"id": 1, "name": "Player", "is_default": True, "created_at": 1}]

    created = workspace_client.post(
        "/api/workspace/collections",
        json={
            "name": "Trade binder",
            "player_id": 1,
            "note": "For events",
        },
    )
    assert created.status_code == 201
    assert created.json()["player_id"] == 1
    assert created.json()["is_default"] is False

    detached_default = workspace_client.patch(
        "/api/workspace/collections/1",
        json={"player_id": None},
    )
    assert detached_default.status_code == 200
    assert detached_default.json()["player_id"] is None
    assert detached_default.json()["is_default"] is True

    updated = workspace_client.patch(
        f"/api/workspace/collections/{created.json()['id']}",
        json={
            "name": "Main binder",
            "note": "Updated note",
            "is_default": True,
            "created_at": 1_800_000_000,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Main binder"
    assert updated.json()["note"] == "Updated note"
    assert updated.json()["is_default"] is True
    assert updated.json()["created_at"] == 1_800_000_000
    collections = workspace_client.get("/api/workspace/collections").json()
    assert [collection["is_default"] for collection in collections] == [False, True]

    deleted = workspace_client.delete(f"/api/workspace/collections/{created.json()['id']}")
    assert deleted.status_code == 204
    assert workspace_client.get("/api/workspace/collections").json()[0]["is_default"] is True


def test_workspace_player_asset_lists_include_decks(workspace_client: TestClient) -> None:
    decks = workspace_client.get("/api/workspace/decks")

    assert decks.status_code == 200
    assert decks.json() == []


def test_workspace_deck_settings_crud(workspace_client: TestClient) -> None:
    created = workspace_client.post(
        "/api/workspace/decks",
        json={
            "name": "Commander plan",
            "player_id": 1,
            "note": "First pass",
            "is_wish": True,
            "created_at": 1_800_000_000,
        },
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Commander plan"
    assert created.json()["player_id"] == 1
    assert created.json()["is_wish"] is True
    assert created.json()["created_at"] == 1_800_000_000
    assert isinstance(created.json()["updated_at"], int)

    duplicate_same_type = workspace_client.post(
        "/api/workspace/decks",
        json={"name": "Commander plan", "player_id": 1, "is_wish": True},
    )
    duplicate_other_type = workspace_client.post(
        "/api/workspace/decks",
        json={"name": "Commander plan", "player_id": 1, "is_wish": False},
    )
    assert duplicate_same_type.status_code == 409
    assert duplicate_other_type.status_code == 201

    updated = workspace_client.patch(
        f"/api/workspace/decks/{created.json()['id']}",
        json={
            "name": "Renamed plan",
            "player_id": None,
            "note": "Updated",
            "created_at": 1_810_000_000,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed plan"
    assert updated.json()["player_id"] is None
    assert updated.json()["is_wish"] is True
    assert updated.json()["created_at"] == 1_810_000_000

    items = workspace_client.get(f"/api/workspace/decks/{created.json()['id']}/items")
    assert items.status_code == 200
    assert items.json() == []

    deleted = workspace_client.delete(f"/api/workspace/decks/{created.json()['id']}")
    assert deleted.status_code == 204


def test_workspace_physical_deck_inventory_search_and_add(
    workspace_client: TestClient,
) -> None:
    created_item = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 2},
    ).json()
    wishlist = workspace_client.post(
        "/api/workspace/collections",
        json={"name": "Wishlist", "player_id": 1, "is_wishlist": True},
    ).json()
    workspace_client.post(
        f"/api/workspace/collections/{wishlist['id']}/items",
        json={"printing_id": 1, "finish_id": 1, "condition_code": "NM", "quantity": 4},
    )
    deck = workspace_client.post(
        "/api/workspace/decks",
        json={"name": "Physical deck", "player_id": 1},
    ).json()

    initial_search = workspace_client.get(
        f"/api/workspace/decks/{deck['id']}/items/search",
        params={"query": "swa"},
    )
    added = workspace_client.post(
        f"/api/workspace/decks/{deck['id']}/items",
        json={"collection_item_id": created_item["id"], "section": "main"},
    )
    incremented = workspace_client.post(
        f"/api/workspace/decks/{deck['id']}/items",
        json={"collection_item_id": created_item["id"], "section": "main"},
    )
    overflow = workspace_client.post(
        f"/api/workspace/decks/{deck['id']}/items",
        json={"collection_item_id": created_item["id"], "section": "main"},
    )
    updated_search = workspace_client.get(
        f"/api/workspace/decks/{deck['id']}/items/search",
        params={"query": "swa"},
    )
    oracle_search = workspace_client.get(
        f"/api/workspace/decks/{deck['id']}/items/search",
        params={"oracle_id": ORACLE_ID},
    )
    russian_search = workspace_client.get(
        f"/api/workspace/decks/{deck['id']}/items/search",
        params={"query": "\u0431\u043e\u043b"},
    )
    deck_items = workspace_client.get(f"/api/workspace/decks/{deck['id']}/items")
    decremented = workspace_client.patch(
        f"/api/workspace/decks/{deck['id']}/items/{added.json()['id']}",
        json={"quantity": 1},
    )
    side_item = workspace_client.post(
        f"/api/workspace/decks/{deck['id']}/items",
        json={"collection_item_id": created_item["id"], "section": "side"},
    )
    moved = workspace_client.patch(
        f"/api/workspace/decks/{deck['id']}/items/{decremented.json()['id']}",
        json={"section": "side"},
    )
    after_move = workspace_client.get(f"/api/workspace/decks/{deck['id']}/items")
    deleted = workspace_client.delete(
        f"/api/workspace/decks/{deck['id']}/items/{moved.json()['id']}",
    )
    after_delete_search = workspace_client.get(
        f"/api/workspace/decks/{deck['id']}/items/search",
        params={"oracle_id": ORACLE_ID},
    )

    assert initial_search.status_code == 200
    assert initial_search.json()[0]["total_owned"] == 2
    assert initial_search.json()[0]["total_available"] == 2
    assert len(initial_search.json()[0]["items"]) == 1
    assert initial_search.json()[0]["items"][0]["collection_name"] == "My collection"
    assert initial_search.json()[0]["items"][0]["release_date"] == 1780099200
    assert added.status_code == 201
    assert added.json()["name"] == "Swamp"
    assert added.json()["oracle_id"] == ORACLE_ID
    assert incremented.status_code == 201
    assert incremented.json()["id"] == added.json()["id"]
    assert incremented.json()["quantity"] == 2
    assert overflow.status_code == 400
    assert overflow.json()["detail"] == "Not enough available copies in collection"
    assert updated_search.json()[0]["total_owned"] == 2
    assert updated_search.json()[0]["total_available"] == 0
    assert updated_search.json()[0]["items"][0]["allocations"] == [
        {"deck_id": deck["id"], "deck_name": "Physical deck", "section": "main", "quantity": 2}
    ]
    assert oracle_search.status_code == 200
    assert oracle_search.json()[0]["oracle_id"] == ORACLE_ID
    assert oracle_search.json()[0]["total_owned"] == 2
    assert oracle_search.json()[0]["total_available"] == 0
    assert russian_search.status_code == 200
    assert russian_search.json()[0]["name"] == "\u0411\u043e\u043b\u043e\u0442\u043e"
    assert russian_search.json()[0]["items"][0]["name"] == "\u0411\u043e\u043b\u043e\u0442\u043e"
    assert deck_items.json() == [
        {
            "id": added.json()["id"],
            "collection_item_id": created_item["id"],
            "printing_id": 1,
            "release_date": 1780099200,
            "language_code": "en",
            "collection_id": 1,
            "collection_name": "My collection",
            "set_code": "TST",
            "keyrune_code": "tst",
            "collector_number": "1",
            "language": "English",
            "finish_id": 0,
            "finish": "nonfoil",
            "condition_code": "NM",
            "owned_quantity": 2,
            "allocated_quantity": 2,
            "available_quantity": 0,
            "section": "main",
            "quantity": 2,
            "name": "Swamp",
            "oracle_id": ORACLE_ID,
        }
    ]
    assert decremented.status_code == 200
    assert decremented.json()["quantity"] == 1
    assert side_item.status_code == 201
    assert side_item.json()["section"] == "side"
    assert side_item.json()["quantity"] == 1
    assert moved.status_code == 200
    assert moved.json()["id"] == side_item.json()["id"]
    assert moved.json()["section"] == "side"
    assert moved.json()["quantity"] == 2
    assert [item["section"] for item in after_move.json()] == ["side"]
    assert deleted.status_code == 204
    assert after_delete_search.status_code == 200
    assert after_delete_search.json()[0]["total_available"] == 2


def test_workspace_wish_decks_reject_physical_inventory_actions(
    workspace_client: TestClient,
) -> None:
    created_item = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 1},
    ).json()
    deck = workspace_client.post(
        "/api/workspace/decks",
        json={"name": "Wish deck", "player_id": 1, "is_wish": True},
    ).json()

    search = workspace_client.get(
        f"/api/workspace/decks/{deck['id']}/items/search",
        params={"query": "swa"},
    )
    add = workspace_client.post(
        f"/api/workspace/decks/{deck['id']}/items",
        json={"collection_item_id": created_item["id"], "section": "main"},
    )

    assert search.status_code == 400
    assert search.json()["detail"] == "Wish deck items are not implemented yet"
    assert add.status_code == 400
    assert add.json()["detail"] == "Wish deck items are not implemented yet"


def test_workspace_physical_deck_item_partial_move(
    workspace_client: TestClient,
) -> None:
    created_item = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 3},
    ).json()
    deck = workspace_client.post(
        "/api/workspace/decks",
        json={"name": "Physical deck", "player_id": 1},
    ).json()
    main_item = workspace_client.post(
        f"/api/workspace/decks/{deck['id']}/items",
        json={"collection_item_id": created_item["id"], "section": "main", "quantity": 2},
    ).json()

    moved_one = workspace_client.patch(
        f"/api/workspace/decks/{deck['id']}/items/{main_item['id']}",
        json={"section": "side", "quantity": 1},
    )
    deck_items = workspace_client.get(f"/api/workspace/decks/{deck['id']}/items")

    assert moved_one.status_code == 200
    assert moved_one.json()["section"] == "side"
    assert moved_one.json()["quantity"] == 1
    assert sorted(
        (item["section"], item["quantity"])
        for item in deck_items.json()
    ) == [("main", 1), ("side", 1)]


def test_workspace_player_settings_crud(workspace_client: TestClient) -> None:
    created = workspace_client.post(
        "/api/workspace/players",
        json={"name": "Second player", "is_default": True, "created_at": 1_800_000_000},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Second player"
    assert created.json()["is_default"] is True
    assert created.json()["created_at"] == 1_800_000_000

    players_after_create = workspace_client.get("/api/workspace/players").json()
    first_player = next(player for player in players_after_create if player["name"] == "Player")
    assert first_player["is_default"] is False

    updated = workspace_client.patch(
        f"/api/workspace/players/{created.json()['id']}",
        json={"name": "Renamed player", "created_at": 1_810_000_000},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed player"
    assert updated.json()["created_at"] == 1_810_000_000

    deleted = workspace_client.delete(f"/api/workspace/players/{created.json()['id']}")
    assert deleted.status_code == 204
    assert workspace_client.get("/api/workspace/players").json()[0]["is_default"] is True


def test_workspace_player_settings_validation(workspace_client: TestClient) -> None:
    duplicate = workspace_client.post("/api/workspace/players", json={"name": "Player"})
    clear_only_preferred = workspace_client.patch("/api/workspace/players/1", json={"is_default": False})
    delete_only_player = workspace_client.delete("/api/workspace/players/1")
    second_player = workspace_client.post("/api/workspace/players", json={"name": "Second player"})
    clear_preferred_with_replacement_available = workspace_client.patch(
        "/api/workspace/players/1",
        json={"is_default": False},
    )
    make_second_preferred = workspace_client.patch(
        f"/api/workspace/players/{second_player.json()['id']}",
        json={"is_default": True},
    )
    delete_linked_player = workspace_client.delete("/api/workspace/players/1")
    confirmed_delete = workspace_client.delete(
        "/api/workspace/players/1",
        params={"confirm_collection_owner_clear": "true"},
    )
    unnamed = workspace_client.post("/api/workspace/players", json={"name": "   "})

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Player with this name already exists"
    assert clear_only_preferred.status_code == 400
    assert clear_only_preferred.json()["detail"] == (
        "Choose another preferred player before clearing this one"
    )
    assert delete_only_player.status_code == 400
    assert delete_only_player.json()["detail"] == "At least one player must remain"
    assert second_player.status_code == 201
    assert clear_preferred_with_replacement_available.status_code == 400
    assert clear_preferred_with_replacement_available.json()["detail"] == (
        "Choose another preferred player before clearing this one"
    )
    assert make_second_preferred.status_code == 200
    assert make_second_preferred.json()["is_default"] is True
    players_after_replacement = workspace_client.get("/api/workspace/players").json()
    assert next(player for player in players_after_replacement if player["name"] == "Second player")[
        "is_default"
    ] is True
    assert delete_linked_player.status_code == 409
    assert delete_linked_player.json()["detail"] == {
        "message": "Player owns collections or decks",
        "collections": [{"id": 1, "name": "My collection"}],
        "decks": [],
    }
    assert confirmed_delete.status_code == 204
    collections_after_player_delete = workspace_client.get("/api/workspace/collections").json()
    assert collections_after_player_delete[0]["player_id"] is None
    assert collections_after_player_delete[0]["is_default"] is True
    assert unnamed.status_code == 422


def test_workspace_player_delete_clears_deck_owner(workspace_client: TestClient) -> None:
    created_player = workspace_client.post(
        "/api/workspace/players",
        json={"name": "Second player"},
    ).json()
    created_deck = workspace_client.post(
        "/api/workspace/decks",
        json={"name": "Loose deck", "player_id": created_player["id"]},
    ).json()
    unconfirmed = workspace_client.delete(f"/api/workspace/players/{created_player['id']}")
    confirmed = workspace_client.delete(
        f"/api/workspace/players/{created_player['id']}",
        params={"confirm_collection_owner_clear": "true"},
    )

    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["detail"] == {
        "message": "Player owns collections or decks",
        "collections": [],
        "decks": [{"id": created_deck["id"], "name": "Loose deck"}],
    }
    assert confirmed.status_code == 204
    decks = workspace_client.get("/api/workspace/decks").json()
    assert next(deck for deck in decks if deck["id"] == created_deck["id"])["player_id"] is None


def test_workspace_collection_settings_validation(workspace_client: TestClient) -> None:
    duplicate = workspace_client.post(
        "/api/workspace/collections",
        json={"name": "My collection", "player_id": 1},
    )
    update_primary_to_wishlist = workspace_client.patch(
        "/api/workspace/collections/1",
        json={"is_wishlist": True},
    )
    clear_only_primary = workspace_client.patch(
        "/api/workspace/collections/1",
        json={"is_default": False},
    )
    delete_only_collection = workspace_client.delete("/api/workspace/collections/1")
    wishlist = workspace_client.post(
        "/api/workspace/collections",
        json={"name": "Wishlist", "player_id": 1, "is_wishlist": True},
    )
    update_wishlist_to_primary = workspace_client.patch(
        f"/api/workspace/collections/{wishlist.json()['id']}",
        json={"is_default": True},
    )
    wishlist_primary = workspace_client.post(
        "/api/workspace/collections",
        json={"name": "Another wishlist", "player_id": 1, "is_default": True, "is_wishlist": True},
    )

    assert duplicate.status_code == 409
    assert update_primary_to_wishlist.status_code == 400
    assert update_primary_to_wishlist.json()["detail"] == "Wishlist collection cannot be primary"
    assert clear_only_primary.status_code == 400
    assert clear_only_primary.json()["detail"] == "Cannot clear the only primary collection"
    assert wishlist.status_code == 201
    assert update_wishlist_to_primary.status_code == 400
    assert update_wishlist_to_primary.json()["detail"] == "Wishlist collection cannot be primary"
    assert wishlist_primary.status_code == 400
    assert wishlist_primary.json()["detail"] == "Wishlist collection cannot be primary"
    assert delete_only_collection.status_code == 400
    assert delete_only_collection.json()["detail"] == "Cannot delete the only collection"


def test_workspace_suggestions_are_limited_to_fifteen(
    workspace_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_limits: list[int] = []

    def search_card_names(query: str, *, exact: bool, limit: int = 15) -> list[dict]:
        _ = query, exact
        captured_limits.append(limit)
        return []

    monkeypatch.setattr(catalog, "search_card_names", search_card_names)
    response = workspace_client.get("/api/workspace/cards/suggest", params={"query": "s"})

    assert response.status_code == 200
    assert captured_limits == [15]


def test_workspace_repeated_add_merges_quantity(workspace_client: TestClient) -> None:
    payload = {"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 2}
    first = workspace_client.post("/api/workspace/collections/1/items", json=payload)
    second = workspace_client.post("/api/workspace/collections/1/items", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["quantity"] == 4
    assert second.json()["name"] == "Swamp"
    assert second.json()["printing_id"] == 1
    assert second.json()["oracle_id"] == ORACLE_ID
    assert second.json()["keyrune_code"] == "tst"
    assert second.json()["rarity"] == "common"


def test_workspace_add_uses_selected_localization(workspace_client: TestClient) -> None:
    response = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={
            "printing_id": 1,
            "finish_id": 0,
            "language_code": "ru",
            "condition_code": "NM",
            "quantity": 1,
        },
    )

    assert response.status_code == 201
    assert response.json()["language_code"] == "ru"
    assert response.json()["language"] == "Russian"
    assert response.json()["name"] == "\u0411\u043e\u043b\u043e\u0442\u043e"


def test_workspace_add_rejects_unavailable_localization(workspace_client: TestClient) -> None:
    response = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={
            "printing_id": 1,
            "finish_id": 0,
            "language_code": "de",
            "condition_code": "NM",
            "quantity": 1,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Language is not available for this printing"


def test_workspace_update_collection_item(workspace_client: TestClient) -> None:
    created = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 2},
    ).json()

    response = workspace_client.patch(
        f"/api/workspace/collections/1/items/{created['id']}",
        json={"printing_id": 1, "finish_id": 1, "condition_code": "NM", "quantity": 3},
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["finish"] == "foil"
    assert response.json()["quantity"] == 3


def test_workspace_update_merges_identity_collision(workspace_client: TestClient) -> None:
    nonfoil = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 2},
    ).json()
    foil = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 1, "condition_code": "NM", "quantity": 3},
    ).json()

    response = workspace_client.patch(
        f"/api/workspace/collections/1/items/{foil['id']}",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 4},
    )
    items = workspace_client.get("/api/workspace/collections/1/items").json()

    assert response.status_code == 200
    assert response.json()["id"] == nonfoil["id"]
    assert response.json()["quantity"] == 6
    assert [item["id"] for item in items] == [nonfoil["id"]]


def test_workspace_delete_collection_item(workspace_client: TestClient) -> None:
    created = workspace_client.post(
        "/api/workspace/collections/1/items",
        json={"printing_id": 1, "finish_id": 0, "condition_code": "NM", "quantity": 2},
    ).json()

    response = workspace_client.delete(f"/api/workspace/collections/1/items/{created['id']}")

    assert response.status_code == 204
    assert workspace_client.get("/api/workspace/collections/1/items").json() == []


def test_workspace_printing_details_use_catalog_localization(
    workspace_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    languages: list[str | None] = []

    def get_localized_printing_faces(printing_id: int, language_code: str | None) -> list[dict]:
        _ = printing_id
        languages.append(language_code)
        return [
            {
                "face_order": 0,
                "name": "\u0411\u043e\u043b\u043e\u0442\u043e",
                "mana_cost": "",
                "type_line": "\u0411\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0435\u043c\u043b\u044f - \u0411\u043e\u043b\u043e\u0442\u043e",
                "oracle_text": "({T}: \u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 {B}.)",
                "flavor_text": None,
            }
        ]

    monkeypatch.setattr(
        scryfall,
        "get_card_json",
        lambda *args: {
            "name": "Swamp",
            "type_line": "Basic Land - Swamp",
            "oracle_text": "({T}: Add {B}.)",
        },
    )
    monkeypatch.setattr(
        catalog,
        "get_localized_printing_faces",
        get_localized_printing_faces,
    )

    response = workspace_client.get("/api/workspace/printings/1/details?language_code=ru")

    assert response.status_code == 200
    card = response.json()["card"]
    assert languages == ["ru"]
    assert card["printed_name"] == "\u0411\u043e\u043b\u043e\u0442\u043e"
    assert card["printed_type_line"] == (
        "\u0411\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0435\u043c\u043b\u044f - \u0411\u043e\u043b\u043e\u0442\u043e"
    )
    assert card["printed_text"] == "({T}: \u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 {B}.)"


def test_workspace_printing_details_hide_raw_scryfall_network_error(
    workspace_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scryfall,
        "get_card_json",
        lambda *args: (_ for _ in ()).throw(URLError("connection refused")),
    )

    response = workspace_client.get("/api/workspace/printings/1/details?language_code=en")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Scryfall is unavailable. Try again later or use already cached card data."
    )


def test_scryfall_json_and_image_are_cached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(scryfall.settings, "scryfall_cache_path", str(tmp_path))

    def request_bytes(url: str, *, accept: str) -> tuple[bytes, str]:
        calls.append(url)
        if "api.scryfall.com" in url:
            return b'{"image_uris":{"normal":"https://cards.scryfall.io/test.jpg"}}', "application/json"
        return b"image", "image/jpeg"

    monkeypatch.setattr(scryfall, "_request_bytes", request_bytes)
    first_card = scryfall.get_card_json("TST", "1", "en")
    second_card = scryfall.get_card_json("TST", "1", "en")
    first_image = scryfall.get_card_image(first_card, scryfall_id=SCRYFALL_ID, version="normal")
    second_image = scryfall.get_card_image(second_card, scryfall_id=SCRYFALL_ID, version="normal")

    assert first_card == second_card
    assert first_image == second_image
    assert len(calls) == 2


def test_scryfall_placeholder_image_falls_back_to_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    languages: list[str] = []

    def get_card_json(set_code: str, collector_number: str, language_code: str) -> dict:
        _ = set_code, collector_number
        languages.append(language_code)
        return {"image_status": "placeholder" if language_code == "ru" else "highres_scan"}

    monkeypatch.setattr(scryfall, "get_card_json", get_card_json)

    card = scryfall.get_card_json_for_image("TST", "1", "ru")

    assert card["image_status"] == "highres_scan"
    assert languages == ["ru", "en"]


def test_scryfall_missing_localized_image_falls_back_to_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    languages: list[str] = []

    def get_card_json(set_code: str, collector_number: str, language_code: str) -> dict:
        _ = set_code, collector_number
        languages.append(language_code)
        if language_code == "ru":
            raise HTTPError("https://example.test", 404, "Not Found", {}, None)
        return {"image_status": "highres_scan"}

    monkeypatch.setattr(scryfall, "get_card_json", get_card_json)

    card = scryfall.get_card_json_for_image("TST", "1", "ru")

    assert card["image_status"] == "highres_scan"
    assert languages == ["ru", "en"]


def test_scryfall_multi_face_images_are_cached_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(scryfall.settings, "scryfall_cache_path", str(tmp_path))
    card = {
        "card_faces": [
            {"image_uris": {"normal": "https://cards.scryfall.io/front.jpg"}},
            {"image_uris": {"normal": "https://cards.scryfall.io/back.jpg"}},
        ]
    }

    def request_bytes(url: str, *, accept: str) -> tuple[bytes, str]:
        _ = accept
        calls.append(url)
        return url.encode(), "image/jpeg"

    monkeypatch.setattr(scryfall, "_request_bytes", request_bytes)
    front_path, _ = scryfall.get_card_image(
        card,
        scryfall_id=SCRYFALL_ID,
        version="normal",
        face_order=0,
    )
    back_path, _ = scryfall.get_card_image(
        card,
        scryfall_id=SCRYFALL_ID,
        version="normal",
        face_order=1,
    )

    assert front_path != back_path
    assert calls == [
        "https://cards.scryfall.io/front.jpg",
        "https://cards.scryfall.io/back.jpg",
    ]


def test_scryfall_symbols_are_cached_with_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(scryfall.settings, "scryfall_cache_path", str(tmp_path))

    def request_bytes(url: str, *, accept: str) -> tuple[bytes, str]:
        _ = accept
        calls.append(url)
        if url.endswith("/symbology"):
            return (
                b'{"data":[{"symbol":"{W}","svg_uri":"https://svgs.scryfall.io/W.svg",'
                b'"english":"white mana"}]}',
                "application/json",
            )
        return b"<svg>white</svg>", "image/svg+xml"

    monkeypatch.setattr(scryfall, "_request_bytes", request_bytes)
    first_status = scryfall.update_symbols_cache()
    second_status = scryfall.update_symbols_cache()
    manifest = scryfall.get_symbols_manifest()
    filename = manifest["symbols"]["{W}"]["file"]

    assert first_status["symbol_count"] == 1
    assert second_status["symbol_count"] == 1
    assert manifest["symbols"]["{W}"]["english"] == "white mana"
    assert scryfall.get_symbol_file(filename) == tmp_path / "symbols" / "svg" / filename
    assert calls == [
        f"{scryfall.settings.scryfall_api_url}/symbology",
        "https://svgs.scryfall.io/W.svg",
        f"{scryfall.settings.scryfall_api_url}/symbology",
    ]


def test_workspace_symbol_manifest_and_svg_are_available(
    workspace_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svg_path = tmp_path / "white.svg"
    svg_path.write_text("<svg>white</svg>", encoding="utf-8")
    monkeypatch.setattr(
        scryfall,
        "get_symbols_manifest",
        lambda: {
            "updated_at": 1_780_275_600,
            "symbols": {
                "{W}": {
                    "file": "white.svg",
                    "svg_uri": "https://svgs.scryfall.io/W.svg",
                    "english": "white mana",
                }
            },
        },
    )
    monkeypatch.setattr(
        scryfall,
        "get_symbol_file",
        lambda filename: svg_path if filename == "white.svg" else None,
    )

    manifest = workspace_client.get("/api/workspace/symbols")
    svg = workspace_client.get("/api/workspace/symbols/svg/white.svg")

    assert manifest.status_code == 200
    assert manifest.json() == {
        "{W}": {
            "image_url": "/api/workspace/symbols/svg/white.svg",
            "label": "white mana",
        }
    }
    assert svg.status_code == 200
    assert svg.headers["content-type"] == "image/svg+xml"
    assert svg.text == "<svg>white</svg>"


def test_workspace_printing_image_uses_oracle_cache_after_scryfall_failure(
    workspace_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_image = tmp_path / "cached.jpg"
    cached_image.write_bytes(b"cached oracle image")
    calls: list[str] = []

    def get_cached_card_image(*, scryfall_id: str, version: str, face_order: int = 0):
        calls.append(f"cache:{scryfall_id}:{version}:{face_order}")
        if scryfall_id == SCRYFALL_ID:
            return None
        return cached_image, "image/jpeg"

    monkeypatch.setattr(scryfall, "get_cached_card_image", get_cached_card_image)
    monkeypatch.setattr(
        scryfall,
        "get_card_json_for_image",
        lambda *args: (_ for _ in ()).throw(URLError("offline")),
    )
    monkeypatch.setattr(
        catalog,
        "list_printings",
        lambda oracle_id: [
            {
                "scryfall_id": "60000000-0000-0000-0000-000000000001",
                "language_code": "en",
                "release_date": 1780099200,
            }
        ],
    )

    response = workspace_client.get("/api/workspace/printings/1/images/normal?language_code=en")

    assert response.status_code == 200
    assert response.content == b"cached oracle image"
    assert calls == [
        f"cache:{SCRYFALL_ID}:normal:0",
        "cache:60000000-0000-0000-0000-000000000001:normal:0",
    ]
