from pydantic import BaseModel, ConfigDict

from app.models.risk_finding import RiskSeverity


class RiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    risk_type: str
    severity: RiskSeverity
    confidence: float
    explanation: str
    source: str = "model"
