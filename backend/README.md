# LegalLens Backend

FastAPI service providing auth, document upload/parsing, and clause
classification & risk detection.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
copy .env.example .env       # then edit JWT_SECRET_KEY, etc.
```

Start Postgres (from the repo root, requires Docker Desktop):

```bash
docker compose up -d
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

Tests (`pip install -r requirements-dev.txt`, then `pytest`) cover the clause
segmenter, check the trained analyzer against the sample agreement, and
exercise the document and two-step verification APIs against a throwaway
SQLite database (they never touch your real database).

## Two-step verification (authenticator app)

Users can turn on TOTP (RFC 6238) from the **Security** page. It works with
Microsoft Authenticator, Google Authenticator, Authy, 1Password and any other
standards-compliant app.

- `POST /auth/2fa/setup` returns a secret and a QR code (SVG data URI);
  `POST /auth/2fa/enable` confirms a first code and returns 8 one-time
  recovery codes (shown once, stored only as SHA-256 hashes);
  `POST /auth/2fa/disable` needs a current code or a recovery code.
- With 2FA on, `POST /auth/login` answers `{"mfa_required": true, "mfa_token": ...}`
  instead of an access token. The `mfa_token` is a 5-minute JWT that is refused
  as an access token; `POST /auth/login/2fa` trades it plus a code for the real
  token. Codes are single-use (a code can't be replayed) with ±1 step of drift.
- Wrong codes are limited to 5 per 5 minutes per account (HTTP 429). The limiter
  is in memory, so it is per process — move it to Redis if you run several workers.
- Swagger's "Authorize" button uses the password-only flow, so it can't sign in
  an account that has 2FA on.
- New `users` columns are added automatically on startup (`app/db/migrate.py`),
  so existing databases upgrade without Alembic.

## Backing up / restoring the database

The `postgres_data` Docker volume already persists data across container
restarts, but doesn't protect against the volume itself being deleted or
corrupted. For an actual point-in-time backup you can restore from later:

```bash
python backend/scripts/backup_db.py
```

Writes a timestamped `.sql` dump to `backend/backups/` (gitignored — it
contains real data) and keeps the 10 most recent dumps. Run this whenever
you want a snapshot; there's no automatic schedule set up.

To restore (⚠️ overwrites all current data in the database):

```bash
python backend/scripts/restore_db.py                  # restores the latest backup
python backend/scripts/restore_db.py path/to/dump.sql  # restores a specific one
```

Both scripts require the `postgres` container to be running (`docker compose up -d`).

## Sample contracts

`samples/` (repo root) has a fictional India-flavoured services agreement as a
`.pdf` and `.txt`, written to exercise the report: a mix of risky clauses
(exclusivity, non-compete, IP assignment, liquidated damages, termination for
convenience, ...) and routine boilerplate. Upload either file in the app.

## NLP: clause classification & risk detection

The NLP layer sits behind the `ClauseAnalyzer` interface
(`app/services/nlp/base.py`). `trained_model.py` is the default:

1. **Segmentation** (`segmentation.py`) cuts a document into clauses:
   numbered headings, `(a)`/`A.` sub-points (labelled with the parent number,
   e.g. "6(c)"), blank-line paragraphs and ALL-CAPS headings; headings are
   attached to the text after them, long clauses are split at sentence
   boundaries, and page markers / signature lines are dropped.
2. **Clause type** (`clause_classifier.joblib`): TF-IDF + linear model over 100
   clause types, trained on LEDGAR (real SEC contract provisions); ~85%
   accuracy on its held-out split. It's unreliable on short sub-clauses, so
   the UI only shows a type when the model is confident.
3. **Risk detection** — 19 risk categories from CUAD, multi-label (a clause can
   carry several). Two models are blended, `0.7 x Legal-BERT + 0.3 x TF-IDF`,
   with per-category thresholds tuned on validation contracts
   (`risk_ensemble.json`):
   - `risk_classifier.joblib`: logistic regression on TF-IDF word 1-2-grams.
   - `risk_transformer.onnx`: `nlpaueb/legal-bert-small-uncased` fine-tuned on
     the same clauses, exported to int8 ONNX (35 MB) so the API needs only
     `onnxruntime` and `tokenizers`, not PyTorch. A whole agreement is
     analysed in well under a second.
4. **General flag** (`severity_classifier.joblib`, optional): a Low/Medium/High
   classifier trained on a broader dataset that includes Indian contract
   clauses. It can flag clauses that match none of the 19 categories, but it
   has no "not risky" class and is noisy, so the report keeps these apart under
   "Also worth a look". It never overrides a named category's curated severity.

`placeholder.py` (regex/keyword) is a fallback: `api/deps.py` uses it if the
required model files are missing.

### How well it works

Scored on **102 CUAD contracts the models never saw** (whole contracts are held
out, never split across train and test). Precision is a lower bound, because
CUAD only labels 41 categories.

| Risk detector | macro-F1 | any-risk precision / recall / F1 | flags per contract |
| --- | --- | --- | --- |
| Earlier version (labelled spans, one label per clause) | 0.40 | 0.30 / 0.76 / 0.43 | 20.8 |
| TF-IDF, trained on whole clauses | 0.52 | 0.67 / 0.62 / 0.64 | 8.6 |
| Legal-BERT alone | 0.54 | 0.66 / 0.63 / 0.64 | 8.6 |
| **Blend (shipped)** | **0.57** | **0.68 / 0.66 / 0.67** | **8.7** |

The gap between the two models is small on CUAD but large on documents
unlike it: on an Indian commercial lease, TF-IDF finds one named risk and
Legal-BERT finds the assignment restriction and the terminate-anytime clause.
Known weak spots: no category for indemnities, auto-renewal or one-sided
arbitrator appointment; it can pick the wrong one of a matching pair of
clauses (a liability cap versus an uncapped liability); risk is judged without
knowing which party you are.

### Retraining / reproducing the models

```bash
cd backend
pip install -r ml_training/requirements.txt      # adds torch, transformers, onnx
python ml_training/download_data.py              # LEDGAR + CUAD parquet files (~320 MB)
python ml_training/build_clause_dataset.py       # cuts CUAD contracts into labelled clauses
python ml_training/train_clause_classifier.py    # clause type (LEDGAR)
python ml_training/train_risk_classifier.py      # TF-IDF risk detector
python ml_training/train_risk_transformer.py     # fine-tune Legal-BERT (~40 min on a 16-core CPU)
python ml_training/export_risk_transformer.py    # -> int8 ONNX + tokenizer, with parity checks
python ml_training/build_risk_ensemble.py        # picks blend weight + thresholds, scores held-out contracts
python ml_training/train_severity_classifier.py  # optional; needs data/external/final_merged_dataset.csv
```

Each script prints its held-out scores and writes its model and metadata to
`app/services/nlp/models/`. `final_merged_dataset.csv` is the output of an
earlier project's own data-prep pipeline, not a public download, so copy it to
`ml_training/data/external/` yourself before running the severity script.

### Swapping in a different model later

Add a new module in `app/services/nlp/` implementing
`ClauseAnalyzer.analyze(document_text: str) -> list[ClauseResult]`, then
point `_load_clause_analyzer()` in `app/api/deps.py` at it. No other code
(routes, database, frontend) needs to change.
