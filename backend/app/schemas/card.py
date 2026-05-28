from pydantic import BaseModel, ConfigDict


class CardRead(BaseModel):
    id: int
    scryfall_id: str
    name: str
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    image_small: str | None = None
    image_normal: str | None = None

    model_config = ConfigDict(from_attributes=True)

