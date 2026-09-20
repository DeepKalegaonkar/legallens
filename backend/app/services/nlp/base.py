from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.risk_finding import RiskSeverity


@dataclass
class RiskResult:
    risk_type: str
    severity: RiskSeverity
    confidence: float
    explanation: str


@dataclass
class ClauseResult:
    text: str
    clause_type: str
    confidence: float
    risks: list[RiskResult] = field(default_factory=list)


class ClauseAnalyzer(ABC):
    """Contract every clause-classification/risk-detection backend must satisfy.

    Swap in a real trained model by implementing this interface and wiring it
    up in api/deps.py::get_clause_analyzer — nothing else needs to change.
    """

    @abstractmethod
    def analyze(self, document_text: str) -> list[ClauseResult]:
        raise NotImplementedError
