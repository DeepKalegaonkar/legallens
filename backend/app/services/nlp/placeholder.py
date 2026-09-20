from app.models.risk_finding import RiskSeverity
from app.services.nlp.base import ClauseAnalyzer, ClauseResult, RiskResult
from app.services.nlp.segmentation import split_into_clauses

CLAUSE_KEYWORDS: dict[str, list[str]] = {
    "termination": ["terminate", "termination", "expiration", "end this agreement"],
    "confidentiality": ["confidential", "non-disclosure", "nondisclosure", "proprietary information"],
    "liability": ["liability", "liable", "damages"],
    "indemnification": ["indemnify", "indemnification", "hold harmless"],
    "payment": ["payment", "invoice", "fees", "compensation"],
    "governing_law": ["governing law", "jurisdiction", "venue"],
    "warranty": ["warrant", "warranty", "disclaims all warranties"],
    "intellectual_property": ["intellectual property", "copyright", "trademark", "patent"],
    "non_compete": ["non-compete", "noncompete", "compete with"],
}

RISK_RULES: list[tuple[str, RiskSeverity, list[str], str]] = [
    (
        "unlimited_liability",
        RiskSeverity.HIGH,
        ["unlimited liability", "without limitation", "no cap on liability"],
        "This clause does not appear to cap liability, exposing a party to unlimited financial risk.",
    ),
    (
        "no_warranty",
        RiskSeverity.HIGH,
        ["as is", "no warranty", "disclaims all warranties", "without warranty"],
        "Warranties are disclaimed, shifting the risk of defects or non-performance onto the other party.",
    ),
    (
        "broad_indemnification",
        RiskSeverity.HIGH,
        ["indemnify and hold harmless", "defend, indemnify"],
        "Requires broad indemnification that may cover losses outside this party's control.",
    ),
    (
        "penalty",
        RiskSeverity.HIGH,
        ["liquidated damages", "penalty of", "forfeit"],
        "Imposes a financial penalty that may be disproportionate to actual damages.",
    ),
    (
        "sole_discretion",
        RiskSeverity.MEDIUM,
        ["sole discretion", "in its sole discretion"],
        "Grants one party unilateral decision-making power with no objective standard.",
    ),
    (
        "auto_renewal",
        RiskSeverity.MEDIUM,
        ["automatically renew", "auto-renew", "automatic renewal"],
        "The contract renews automatically, which can create lock-in unless action is taken before a deadline.",
    ),
    (
        "unilateral_termination",
        RiskSeverity.MEDIUM,
        ["at any time for any reason", "for any reason or no reason", "without cause"],
        "Allows termination without cause, creating uncertainty for the other party.",
    ),
    (
        "non_compete",
        RiskSeverity.MEDIUM,
        ["non-compete", "noncompete"],
        "Restricts future business activity, which may be overly broad or unenforceable in some jurisdictions.",
    ),
]

class PlaceholderClauseAnalyzer(ClauseAnalyzer):
    """Rule/regex-based stand-in for the trained clause classification model.

    Implements the ClauseAnalyzer contract so it can be swapped for a real
    model later without touching routes, the database layer, or the frontend.
    Used automatically as a fallback if the trained model artifacts under
    app/services/nlp/models/ are missing.
    """

    def analyze(self, document_text: str) -> list[ClauseResult]:
        return [self._analyze_clause(text) for text in split_into_clauses(document_text)]

    def _analyze_clause(self, text: str) -> ClauseResult:
        clause_type, confidence = self._classify(text)
        return ClauseResult(
            text=text,
            clause_type=clause_type,
            confidence=confidence,
            risks=self._detect_risks(text),
        )

    def _classify(self, text: str) -> tuple[str, float]:
        lowered = text.lower()
        best_type = "other"
        best_hits = 0
        for clause_type, keywords in CLAUSE_KEYWORDS.items():
            hits = sum(1 for keyword in keywords if keyword in lowered)
            if hits > best_hits:
                best_hits = hits
                best_type = clause_type

        if best_hits == 0:
            return "other", 0.4
        return best_type, round(min(0.55 + 0.12 * best_hits, 0.95), 2)

    def _detect_risks(self, text: str) -> list[RiskResult]:
        lowered = text.lower()
        risks: list[RiskResult] = []
        for risk_type, severity, keywords, explanation in RISK_RULES:
            hits = [keyword for keyword in keywords if keyword in lowered]
            if not hits:
                continue
            risks.append(
                RiskResult(
                    risk_type=risk_type,
                    severity=severity,
                    confidence=round(min(0.6 + 0.1 * len(hits), 0.95), 2),
                    explanation=explanation,
                )
            )
        return risks
