"""Exports the fine-tuned risk transformer to a small ONNX file for the API.

Training needs PyTorch; serving doesn't. This converts the best checkpoint to
ONNX, quantises the weights to int8 (about a quarter of the size, CPU-friendly)
and writes a standalone tokenizer file. It checks the exported model and the
tokenizer against PyTorch / Hugging Face on real clauses. Thresholds and the
blend with the TF-IDF model are decided later, by build_risk_ensemble.py.

Run after train_risk_transformer.py:
    python ml_training/export_risk_transformer.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from tokenizers import Tokenizer
from transformers import AutoTokenizer

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from train_risk_classifier import CATEGORIES  # noqa: E402
from train_risk_transformer import BASE_MODEL, MAX_TOKENS, RiskModel  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
MODELS_DIR = Path(__file__).parent.parent / "app" / "services" / "nlp" / "models"


def export_onnx(model: RiskModel, destination: Path) -> None:
    model.eval()
    example = {
        "input_ids": torch.randint(1000, 5000, (2, 32)),
        "attention_mask": torch.ones(2, 32, dtype=torch.long),
    }
    torch.onnx.export(
        model,
        (example["input_ids"], example["attention_mask"]),
        str(destination),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "tokens"},
            "attention_mask": {0: "batch", 1: "tokens"},
            "logits": {0: "batch"},
        },
        opset_version=17,
        dynamo=False,
    )


def main() -> None:
    model = RiskModel()
    model.load_state_dict(torch.load(ARTIFACTS_DIR / "risk_transformer.pt"))

    full_path = ARTIFACTS_DIR / "risk_transformer_fp32.onnx"
    export_onnx(model, full_path)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    quantized_path = MODELS_DIR / "risk_transformer.onnx"
    quantize_dynamic(str(full_path), str(quantized_path), weight_type=QuantType.QInt8)
    print(f"fp32 {full_path.stat().st_size / 1e6:.1f} MB -> int8 {quantized_path.stat().st_size / 1e6:.1f} MB")

    hf_tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    hf_tokenizer.save_pretrained(ARTIFACTS_DIR / "tokenizer")
    tokenizer = Tokenizer.from_file(str(ARTIFACTS_DIR / "tokenizer" / "tokenizer.json"))
    tokenizer.save(str(MODELS_DIR / "risk_transformer_tokenizer.json"))

    # Parity check on real held-out clauses: ONNX int8 vs the PyTorch model.
    test = pd.read_parquet(DATA_DIR / "cuad_clauses.parquet").query("split == 'test'").reset_index(drop=True)
    sample = test.sample(400, random_state=1)
    encoded = hf_tokenizer(sample["text"].tolist(), truncation=True, max_length=MAX_TOKENS, padding=True, return_tensors="pt")
    with torch.no_grad():
        torch_probs = torch.sigmoid(model(encoded["input_ids"], encoded["attention_mask"])).numpy()
    session = ort.InferenceSession(str(quantized_path), providers=["CPUExecutionProvider"])
    logits = session.run(None, {"input_ids": encoded["input_ids"].numpy(), "attention_mask": encoded["attention_mask"].numpy()})[0]
    onnx_probs = 1 / (1 + np.exp(-logits))
    print(f"max |torch - onnx int8| probability difference on 400 clauses: {np.abs(torch_probs - onnx_probs).max():.3f}"
          f" (mean {np.abs(torch_probs - onnx_probs).mean():.4f})")

    # The standalone tokenizer must agree with the Hugging Face one, or scores drift.
    tokenizer.enable_truncation(max_length=MAX_TOKENS)
    for text in sample["text"].iloc[:100]:
        standalone = tokenizer.encode(text).ids
        reference = hf_tokenizer(text, truncation=True, max_length=MAX_TOKENS)["input_ids"]
        assert standalone == reference, f"tokenizer mismatch on: {text[:60]}"

    (MODELS_DIR / "risk_transformer_meta.json").write_text(
        json.dumps({"base_model": BASE_MODEL, "max_tokens": MAX_TOKENS, "categories": CATEGORIES}, indent=2)
    )
    print(f"saved ONNX model, tokenizer and metadata to {MODELS_DIR}")


if __name__ == "__main__":
    main()
