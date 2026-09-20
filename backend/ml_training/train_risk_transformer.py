"""Fine-tunes Legal-BERT (small) as a multi-label risk detector on CUAD clauses.

Same task, data and contract-level splits as train_risk_classifier.py, but with
a pretrained legal language model instead of TF-IDF, so wording it hasn't seen
before (an Indian lease, say) still maps onto the risk categories it learned.

Every epoch uses all risky clauses plus a fresh random slice of the benign ones
(most clauses are benign, and CPU time is limited). That skews the raw scores,
so per-category thresholds are tuned on the validation contracts at their real
base rate. The best epoch by validation macro-F1 is kept and scored once on the
held-out test contracts.

Run after build_clause_dataset.py (needs the training extras: torch, transformers):
    python ml_training/train_risk_transformer.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk_eval import evaluate, summarize  # noqa: E402
from train_risk_classifier import CATEGORIES, labels_matrix, tune_thresholds  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

BASE_MODEL = "nlpaueb/legal-bert-small-uncased"
MAX_TOKENS = 160
EPOCHS = 4
BATCH_SIZE = 32
LEARNING_RATE = 6e-5
NEGATIVE_RATE = 0.35
SEED = 42


class RiskModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(BASE_MODEL)
        self.dropout = torch.nn.Dropout(0.1)
        self.head = torch.nn.Linear(self.encoder.config.hidden_size, len(CATEGORIES))

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        return self.head(self.dropout(pooled))


def collate(token_ids: list[list[int]], pad_id: int) -> tuple[torch.Tensor, torch.Tensor]:
    width = max(len(ids) for ids in token_ids)
    inputs = torch.full((len(token_ids), width), pad_id, dtype=torch.long)
    mask = torch.zeros((len(token_ids), width), dtype=torch.long)
    for row, ids in enumerate(token_ids):
        inputs[row, : len(ids)] = torch.tensor(ids)
        mask[row, : len(ids)] = 1
    return inputs, mask


def bucketed_batches(indices: np.ndarray, lengths: np.ndarray, rng: np.random.Generator) -> list[np.ndarray]:
    """Shuffle, then group similar-length clauses so batches waste little padding."""
    indices = rng.permutation(indices)
    pool = BATCH_SIZE * 50
    batches = []
    for start in range(0, len(indices), pool):
        chunk = indices[start : start + pool]
        chunk = chunk[np.argsort(lengths[chunk])]
        batches.extend(chunk[i : i + BATCH_SIZE] for i in range(0, len(chunk), BATCH_SIZE))
    order = rng.permutation(len(batches))
    return [batches[i] for i in order]


@torch.no_grad()
def predict(model: RiskModel, token_ids: list[list[int]], pad_id: int, batch_size: int = 128) -> np.ndarray:
    model.eval()
    order = np.argsort([len(ids) for ids in token_ids])
    output = np.zeros((len(token_ids), len(CATEGORIES)), dtype=np.float32)
    for start in range(0, len(order), batch_size):
        chosen = order[start : start + batch_size]
        inputs, mask = collate([token_ids[i] for i in chosen], pad_id)
        output[chosen] = torch.sigmoid(model(inputs, mask)).numpy()
    return output


def main() -> None:
    torch.manual_seed(SEED)
    torch.set_num_threads(14)
    rng = np.random.default_rng(SEED)
    ARTIFACTS_DIR.mkdir(exist_ok=True)

    dataset = pd.read_parquet(DATA_DIR / "cuad_clauses.parquet")
    splits = {name: dataset[dataset["split"] == name].reset_index(drop=True) for name in ("train", "val", "test")}
    labels = {name: labels_matrix(df) for name, df in splits.items()}

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    tokens = {
        name: tokenizer(df["text"].tolist(), truncation=True, max_length=MAX_TOKENS)["input_ids"]
        for name, df in splits.items()
    }
    pad_id = tokenizer.pad_token_id
    train_lengths = np.array([len(ids) for ids in tokens["train"]])

    risky = np.nonzero(labels["train"].any(axis=1))[0]
    benign = np.nonzero(~labels["train"].any(axis=1))[0]
    per_epoch = len(risky) + int(NEGATIVE_RATE * len(benign))
    print(f"train: {len(risky)} risky + {len(benign)} benign clauses; ~{per_epoch} per epoch", flush=True)

    positives = labels["train"][np.concatenate([risky, benign[: int(NEGATIVE_RATE * len(benign))]])].sum(axis=0)
    negatives = per_epoch - positives
    pos_weight = torch.tensor(np.clip(np.sqrt(negatives / np.maximum(positives, 1)), 1.0, 8.0), dtype=torch.float32)

    model = RiskModel()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=0.01)
    steps = EPOCHS * (per_epoch // BATCH_SIZE + 1)
    scheduler = get_linear_schedule_with_warmup(optimizer, int(0.06 * steps), steps)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    targets = torch.tensor(labels["train"], dtype=torch.float32)

    best_f1 = -1.0
    for epoch in range(1, EPOCHS + 1):
        started = time.time()
        model.train()
        chosen = np.concatenate([risky, rng.choice(benign, int(NEGATIVE_RATE * len(benign)), replace=False)])
        losses = []
        for step, batch in enumerate(bucketed_batches(chosen, train_lengths, rng), start=1):
            inputs, mask = collate([tokens["train"][i] for i in batch], pad_id)
            loss = loss_fn(model(inputs, mask), targets[batch])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            losses.append(loss.item())
            if step % 50 == 0:
                print(f"  epoch {epoch} step {step}: loss {np.mean(losses[-50:]):.4f} ({time.time() - started:.0f}s)", flush=True)

        val_probs = predict(model, tokens["val"], pad_id)
        thresholds = tune_thresholds(val_probs, labels["val"])
        val_result = evaluate(labels["val"], val_probs >= thresholds, CATEGORIES, splits["val"]["title"].nunique())
        print(f"epoch {epoch} done in {time.time() - started:.0f}s | {summarize('validation', val_result)}", flush=True)
        if val_result["macro_f1"] > best_f1:
            best_f1 = val_result["macro_f1"]
            torch.save(model.state_dict(), ARTIFACTS_DIR / "risk_transformer.pt")
            np.save(ARTIFACTS_DIR / "val_probs.npy", val_probs)
            print("  saved as best epoch", flush=True)

    model.load_state_dict(torch.load(ARTIFACTS_DIR / "risk_transformer.pt"))
    val_probs = np.load(ARTIFACTS_DIR / "val_probs.npy")
    thresholds = tune_thresholds(val_probs, labels["val"])
    test_probs = predict(model, tokens["test"], pad_id)
    np.save(ARTIFACTS_DIR / "test_probs.npy", test_probs)
    np.save(ARTIFACTS_DIR / "thresholds.npy", thresholds)
    result = evaluate(labels["test"], test_probs >= thresholds, CATEGORIES, splits["test"]["title"].nunique())
    print(summarize("TEST (held-out contracts)", result), flush=True)
    for category, scores in result["per_category"].items():
        print(
            f"  {category:34} P {scores['precision']:.2f} R {scores['recall']:.2f} F1 {scores['f1']:.2f}"
            f"  gold {scores['support']:4d} flagged {scores['flagged']:4d}"
        )


if __name__ == "__main__":
    main()
