import time
from pathlib import Path

import pytest

from app.services.nlp.trained_model import TrainedClauseAnalyzer

SAMPLE = Path(__file__).parent.parent.parent / "samples" / "sample_services_agreement.txt"


@pytest.fixture(scope="module")
def results():
    analyzer = TrainedClauseAnalyzer()
    started = time.perf_counter()
    analysed = analyzer.analyze(SAMPLE.read_text(encoding="utf-8"))
    return {"clauses": analysed, "seconds": time.perf_counter() - started}


def risk_types_by_label(analysed):
    return {clause.text.split()[0].rstrip("."): {risk.risk_type for risk in clause.risks} for clause in analysed}


def test_sample_agreement_named_risks_are_found_on_the_right_clauses(results):
    found = risk_types_by_label(results["clauses"])

    assert "exclusivity" in found["4(a)"]
    assert "non_compete" in found["4(b)"]
    assert "ip_ownership_assignment" in found["6(a)"]
    assert "irrevocable_or_perpetual_license" in found["6(b)"]
    assert "liquidated_damages" in found["11(b)"]
    assert "termination_for_convenience" in found["13(a)"]
    assert "change_of_control" in found["14"]
    assert "anti_assignment" in found["15(a)"]


def test_routine_boilerplate_is_not_flagged_with_a_named_risk(results):
    found = risk_types_by_label(results["clauses"])

    for label in ("1(c)", "22(a)", "22(b)", "22(c)", "17", "18"):
        assert not found[label], f"{label} should not carry a risk"


def test_every_finding_has_a_probability_and_a_severity(results):
    for clause in results["clauses"]:
        for risk in clause.risks:
            assert 0.0 < risk.confidence <= 1.0
            assert risk.severity.value in {"low", "medium", "high", "critical"}


def test_a_whole_agreement_is_analysed_in_a_few_seconds(results):
    assert results["seconds"] < 10
