"""Builds the clause-level dataset used to train and evaluate the risk model.

Each of the ~510 real CUAD contracts is cut into clauses with the same
segmenter the API uses, and every expert-labelled span (41 categories) is
mapped onto the clause(s) it overlaps. Splits are by *contract*, so a model is
never evaluated on a contract it saw during training:

    train / val : carved from CUAD's original training contracts
    test        : CUAD's original held-out contracts

Run after download_data.py:
    python ml_training/build_clause_dataset.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.nlp.segmentation import segment  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
OUTPUT = DATA_DIR / "cuad_clauses.parquet"
VAL_CONTRACTS = 60
SEED = 42
MIN_OVERLAP = 0.5


def load(files: list[str]) -> pd.DataFrame:
    frames = [pd.read_parquet(DATA_DIR / f, columns=["title", "context", "question", "answers"]) for f in files]
    return pd.concat(frames, ignore_index=True)


def clause_labels(segments, spans: list[tuple[str, int, int]]) -> list[set[str]]:
    labels = [set() for _ in segments]
    starts = np.array([s.start for s in segments])
    ends = np.array([s.end for s in segments])
    for category, span_start, span_end in spans:
        overlap = np.minimum(ends, span_end) - np.maximum(starts, span_start)
        needed = MIN_OVERLAP * np.minimum(ends - starts, span_end - span_start)
        for index in np.nonzero((overlap > 0) & (overlap >= needed))[0]:
            labels[index].add(category)
    return labels


def build(df: pd.DataFrame, split_of: dict[str, str]) -> pd.DataFrame:
    rows = []
    for title, group in df.groupby("title", sort=False):
        context = group["context"].iloc[0]
        spans = []
        for category, answers in zip(group["question"], group["answers"]):
            for text, start in zip(answers["text"], answers["answer_start"]):
                if context[start : start + len(text)] == text:
                    spans.append((category, int(start), int(start) + len(text)))
        segments = segment(context)
        for index, (piece, labels) in enumerate(zip(segments, clause_labels(segments, spans))):
            rows.append(
                {
                    "title": title,
                    "split": split_of[title],
                    "index": index,
                    "start": piece.start,
                    "text": piece.text,
                    "labels": sorted(labels),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    train = load(["cuad_train_0.parquet", "cuad_train_1.parquet"])
    test = load(["cuad_test.parquet"])

    rng = np.random.default_rng(SEED)
    train_titles = sorted(train["title"].unique())
    val_titles = set(rng.choice(train_titles, size=VAL_CONTRACTS, replace=False))
    split_of = {t: ("val" if t in val_titles else "train") for t in train_titles}
    split_of.update({t: "test" for t in test["title"].unique()})

    dataset = build(pd.concat([train, test], ignore_index=True), split_of)
    dataset.to_parquet(OUTPUT)

    print(f"{len(dataset):,} clauses from {dataset['title'].nunique()} contracts -> {OUTPUT}")
    print(dataset.groupby("split").agg(contracts=("title", "nunique"), clauses=("text", "size")).to_string())
    labelled = dataset["labels"].map(len).gt(0).mean()
    print(f"clauses carrying at least one CUAD label: {labelled:.1%}")


if __name__ == "__main__":
    main()
