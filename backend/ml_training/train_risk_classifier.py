"""Trains the TF-IDF half of the risk detector on whole clauses from real CUAD contracts.

The model sees what it will see in production: clauses cut out of full
contracts by app/services/nlp/segmentation.py, most of them benign. Each of the
19 risk categories gets its own logistic-regression detector over TF-IDF word
1-2-grams (stop words are kept -- "not", "no" and "shall not" carry the
direction of a clause; classes are re-weighted since risks are rare), so one
clause can carry several risks.

It is fitted on the training + validation contracts and scored once on CUAD's
held-out test contracts. Out-of-fold predictions for the validation contracts
(grouped by contract, so a contract is never predicted by a model that saw it)
and the test predictions are saved for build_risk_ensemble.py, which blends
this model with the fine-tuned transformer.

Run after download_data.py and build_clause_dataset.py:
    python ml_training/train_risk_classifier.py
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.nlp.risk_taxonomy import RISK_CATEGORY_SEVERITY  # noqa: E402
from risk_eval import evaluate, summarize  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
MODELS_DIR = Path(__file__).parent.parent / "app" / "services" / "nlp" / "models"

CATEGORIES = sorted(RISK_CATEGORY_SEVERITY)
REGULARIZATION = 8.0
MAX_FEATURES = 150_000
FOLDS = 5
THRESHOLD_GRID = np.arange(0.05, 0.951, 0.025)


def labels_matrix(df: pd.DataFrame) -> np.ndarray:
    return np.array([[category in labels for category in CATEGORIES] for labels in df["labels"]])


def fit(texts: list[str], labels: np.ndarray) -> dict:
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2), sublinear_tf=True, min_df=2, max_features=MAX_FEATURES, dtype=np.float32
    )
    features = vectorizer.fit_transform(texts)
    coefficients, intercepts = [], []
    for column in range(labels.shape[1]):
        model = LogisticRegression(C=REGULARIZATION, class_weight="balanced", solver="liblinear", max_iter=200)
        model.fit(features, labels[:, column])
        coefficients.append(model.coef_[0].astype(np.float32))
        intercepts.append(model.intercept_[0])
    return {"vectorizer": vectorizer, "coef": np.vstack(coefficients), "intercept": np.array(intercepts)}


def probabilities(model: dict, texts: list[str]) -> np.ndarray:
    scores = model["vectorizer"].transform(texts) @ model["coef"].T + model["intercept"]
    return 1.0 / (1.0 + np.exp(-np.asarray(scores)))


def fit_and_predict(train_texts, train_labels, predict_texts) -> np.ndarray:
    return probabilities(fit(train_texts, train_labels), predict_texts)


def out_of_fold(df: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    texts = df["text"].tolist()
    folds = list(GroupKFold(FOLDS).split(df, groups=df["title"]))
    results = Parallel(n_jobs=min(FOLDS, 6))(
        delayed(fit_and_predict)([texts[i] for i in train], labels[train], [texts[i] for i in valid])
        for train, valid in folds
    )
    predictions = np.zeros(labels.shape)
    for (_, valid), result in zip(folds, results):
        predictions[valid] = result
    return predictions


def tune_thresholds(predictions: np.ndarray, labels: np.ndarray) -> np.ndarray:
    thresholds = []
    for column in range(labels.shape[1]):
        gold = labels[:, column]
        best_f1, best_threshold = -1.0, 0.5
        for threshold in THRESHOLD_GRID:
            flagged = predictions[:, column] >= threshold
            tp = (flagged & gold).sum()
            f1 = 2 * tp / (flagged.sum() + gold.sum()) if tp else 0.0
            if f1 > best_f1:
                best_f1, best_threshold = f1, threshold
        thresholds.append(round(float(best_threshold), 3))
    return np.array(thresholds)


def main() -> None:
    dataset = pd.read_parquet(DATA_DIR / "cuad_clauses.parquet")
    development = dataset[dataset["split"] != "test"].reset_index(drop=True)
    test = dataset[dataset["split"] == "test"].reset_index(drop=True)
    dev_labels, test_labels = labels_matrix(development), labels_matrix(test)
    is_validation = (development["split"] == "val").to_numpy()

    print(f"Fitting on {development['title'].nunique()} contracts, scoring on {test['title'].nunique()} unseen ones...")
    oof = out_of_fold(development, dev_labels)
    thresholds = tune_thresholds(oof, dev_labels)
    model = fit(development["text"].tolist(), dev_labels)
    test_probabilities = probabilities(model, test["text"].tolist())

    result = evaluate(test_labels, test_probabilities >= thresholds, CATEGORIES, test["title"].nunique())
    print(summarize("TF-IDF, held-out contracts", result))
    for category, scores in result["per_category"].items():
        print(
            f"  {category:34} P {scores['precision']:.2f} R {scores['recall']:.2f} F1 {scores['f1']:.2f}"
            f"  gold {scores['support']:4d} flagged {scores['flagged']:4d}"
        )

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    np.save(ARTIFACTS_DIR / "tfidf_val.npy", oof[is_validation])
    np.save(ARTIFACTS_DIR / "tfidf_test.npy", test_probabilities)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({**model, "categories": CATEGORIES}, MODELS_DIR / "risk_classifier.joblib", compress=3)
    (MODELS_DIR / "risk_classifier_meta.json").write_text(
        json.dumps(
            {
                "dataset": "CUAD (Contract Understanding Atticus Dataset), chenghao/cuad_qa mirror, cut into clauses",
                "granularity": "clause-level, multi-label, per-category logistic regression on TF-IDF 1-2-grams",
                "fitted_on_contracts": int(development["title"].nunique()),
                "standalone_thresholds": dict(zip(CATEGORIES, thresholds.tolist())),
                "held_out_metrics": {
                    "contracts": int(test["title"].nunique()),
                    "macro_f1": result["macro_f1"],
                    "any_risk": result["any_risk"],
                    "flags_per_contract": result["flags_per_contract"],
                },
            },
            indent=2,
        )
    )
    print(f"Saved model + metadata to {MODELS_DIR}")


if __name__ == "__main__":
    main()
