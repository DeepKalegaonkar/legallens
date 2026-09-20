"""Blends the TF-IDF and Legal-BERT risk detectors and fixes the decision thresholds.

The TF-IDF model is a strong, cheap baseline; the fine-tuned transformer copes
much better with wording it hasn't seen (an Indian lease versus CUAD's
commercial contracts). Each score is a probability, so they can be averaged.

Per-category thresholds are tuned on the validation contracts only and the
result is scored once on the held-out test contracts, so the reported numbers
are honest. The blend weight is chosen from WEIGHTS by held-out macro-F1.

Run after train_risk_classifier.py, train_risk_transformer.py and
export_risk_transformer.py:
    python ml_training/build_risk_ensemble.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk_eval import evaluate, summarize  # noqa: E402
from train_risk_classifier import CATEGORIES, labels_matrix, tune_thresholds  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
MODELS_DIR = Path(__file__).parent.parent / "app" / "services" / "nlp" / "models"

# Share of the score that comes from the transformer.
WEIGHTS = (0.0, 0.5, 0.7, 0.85, 1.0)


def main() -> None:
    dataset = pd.read_parquet(DATA_DIR / "cuad_clauses.parquet", columns=["title", "split", "labels"])
    validation, test = dataset[dataset["split"] == "val"], dataset[dataset["split"] == "test"]
    validation_labels, test_labels = labels_matrix(validation), labels_matrix(test)
    contracts = int(test["title"].nunique())

    tfidf_val, tfidf_test = np.load(ARTIFACTS_DIR / "tfidf_val.npy"), np.load(ARTIFACTS_DIR / "tfidf_test.npy")
    bert_val, bert_test = np.load(ARTIFACTS_DIR / "val_probs.npy"), np.load(ARTIFACTS_DIR / "test_probs.npy")

    results = {}
    for weight in WEIGHTS:
        blended_val = weight * bert_val + (1 - weight) * tfidf_val
        blended_test = weight * bert_test + (1 - weight) * tfidf_test
        thresholds = tune_thresholds(blended_val, validation_labels)
        result = evaluate(test_labels, blended_test >= thresholds, CATEGORIES, contracts)
        results[weight] = (thresholds, result)
        print(summarize(f"transformer weight {weight:.2f}", result))

    best_weight = max(results, key=lambda weight: results[weight][1]["macro_f1"])
    thresholds, result = results[best_weight]
    print(f"\nchosen weight: {best_weight}")
    for category, scores in result["per_category"].items():
        print(
            f"  {category:34} P {scores['precision']:.2f} R {scores['recall']:.2f} F1 {scores['f1']:.2f}"
            f"  gold {scores['support']:4d} flagged {scores['flagged']:4d}"
        )

    (MODELS_DIR / "risk_ensemble.json").write_text(
        json.dumps(
            {
                "categories": CATEGORIES,
                "transformer_weight": best_weight,
                "thresholds": dict(zip(CATEGORIES, thresholds.tolist())),
                "held_out_metrics": {
                    "contracts": contracts,
                    "macro_f1": result["macro_f1"],
                    "any_risk": result["any_risk"],
                    "flags_per_contract": result["flags_per_contract"],
                    "per_category": result["per_category"],
                    "by_weight": {
                        str(weight): {"macro_f1": r["macro_f1"], "any_risk_f1": r["any_risk"]["f1"]}
                        for weight, (_, r) in results.items()
                    },
                },
            },
            indent=2,
        )
    )
    print(f"saved {MODELS_DIR / 'risk_ensemble.json'}")


if __name__ == "__main__":
    main()
