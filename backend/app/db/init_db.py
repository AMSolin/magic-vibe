from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Card, Collection, Deck, MODELS

DEV_CARDS = [
    {
        "card_uuid": "00000000-0000-0000-0000-000000000001",
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    },
    {
        "card_uuid": "00000000-0000-0000-0000-000000000002",
        "name": "Counterspell",
        "mana_cost": "{U}{U}",
        "type_line": "Instant",
        "oracle_text": "Counter target spell.",
    },
    {
        "card_uuid": "00000000-0000-0000-0000-000000000003",
        "name": "Sol Ring",
        "mana_cost": "{1}",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}{C}.",
    },
    {
        "card_uuid": "00000000-0000-0000-0000-000000000004",
        "name": "Swords to Plowshares",
        "mana_cost": "{W}",
        "type_line": "Instant",
        "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
    },
    {
        "card_uuid": "00000000-0000-0000-0000-000000000005",
        "name": "Llanowar Elves",
        "mana_cost": "{G}",
        "type_line": "Creature - Elf Druid",
        "oracle_text": "{T}: Add {G}.",
    },
    {
        "card_uuid": "00000000-0000-0000-0000-000000000006",
        "name": "Demonic Tutor",
        "mana_cost": "{1}{B}",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for a card, put that card into your hand, then shuffle.",
    },
]


def init_db() -> None:
    _ = MODELS
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.scalar(select(Card.id).limit(1)) is not None:
            return

        db.add_all(Card(**card_data) for card_data in DEV_CARDS)
        default_collection = Collection(name="My collection", is_default=True)
        wishlist_collection = Collection(name="Wishlist", is_wishlist=True)
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
