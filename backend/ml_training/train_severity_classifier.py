"""Trains a general-purpose Low/Medium/High risk-severity classifier.

Unlike train_risk_classifier.py (which predicts *which* of 19 specific CUAD
risk categories a clause matches), this model predicts *how severe* a clause
is, directly, from a broader real dataset: data/external/final_merged_dataset.csv
(11k+ real clauses), which combines CUAD-derived clauses with a real Indian
legal-contract-clauses dataset. This gives the risk pipeline a second,
independent signal that isn't limited to CUAD's US-centric category taxonomy
-- see app/services/nlp/trained_model.py for how it's combined with the
category classifier.

The source CSV isn't from a stable public URL (it's the output of a prior
project's own data-prep pipeline), so it isn't in download_data.py -- copy it
to ml_training/data/external/final_merged_dataset.csv before running this.

Run: python ml_training/train_severity_classifier.py
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

DATA_PATH = Path(__file__).parent / "data" / "external" / "final_merged_dataset.csv"
MODELS_DIR = Path(__file__).parent.parent / "app" / "services" / "nlp" / "models"

RANDOM_STATE = 42


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH} not found. Copy final_merged_dataset.csv there first "
            "(see this script's module docstring)."
        )

    print("Loading merged risk-severity dataset...")
    df = pd.read_csv(DATA_PATH).dropna(subset=["clause_text", "risk"])
    df = df[df["clause_text"].str.len() > 15]
    df = df.drop_duplicates(subset=["clause_text"])
    print(f"{len(df):,} labeled clauses")
    print(df["risk"].value_counts().to_string())

    X_train, X_test, y_train, y_test = train_test_split(
        df["clause_text"],
        df["risk"],
        test_size=0.15,
        stratify=df["risk"],
        random_state=RANDOM_STATE,
    )

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=20_000,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                    min_df=2,
                    stop_words="english",
                ),
            ),
            (
                "clf",
                SGDClassifier(
                    loss="log_loss",
                    alpha=1e-5,
                    max_iter=50,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    print("Training TF-IDF + SGDClassifier pipeline...")
    pipeline.fit(X_train, y_train)

    print("Evaluating on held-out test split...")
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    macro_f1 = f1_score(y_test, y_pred, average="macro")
    micro_f1 = f1_score(y_test, y_pred, average="micro")
    print(f"accuracy={accuracy:.4f}  macro_f1={macro_f1:.4f}  micro_f1={micro_f1:.4f}")
    print(classification_report(y_test, y_pred, zero_division=0))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODELS_DIR / "severity_classifier.joblib", compress=3)

    metadata = {
        "dataset": "final_merged_dataset.csv (CUAD-derived clauses + Indian legal-contract-clauses dataset, merged by a prior project's data-prep pipeline)",
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "labels": sorted(df["risk"].unique().tolist()),
        "metrics": {"accuracy": accuracy, "macro_f1": macro_f1, "micro_f1": micro_f1},
    }
    (MODELS_DIR / "severity_classifier_meta.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved model + metadata to {MODELS_DIR}")


if __name__ == "__main__":
    main()
