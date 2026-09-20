"""CPU inference for the fine-tuned Legal-BERT risk detector.

The model is trained with PyTorch (see ml_training/train_risk_transformer.py)
but served from an int8 ONNX file, so the API needs only onnxruntime and
tokenizers.
"""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

BATCH_SIZE = 32


class OnnxRiskDetector:
    def __init__(self, models_dir: Path) -> None:
        meta = json.loads((models_dir / "risk_transformer_meta.json").read_text())
        self.categories: list[str] = meta["categories"]

        self._tokenizer = Tokenizer.from_file(str(models_dir / "risk_transformer_tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=meta["max_tokens"])
        self._tokenizer.enable_padding(pad_id=self._tokenizer.token_to_id("[PAD]"), pad_token="[PAD]")
        self._session = ort.InferenceSession(
            str(models_dir / "risk_transformer.onnx"), providers=["CPUExecutionProvider"]
        )

    def probabilities(self, texts: list[str]) -> np.ndarray:
        """Per-category probabilities, shape (len(texts), len(categories))."""
        output = np.zeros((len(texts), len(self.categories)), dtype=np.float32)
        # Similar-length clauses per batch keeps padding (and compute) small.
        order = np.argsort([len(text) for text in texts])
        for start in range(0, len(order), BATCH_SIZE):
            chosen = order[start : start + BATCH_SIZE]
            encodings = self._tokenizer.encode_batch([texts[i] for i in chosen])
            inputs = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            }
            logits = self._session.run(None, inputs)[0]
            output[chosen] = 1.0 / (1.0 + np.exp(-logits))
        return output
