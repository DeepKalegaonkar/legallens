"""ClauseAnalyzer backed by real trained scikit-learn models.

Three independently trained TF-IDF + linear classifiers, produced by the
scripts in ml_training/ from real legal-contract corpora:
  - clause_classifier.joblib: 100-class clause-type classifier trained on
    LEDGAR (real SEC contract provisions).
  - risk detectors: 19 per-category, multi-label (a clause can carry several
    risks), trained on whole clauses cut from real CUAD contracts and scored on
    held-out contracts -- see ml_training/. Two models are blended: a TF-IDF
    logistic regression (risk_classifier.joblib) and a fine-tuned Legal-BERT
    served as int8 ONNX (risk_transformer.onnx); risk_ensemble.json holds the
    blend weight and the per-category thresholds.
  - severity_classifier.joblib: Low/Medium/High severity classifier trained
    on a broader, India-inclusive dataset (CUAD clauses + a real Indian
    legal-contract-clauses dataset). It's optional -- see _load_optional().

On top of the models, services/nlp/rules.py adds deterministic rules for indemnities,
auto-renewal, one-sided arbitrator appointment and the direction of liability caps.

Raising FileNotFoundError from __init__ for the two required models (rather
than swallowing it) is intentional: api/deps.py catches it and falls back to
PlaceholderClauseAnalyzer, so missing/untrained models degrade gracefully
instead of crashing the API.
"""

import json
from pathlib import Path

import joblib
import numpy as np

from app.models.risk_finding import RiskSeverity
from app.services.nlp.base import ClauseAnalyzer, ClauseResult, RiskResult
from app.services.nlp.onnx_risk import OnnxRiskDetector
from app.services.nlp.risk_taxonomy import (
    GENERAL_RISK_EXPLANATION,
    GENERAL_RISK_TYPE,
    RISK_CATEGORY_EXPLANATIONS,
    RISK_CATEGORY_SEVERITY,
    SEVERITY_LABEL_TO_ENUM,
)
from app.services.nlp.rules import apply_rules
from app.services.nlp.segmentation import slugify, split_into_clauses

MODELS_DIR = Path(__file__).parent / "models"

# Bar for the severity model to flag risk on its own, when no specific CUAD
# category matched. It's then the *only* signal, and it has no "not risky"
# class, so the bar is high and the report keeps these separate.
GENERAL_RISK_THRESHOLD = 0.6


class TrainedClauseAnalyzer(ClauseAnalyzer):
    def __init__(self) -> None:
        clause_path = MODELS_DIR / "clause_classifier.joblib"
        required = ["risk_classifier.joblib", "risk_transformer.onnx", "risk_ensemble.json"]
        if not clause_path.exists() or not all((MODELS_DIR / name).exists() for name in required):
            raise FileNotFoundError(
                "Trained model artifacts not found. Run the scripts in ml_training/ "
                "(see backend/README.md) to train them."
            )
        self._clause_pipeline = joblib.load(clause_path)
        self._tfidf_risk_model = joblib.load(MODELS_DIR / "risk_classifier.joblib")
        self._transformer_risk_model = OnnxRiskDetector(MODELS_DIR)
        ensemble = json.loads((MODELS_DIR / "risk_ensemble.json").read_text())
        self._risk_categories: list[str] = ensemble["categories"]
        self._transformer_weight: float = ensemble["transformer_weight"]
        self._risk_thresholds = np.array([ensemble["thresholds"][c] for c in self._risk_categories])
        self._severity_pipeline = self._load_optional("severity_classifier.joblib")

        # The LEDGAR "label" column is stored as integer class codes; recover
        # the human-readable clause-type names saved alongside the model.
        clause_meta = json.loads((MODELS_DIR / "clause_classifier_meta.json").read_text())
        self._clause_label_names: list[str] = clause_meta["labels"]

    @staticmethod
    def _load_optional(filename: str):
        path = MODELS_DIR / filename
        return joblib.load(path) if path.exists() else None

    def analyze(self, document_text: str) -> list[ClauseResult]:
        clauses = split_into_clauses(document_text)
        if not clauses:
            return []

        clause_types, clause_confidences = self._predict(
            self._clause_pipeline, clauses, label_names=self._clause_label_names
        )
        named_risks = self._named_risks(clauses)

        severity_labels: list[str | None] = [None] * len(clauses)
        severity_confidences: list[float | None] = [None] * len(clauses)
        if self._severity_pipeline is not None:
            severity_labels, severity_confidences = self._predict(self._severity_pipeline, clauses)

        results = []
        for i, text in enumerate(clauses):
            risks = self._combine_risk_signals(
                named_risks=named_risks[i],
                severity_label=severity_labels[i],
                severity_confidence=severity_confidences[i],
            )
            risks = apply_rules(text, risks)
            results.append(
                ClauseResult(
                    text=text,
                    clause_type=slugify(clause_types[i]),
                    confidence=clause_confidences[i],
                    risks=risks,
                )
            )
        return results

    def _named_risks(self, clauses: list[str]) -> list[list[tuple[str, float]]]:
        """(category, probability) for every category whose tuned threshold a clause clears."""
        tfidf = self._tfidf_risk_model
        scores = tfidf["vectorizer"].transform(clauses) @ tfidf["coef"].T + tfidf["intercept"]
        tfidf_probabilities = 1.0 / (1.0 + np.exp(-np.asarray(scores)))
        transformer_probabilities = self._transformer_risk_model.probabilities(clauses)

        weight = self._transformer_weight
        probabilities = weight * transformer_probabilities + (1 - weight) * tfidf_probabilities
        flagged = probabilities >= self._risk_thresholds
        return [
            sorted(
                ((self._risk_categories[j], round(float(probabilities[i, j]), 4)) for j in np.nonzero(row)[0]),
                key=lambda item: -item[1],
            )
            for i, row in enumerate(flagged)
        ]

    @staticmethod
    def _combine_risk_signals(
        *,
        named_risks: list[tuple[str, float]],
        severity_label: str | None,
        severity_confidence: float | None,
    ) -> list[RiskResult]:
        if named_risks:
            # Severity comes from the hand-curated, legally-informed
            # RISK_CATEGORY_SEVERITY mapping, not the general severity model --
            # e.g. "Uncapped Liability" is always HIGH by definition.
            return [
                RiskResult(
                    risk_type=slugify(category),
                    severity=RISK_CATEGORY_SEVERITY.get(category, RiskSeverity.MEDIUM),
                    confidence=confidence,
                    explanation=RISK_CATEGORY_EXPLANATIONS.get(
                        category, "This clause was flagged as a potential risk by the model."
                    ),
                )
                for category, confidence in named_risks
            ]

        # No specific CUAD category matched -- fall back to the general
        # severity model, which can still catch risky clauses (e.g. from
        # Indian contract patterns) that CUAD's US-centric taxonomy misses.
        if (
            severity_label in ("Medium", "High")
            and severity_confidence is not None
            and severity_confidence >= GENERAL_RISK_THRESHOLD
        ):
            return [
                RiskResult(
                    risk_type=GENERAL_RISK_TYPE,
                    severity=SEVERITY_LABEL_TO_ENUM[severity_label],
                    confidence=severity_confidence,
                    explanation=GENERAL_RISK_EXPLANATION,
                )
            ]

        return []

    @staticmethod
    def _predict(
        pipeline, texts: list[str], label_names: list[str] | None = None
    ) -> tuple[list[str], list[float]]:
        probabilities = pipeline.predict_proba(texts)
        classes = pipeline.classes_
        best_idx = probabilities.argmax(axis=1)
        if label_names is not None:
            labels = [label_names[classes[i]] for i in best_idx]
        else:
            labels = [classes[i] for i in best_idx]
        confidences = [round(float(probabilities[row, i]), 4) for row, i in enumerate(best_idx)]
        return labels, confidences
