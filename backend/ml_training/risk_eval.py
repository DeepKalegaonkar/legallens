"""Clause-level evaluation of a risk detector against CUAD's expert labels.

A detector is scored on held-out contracts: for each of the risk categories it
must flag the clauses experts labelled with that category. Precision here is a
lower bound -- CUAD only labels 41 categories, so a flag on a clause that is
genuinely risky in some other way still counts as a miss.
"""

import numpy as np


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def evaluate(gold: np.ndarray, predicted: np.ndarray, categories: list[str], n_contracts: int) -> dict:
    """gold, predicted: boolean arrays of shape (clauses, categories)."""
    per_category = {}
    for j, category in enumerate(categories):
        tp = int((gold[:, j] & predicted[:, j]).sum())
        fp = int((~gold[:, j] & predicted[:, j]).sum())
        fn = int((gold[:, j] & ~predicted[:, j]).sum())
        p, r, f = prf(tp, fp, fn)
        per_category[category] = {"precision": p, "recall": r, "f1": f, "support": tp + fn, "flagged": tp + fp}

    supported = [v for v in per_category.values() if v["support"] > 0]
    any_gold, any_pred = gold.any(axis=1), predicted.any(axis=1)
    tp, fp, fn = int((any_gold & any_pred).sum()), int((~any_gold & any_pred).sum()), int((any_gold & ~any_pred).sum())
    p, r, f = prf(tp, fp, fn)
    return {
        "macro_f1": float(np.mean([v["f1"] for v in supported])),
        "any_risk": {"precision": p, "recall": r, "f1": f},
        "flags_per_contract": float(predicted.sum() / n_contracts),
        "clauses_flagged": float(any_pred.mean()),
        "per_category": per_category,
    }


def summarize(name: str, result: dict) -> str:
    a = result["any_risk"]
    return (
        f"{name:34} macro-F1 {result['macro_f1']:.3f} | any-risk P {a['precision']:.2f} R {a['recall']:.2f} F1 {a['f1']:.2f}"
        f" | {result['flags_per_contract']:.1f} flags/contract ({result['clauses_flagged']:.1%} of clauses)"
    )
