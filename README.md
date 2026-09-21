# LegalLens

[![CI](https://github.com/DeepKalegaonkar/legallens/actions/workflows/ci.yml/badge.svg)](https://github.com/DeepKalegaonkar/legallens/actions/workflows/ci.yml)

Upload a contract, get it cut into clauses, and see which ones are risky.
LegalLens classifies each clause, flags risks across 19 categories, and turns
the result into a findings-first report.

**Stack:** Angular 22 · FastAPI · PostgreSQL · scikit-learn + Legal-BERT (ONNX)

## What it does

- **Upload** a `.pdf`, `.docx` or `.txt` contract.
- **Segments** it into clauses (numbered headings, `(a)`/`(b)` sub-points, paragraphs).
- **Classifies** each clause into one of 100 types (trained on LEDGAR).
- **Detects risk** in 19 categories such as uncapped liability, termination for
  convenience, non-compete and anti-assignment (trained on CUAD), plus a rule layer
  for indemnities, auto-renewal, one-sided arbitrator appointment and whether a
  liability clause is capped or unlimited.
- **Reports** an overall verdict, a heat-strip of the document, key findings
  ranked by severity, and the full clause list.
- **Accounts:** JWT login with bcrypt passwords, plus optional two-step
  verification with any authenticator app (Microsoft Authenticator, Google
  Authenticator, ...), recovery codes and rate limiting.

## How well the risk model works

Scored on 102 real contracts the models never saw (contracts are held out
whole, never split between train and test):

| Risk detector | macro-F1 | any-risk precision / recall / F1 |
| --- | --- | --- |
| TF-IDF logistic regression | 0.52 | 0.67 / 0.62 / 0.64 |
| Legal-BERT alone | 0.54 | 0.66 / 0.63 / 0.64 |
| **Blend of both (shipped)** | **0.57** | **0.68 / 0.66 / 0.67** |

Precision is a lower bound because CUAD labels only some categories. The
indemnity, auto-renewal, arbitrator and liability-direction findings come from
deterministic rules layered on top of the models; they are unit-tested but not
scored on this benchmark. Risk is judged without knowing which party you are.
Details, the pipeline and the retraining steps are in [backend/README.md](backend/README.md).

## Human judgement has the final say

LegalLens reads every clause in seconds and shows you where to look. It can't
know your goals, your bargaining position or the law that applies to you, but a
person can. Treat its findings as a well-organised starting point: human
judgement, ideally a qualified lawyer's, should always have the final word on a
contract. It is a decision aid, not legal advice.

## Project layout

```
src/app/            Angular app (core services, guards, interceptors; features:
                    home, auth, dashboard, upload, document-detail, profile)
backend/app/        FastAPI app (api routes, models, schemas, crud, core, services/nlp)
backend/ml_training training and evaluation scripts for the models
backend/tests/      pytest suite
samples/            a fictional sample agreement (.txt and .pdf) to try
Dockerfile          frontend image (backend/Dockerfile is the API image)
docker-compose.yml  PostgreSQL, backend and frontend
.github/workflows/  CI: backend tests, frontend tests and build, Docker build
```

## Running it locally

### Option 1: everything in Docker

You only need Docker Desktop.

```bash
docker compose up --build
```

Then open http://localhost:4200 (API docs at http://localhost:8000/docs). Set
`JWT_SECRET_KEY` in your environment or a `.env` file first if this is anything
more than a local trial.

### Option 2: run the pieces yourself (development)

You need Node.js, Python 3 and Docker Desktop (for PostgreSQL). Developed on Node 24 and Python 3.14.

```bash
# 1. Database only (repo root)
docker compose up -d postgres

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
# edit .env: set JWT_SECRET_KEY to a long random string
uvicorn app.main:app --reload     # API on http://127.0.0.1:8000, docs at /docs

# 3. Frontend (repo root, new terminal)
npm install
ng serve                          # http://localhost:4200
```

Either way, register an account, then upload `samples/sample_services_agreement.pdf`.

The trained models are committed under `backend/app/services/nlp/models/`
(about 70 MB), so nothing needs training to run the app.

## Tests

```bash
cd backend && pytest        # API, segmentation, analyzer, rule and 2FA tests (temporary SQLite)
ng test                     # Angular unit tests
```

## Security notes

- The `postgres`/`postgres` credentials and the default JWT secret in `docker-compose.yml`
  are for local use only. Change them (and set `NG_ALLOWED_HOSTS` to your domain)
  before deploying anywhere.
- Failed two-step verification attempts are rate limited in memory, so the limit
  is per server process. Use a shared store such as Redis if you run several workers.
- Uploaded contracts are stored in your database. Do not upload confidential
  documents to a shared or public deployment without adding proper access controls.

## Not built yet

Alembic migrations (new columns are added on startup instead), background
processing for large files, and a hosted deployment.

## Data and models

Clause types and risks were trained on [LEDGAR](https://huggingface.co/datasets/coastalcph/lex_glue) and
[CUAD](https://www.atticusprojectai.org/cuad); the optional "general flag" model also uses a merged set that includes Indian contract clauses. The risk model fine-tunes
[`nlpaueb/legal-bert-small-uncased`](https://huggingface.co/nlpaueb/legal-bert-small-uncased).
Check each dataset's and model's license before reusing them commercially.
