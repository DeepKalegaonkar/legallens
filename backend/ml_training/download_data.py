"""Downloads the raw parquet datasets used to train the clause/risk models.

Data sources (real, publicly available legal-contract corpora):
  - LEDGAR (via the LexGLUE benchmark mirror MAdAiLab/lex_glue_ledgar):
    ~70k real SEC contract provisions labeled with 100 clause-type categories.
  - CUAD (Contract Understanding Atticus Dataset, via chenghao/cuad_qa):
    ~500 real commercial contracts with expert-labeled clause spans across
    41 categories, used here to build the risk classifier.

Run once before train_clause_classifier.py / train_risk_classifier.py:
    python ml_training/download_data.py
"""

import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

FILES = {
    "ledgar_train.parquet": "https://huggingface.co/datasets/MAdAiLab/lex_glue_ledgar/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
    "ledgar_test.parquet": "https://huggingface.co/datasets/MAdAiLab/lex_glue_ledgar/resolve/refs%2Fconvert%2Fparquet/default/test/0000.parquet",
    "cuad_train_0.parquet": "https://huggingface.co/datasets/chenghao/cuad_qa/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
    "cuad_train_1.parquet": "https://huggingface.co/datasets/chenghao/cuad_qa/resolve/refs%2Fconvert%2Fparquet/default/train/0001.parquet",
    "cuad_test.parquet": "https://huggingface.co/datasets/chenghao/cuad_qa/resolve/refs%2Fconvert%2Fparquet/default/test/0000.parquet",
}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in FILES.items():
        destination = DATA_DIR / filename
        if destination.exists():
            print(f"skip (already downloaded): {filename}")
            continue
        print(f"downloading {filename} ...")
        urllib.request.urlretrieve(url, destination)
        print(f"  saved {destination.stat().st_size / 1_000_000:.1f} MB")


if __name__ == "__main__":
    main()
