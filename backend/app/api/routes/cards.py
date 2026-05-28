from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.card import Card
from app.schemas.card import CardRead

router = APIRouter()


@router.get("", response_model=list[CardRead])
def list_cards(
    search: str | None = Query(default=None, min_length=2),
    db: Session = Depends(get_db),
) -> list[Card]:
    statement = select(Card).order_by(Card.name).limit(50)
    if search:
        statement = select(Card).where(Card.name.ilike(f"%{search}%")).order_by(Card.name).limit(50)

    return list(db.scalars(statement))

