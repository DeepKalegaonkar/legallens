"""Deterministic rules that cover what the trained risk models cannot.

CUAD has no label for indemnities, auto-renewal or one-sided arbitrator
appointment, and a bag-of-words model cannot read the direction of a liability
clause ("shall not exceed" vs "shall be unlimited"). Those are exactly the cases
where a precise pattern beats a statistical guess, so they are handled here.

The rules run *after* the models and only ever:
  - add a finding the models have no category for (indemnification,
    auto_renewal, unilateral_arbitrator_appointment), or
  - correct the model's uncapped_liability call when the clause text plainly
    says the liability is capped (drop it) or plainly says it is unlimited (add it).

Every finding produced here carries source="rule", so the report can say it came
from a pattern match rather than show a model probability.
"""

import re

from app.models.risk_finding import RiskSeverity
from app.services.nlp.base import RiskResult

RULE_SOURCE = "rule"

# Nominal value: a rule either matches or it does not. It only orders findings
# within a severity; the report shows "rule match" instead of a percentage.
RULE_CONFIDENCE = 0.9

UNCAPPED_LIABILITY = "uncapped_liability"
INDEMNIFICATION = "indemnification"
AUTO_RENEWAL = "auto_renewal"
UNILATERAL_ARBITRATOR = "unilateral_arbitrator_appointment"


def _pattern(expression: str) -> re.Pattern[str]:
    return re.compile(expression, re.IGNORECASE)


# --- Indemnification -------------------------------------------------------

_INDEMNITY = _pattern(
    r"\b(?:shall|will|must|agrees?\s+to|undertakes?\s+to|hereby)\b[^.;]{0,60}?"
    r"\b(?:indemnif(?:y|ies)|hold\s+harmless)\b"
)
# "shall have no obligation to indemnify", "shall not be required to indemnify"
_INDEMNITY_NEGATED = _pattern(r"\b(?:no|not|never)\b[^.;]{0,50}\bindemnif")
_INDEMNITY_BROAD = _pattern(r"\bany\s+and\s+all\b")

# --- Auto-renewal ----------------------------------------------------------

_AUTO_RENEWAL = [
    _pattern(r"\bautomatic(?:ally)?\b[^.;]{0,40}\b(?:renew\w*|extend\w*)"),
    _pattern(r"\b(?:renew\w*|extend\w*)\b[^.;]{0,30}\bautomatic(?:ally)?\b"),
    _pattern(r"\bauto[- ]?renew"),
    _pattern(r"\bevergreen\b"),
]
_AUTO_RENEWAL_NEGATED = _pattern(r"\b(?:not|no|never)\b[^.;]{0,20}\bautomatic")

# --- Unilateral arbitrator appointment -------------------------------------

_APPOINTED_BY = _pattern(
    r"\barbitrator\b[^.;]{0,80}?\b(?:appointed|nominated|selected|designated|chosen)\s+"
    r"(?:solely\s+|unilaterally\s+|exclusively\s+)?by\s+(?:the\s+)?(?P<who>(?:[a-z']+\s?){1,3})"
)
_PARTY_APPOINTS = _pattern(
    r"\b(?P<who>[a-z][a-z' ]{1,40}?)\s+(?:shall|may|will|has\s+the\s+right\s+to)\s+"
    r"(?:solely\s+|unilaterally\s+|exclusively\s+)?(?:appoint|nominate|select|designate)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?:sole\s+|single\s+)?arbitrator"
)
# Appointers that are neutral or joint, so the appointment is not one-sided.
_NEUTRAL_APPOINTER = _pattern(
    r"\b(?:court|justice|institution|centre|center|council|tribunal|mutual|mutually|jointly|both|"
    r"each|parties|party\s+and|agreement|agreed|and|two|presiding|independent|"
    r"appointing\s+authority|chamber|association|commission)\b"
)

# --- Liability cap vs. unlimited -------------------------------------------

_LIABILITY_WORDS = _pattern(r"\b(?:liabilit\w*|damages|indemnit\w*|losses|loss)\b")
_CAP_LANGUAGE = _pattern(
    r"\b(?:not\s+(?:to\s+)?exceed|shall\s+not\s+be\s+(?:greater|more)\s+than|no\s+more\s+than|"
    r"capped\s+at|(?:be|is|are)\s+limited\s+to|"
    r"in\s+no\s+event[^.;]{0,100}?\bexceed|maximum\s+(?:aggregate\s+)?liability)"
)
_UNLIMITED_STRONG = [
    _pattern(r"\b(?:unlimited|uncapped)\b"),
    _pattern(r"\bwithout\s+(?:any\s+)?(?:limit|limitation|cap)\b"),
    _pattern(r"\bno\s+(?:limit|limitation|cap)\s+(?:on|to|of)\b"),
]
_UNLIMITED_NEGATED = _pattern(r"\b(?:not|never)\s+(?:be\s+)?(?:unlimited|uncapped)\b")
# "Nothing in this agreement shall limit ... liability": counts as unlimited only
# when it is not the usual carve-out for fraud, death or matters the law will not
# let a party exclude.
_NOTHING_LIMITS = _pattern(r"\bnothing\b[^.;]{0,60}\b(?:limit|exclude|restrict)\b[^.;]{0,60}\bliabilit")
_LEGAL_CARVE_OUT = _pattern(
    r"\b(?:fraud\w*|death|personal\s+injury|wilful|willful|gross\s+negligence|misrepresentation|"
    r"cannot\s+be\s+(?:limited|excluded)|by\s+law|applicable\s+law|statute|statutory)\b"
)


def _has_cap_language(text: str) -> bool:
    return bool(_CAP_LANGUAGE.search(text))


def _says_unlimited(text: str) -> bool:
    if not _LIABILITY_WORDS.search(text):
        return False
    if _UNLIMITED_NEGATED.search(text):
        return False
    if any(pattern.search(text) for pattern in _UNLIMITED_STRONG):
        return True
    return bool(_NOTHING_LIMITS.search(text)) and not _LEGAL_CARVE_OUT.search(text)


def _is_indemnity(text: str) -> bool:
    return bool(_INDEMNITY.search(text)) and not _INDEMNITY_NEGATED.search(text)


def _is_auto_renewal(text: str) -> bool:
    if _AUTO_RENEWAL_NEGATED.search(text):
        return False
    return any(pattern.search(text) for pattern in _AUTO_RENEWAL)


def _is_one_party(who: str) -> bool:
    return bool(who.strip()) and not _NEUTRAL_APPOINTER.search(who)


def _is_unilateral_arbitrator(text: str) -> bool:
    match = _APPOINTED_BY.search(text)
    if match and _is_one_party(match.group("who")):
        return True
    match = _PARTY_APPOINTS.search(text)
    return bool(match and _is_one_party(match.group("who")))


def _rule_risk(risk_type: str, severity: RiskSeverity, explanation: str) -> RiskResult:
    return RiskResult(
        risk_type=risk_type,
        severity=severity,
        confidence=RULE_CONFIDENCE,
        explanation=explanation,
        source=RULE_SOURCE,
    )


def apply_rules(text: str, risks: list[RiskResult]) -> list[RiskResult]:
    """Return `risks` corrected and extended by the rules for this clause."""
    result = list(risks)

    # Liability direction. "Unlimited" wins over cap language, because a clause
    # can cap one party and leave the other unlimited (both in one sentence).
    if _says_unlimited(text):
        if not any(risk.risk_type == UNCAPPED_LIABILITY for risk in result):
            result.append(
                _rule_risk(
                    UNCAPPED_LIABILITY,
                    RiskSeverity.HIGH,
                    "This clause states that liability is unlimited or is expressly not capped, "
                    "exposing a party to unlimited financial risk.",
                )
            )
    elif _has_cap_language(text):
        result = [risk for risk in result if risk.risk_type != UNCAPPED_LIABILITY]

    if _is_indemnity(text) and not any(risk.risk_type == INDEMNIFICATION for risk in result):
        broad = bool(_INDEMNITY_BROAD.search(text))
        result.append(
            _rule_risk(
                INDEMNIFICATION,
                RiskSeverity.HIGH if broad else RiskSeverity.MEDIUM,
                "One party must cover the other's losses and legal costs, and the wording is broad "
                "(\"any and all\"). Check whether it is mutual, capped and limited to third-party claims."
                if broad
                else "One party must cover the other's losses and legal costs. Check whether it is "
                "mutual, capped and limited to third-party claims.",
            )
        )

    if _is_auto_renewal(text):
        result.append(
            _rule_risk(
                AUTO_RENEWAL,
                RiskSeverity.MEDIUM,
                "The contract renews by itself unless notice is given in time. Note the notice "
                "deadline, because missing it commits you to another term.",
            )
        )

    if _is_unilateral_arbitrator(text):
        result.append(
            _rule_risk(
                UNILATERAL_ARBITRATOR,
                RiskSeverity.HIGH,
                "One party appoints the arbitrator alone. That can compromise neutrality, and "
                "courts in India have held that a party with an interest in the outcome should "
                "not unilaterally appoint the sole arbitrator, so the clause may be open to challenge.",
            )
        )

    return result
