"""Trains the clause-type classifier on the real LEDGAR legal-provision corpus.

LEDGAR (Tuggener et al., 2020) is a corpus of ~70k real contract provisions
extracted from SEC filings, labeled with 100 clause-type categories
(Confidentiality, Indemnifications, Terminations, Warranties, ...). This
script trains a TF-IDF + linear classifier pipeline and saves it for use by
app/services/nlp/trained_model.py.

Run: python ml_training/train_clause_classifier.py
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline

DATA_DIR = Path(__file__).parent / "data"
MODELS_DIR = Path(__file__).parent.parent / "app" / "services" / "nlp" / "models"

# Exact category order from the dataset's ClassLabel feature
# (MAdAiLab/lex_glue_ledgar), matching the integer codes stored in the
# parquet "label" column.
LABEL_NAMES = [
    "Adjustments", "Agreements", "Amendments", "Anti-Corruption Laws", "Applicable Laws", "Approvals",
    "Arbitration", "Assignments", "Assigns", "Authority", "Authorizations", "Base Salary", "Benefits",
    "Binding Effects", "Books", "Brokers", "Capitalization", "Change In Control", "Closings",
    "Compliance With Laws", "Confidentiality", "Consent To Jurisdiction", "Consents", "Construction",
    "Cooperation", "Costs", "Counterparts", "Death", "Defined Terms", "Definitions", "Disability",
    "Disclosures", "Duties", "Effective Dates", "Effectiveness", "Employment", "Enforceability",
    "Enforcements", "Entire Agreements", "Erisa", "Existence", "Expenses", "Fees", "Financial Statements",
    "Forfeitures", "Further Assurances", "General", "Governing Laws", "Headings", "Indemnifications",
    "Indemnity", "Insurances", "Integration", "Intellectual Property", "Interests", "Interpretations",
    "Jurisdictions", "Liens", "Litigations", "Miscellaneous", "Modifications", "No Conflicts", "No Defaults",
    "No Waivers", "Non-Disparagement", "Notices", "Organizations", "Participations", "Payments",
    "Positions", "Powers", "Publicity", "Qualifications", "Records", "Releases", "Remedies",
    "Representations", "Sales", "Sanctions", "Severability", "Solvency", "Specific Performance",
    "Submission To Jurisdiction", "Subsidiaries", "Successors", "Survival", "Tax Withholdings", "Taxes",
    "Terminations", "Terms", "Titles", "Transactions With Affiliates", "Use Of Proceeds", "Vacations",
    "Venues", "Vesting", "Waiver Of Jury Trials", "Waivers", "Warranties", "Withholdings",
]


def load_split(filename: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / filename, columns=["text", "label"])


def main() -> None:
    print("Loading LEDGAR train/test splits...")
    train_df = load_split("ledgar_train.parquet")
    test_df = load_split("ledgar_test.parquet")
    print(f"{len(train_df):,} train rows, {len(test_df):,} test rows, {len(LABEL_NAMES)} categories")

    X_train, y_train = train_df["text"], train_df["label"]
    X_test, y_test = test_df["text"], test_df["label"]

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=30_000,
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
                    max_iter=30,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
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

    present_labels = sorted(set(y_test) | set(y_pred))
    target_names = [LABEL_NAMES[i] for i in present_labels]
    print(classification_report(y_test, y_pred, labels=present_labels, target_names=target_names, zero_division=0))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODELS_DIR / "clause_classifier.joblib", compress=3)

    metadata = {
        "dataset": "LEDGAR (LexGLUE), MAdAiLab/lex_glue_ledgar mirror",
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "labels": LABEL_NAMES,
        "metrics": {"accuracy": accuracy, "macro_f1": macro_f1, "micro_f1": micro_f1},
    }
    (MODELS_DIR / "clause_classifier_meta.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved model + metadata to {MODELS_DIR}")


if __name__ == "__main__":
    main()
