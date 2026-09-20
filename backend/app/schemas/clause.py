from pydantic import BaseModel, ConfigDict

from app.schemas.risk import RiskOut


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_index: int
    text: str
    clause_type: str
    confidence: float
    risks: list[RiskOut]
