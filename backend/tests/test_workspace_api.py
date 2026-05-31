import sqlite3
from collections.abc import Generator
from pathlib import Path
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

    options_response = workspace_client.get(
        f"/api/workspace/cards/{ORACLE_ID}/printings",
        params={"preferred_language_code": "en"},
    )
    assert options_response.status_code == 200
    assert options_response.json()["printings"][0]["finishes"] == [
        {"id": 0, "name": "nonfoil"},
        {"id": 1, "name": "foil"},
    ]


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
