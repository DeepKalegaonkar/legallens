from app.models.risk_finding import RiskSeverity
from app.services.nlp.base import RiskResult
from app.services.nlp.rules import (
    AUTO_RENEWAL,
    INDEMNIFICATION,
    UNCAPPED_LIABILITY,
    UNILATERAL_ARBITRATOR,
    apply_rules,
)


def types(text, risks=()):
    return {risk.risk_type for risk in apply_rules(text, list(risks))}


def model_uncapped():
    return RiskResult(UNCAPPED_LIABILITY, RiskSeverity.HIGH, 0.68, "model said so")


# --- indemnification --------------------------------------------------------


def test_indemnity_duty_is_flagged_and_broad_wording_is_high():
    text = "The Service Provider shall defend, indemnify and hold harmless the Client from any and all claims."
    (risk,) = apply_rules(text, [])
    assert risk.risk_type == INDEMNIFICATION
    assert risk.severity is RiskSeverity.HIGH
    assert risk.source == "rule"


def test_narrow_indemnity_is_medium():
    text = "Each party shall indemnify the other against third-party claims caused by its breach."
    (risk,) = apply_rules(text, [])
    assert risk.severity is RiskSeverity.MEDIUM


def test_a_disclaimer_of_indemnity_is_not_flagged():
    assert INDEMNIFICATION not in types("The Client shall have no obligation to indemnify the Service Provider.")


def test_a_mention_of_indemnity_without_a_duty_is_not_flagged():
    assert INDEMNIFICATION not in types("The indemnification procedure is described in Schedule C.")


# --- auto-renewal -----------------------------------------------------------


def test_automatic_renewal_variants_are_flagged():
    for text in (
        "This Agreement shall automatically renew for successive one year periods.",
        "The term will be automatically extended unless notice is given.",
        "The subscription renews automatically each year.",
        "This is an auto-renewing agreement.",
        "The licence is an evergreen licence.",
    ):
        assert AUTO_RENEWAL in types(text), text


def test_a_clause_saying_it_will_not_auto_renew_is_not_flagged():
    assert AUTO_RENEWAL not in types("This Agreement shall not automatically renew.")


def test_a_fixed_term_is_not_flagged():
    assert AUTO_RENEWAL not in types("This Agreement continues for an initial term of two (2) years.")


# --- unilateral arbitrator --------------------------------------------------


def test_arbitrator_appointed_by_one_party_is_flagged():
    for text in (
        "Any dispute shall be referred to a sole arbitrator appointed by the Client.",
        "The disputes shall be settled by an arbitrator nominated solely by the Lessor.",
        "The Company shall appoint the sole arbitrator.",
    ):
        assert UNILATERAL_ARBITRATOR in types(text), text


def test_neutral_or_joint_appointment_is_not_flagged():
    for text in (
        "The dispute goes to a sole arbitrator appointed by mutual agreement of the parties.",
        "The arbitrator shall be appointed by the High Court on application of either party.",
        "The arbitrator shall be appointed jointly by the Client and the Service Provider.",
        "The arbitrator shall be appointed by the Client and the Service Provider.",
        "Each party shall appoint one arbitrator and the two shall appoint a third.",
        "Disputes shall be resolved by arbitration under the Arbitration and Conciliation Act, 1996.",
    ):
        assert UNILATERAL_ARBITRATOR not in types(text), text


# --- liability direction ----------------------------------------------------


def test_a_liability_cap_removes_the_models_uncapped_flag():
    text = "The total aggregate liability of the Client shall not exceed the fees paid in the preceding month."
    assert UNCAPPED_LIABILITY not in types(text, [model_uncapped()])


def test_unlimited_liability_is_added_when_the_model_missed_it():
    text = "The liability of the Service Provider under this Agreement shall be unlimited."
    (risk,) = apply_rules(text, [])
    assert risk.risk_type == UNCAPPED_LIABILITY
    assert risk.severity is RiskSeverity.HIGH
    assert risk.source == "rule"


def test_unlimited_liability_keeps_the_models_own_finding_instead_of_duplicating_it():
    text = "The liability of the Service Provider shall be unlimited."
    found = apply_rules(text, [model_uncapped()])
    assert [risk.source for risk in found] == ["model"]


def test_unlimited_wins_when_one_clause_caps_one_party_and_not_the_other():
    text = (
        "The Client's liability shall not exceed the fees paid, but the Service Provider's "
        "liability shall be unlimited."
    )
    assert UNCAPPED_LIABILITY in types(text, [model_uncapped()])


def test_nothing_shall_limit_liability_counts_only_without_a_legal_carve_out():
    assert UNCAPPED_LIABILITY in types("Nothing in this Agreement shall limit or exclude the Provider's liability.")
    assert UNCAPPED_LIABILITY not in types(
        "Nothing in this Agreement limits or excludes liability for fraud or death or personal injury."
    )


def test_clauses_that_say_nothing_about_liability_are_untouched():
    kept = RiskResult("exclusivity", RiskSeverity.MEDIUM, 0.8, "why")
    assert apply_rules("The Service Provider shall work exclusively for the Client.", [kept]) == [kept]
