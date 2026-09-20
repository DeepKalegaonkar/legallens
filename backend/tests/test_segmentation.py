from pathlib import Path

from app.services.nlp.segmentation import MAX_CLAUSE_CHARS, segment, split_into_clauses

SAMPLE = Path(__file__).parent.parent.parent / "samples" / "sample_services_agreement.txt"


def test_numbered_subclauses_are_split_and_labelled_with_the_parent_number():
    text = (
        "4. Exclusivity and Non-Competition\n"
        "(a) During the Term, the Provider shall work exclusively for the Client and no one else.\n"
        "(b) For three years after the Term, the Provider shall not engage in any competing business.\n"
    )

    clauses = split_into_clauses(text)

    assert [clause.split()[0] for clause in clauses] == ["4(a)", "4(b)"]
    assert "exclusively" in clauses[0]


def test_heading_on_its_own_line_is_attached_to_the_paragraph_after_it():
    text = (
        "8. MINIMUM NUMBER OF TOURNAMENTS\n\n"
        "A.  In each calendar year the consultant shall compete in a minimum number of events.\n"
    )

    clauses = split_into_clauses(text)

    assert len(clauses) == 1
    assert clauses[0].startswith("8. MINIMUM NUMBER OF TOURNAMENTS A.")


def test_section_title_before_a_numbered_clause_is_dropped():
    text = "WHEREAS\n1. The Lessor is the owner of the premises and is entitled to let them out.\n"

    assert split_into_clauses(text)[0].startswith("1. The Lessor")


def test_page_markers_blank_fields_and_signature_lines_are_removed():
    text = (
        "Page 1 of 7\n"
        "1. The Client shall pay Rs. ______________ per month as rent for the premises used.\n"
        "Signed for the Client: ____________________\n"
        "Signed for the Provider: ____________________\n"
    )

    clauses = split_into_clauses(text)

    assert clauses == ["1. The Client shall pay Rs. ___ per month as rent for the premises used."]


def test_very_long_clauses_are_cut_at_sentence_boundaries():
    sentence = "The Supplier shall deliver the goods to the Buyer on the agreed date and place. "
    clauses = split_into_clauses("1. " + sentence * 60)

    assert len(clauses) > 1
    assert all(len(clause) <= MAX_CLAUSE_CHARS for clause in clauses)


def test_offsets_point_back_at_the_source_text():
    text = "1. First clause about payment terms and the schedule of fees due each month.\n\n" \
           "2. Second clause about termination and the notice period that applies to both parties.\n"

    for piece in segment(text):
        assert text[piece.start : piece.end].split()[:3] == piece.text.split()[:3]


def test_sample_agreement_yields_one_clause_per_subclause():
    clauses = split_into_clauses(SAMPLE.read_text(encoding="utf-8"))

    labels = {clause.split()[0] for clause in clauses}
    assert {"4(a)", "4(b)", "10(a)", "10(b)", "13(a)", "19(c)"} <= labels
    assert not any(clause.startswith("Signed for") for clause in clauses)
