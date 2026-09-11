# CivicAI

**An AI-Powered Intelligent Citizen Service Platform for Government Offices.**

CivicAI helps citizens get answers, submit documents and find schemes without
standing in queues, and helps government offices see where their service is slow.

> **Status: project foundation only.** The folder structure, configuration,
> database layer, authentication and API/UI skeletons work. The six AI modules
> are placeholders and will be implemented one at a time.

---

## Modules

| # | Module | What it will do |
|---|--------|-----------------|
| 1 | Regulation RAG Assistant | Answer questions about regulations from official documents |
| 2 | Document Verification | Read uploaded documents with OCR and validate them |
| 3 | Queue Wait-Time Prediction | Predict how long a citizen will wait at an office |
| 4 | Officer Productivity Dashboard | Show how applications are handled per officer |
| 5 | Proactive Eligibility Nudge | Tell citizens about schemes they qualify for |
| 6 | Citizen Feedback Sentiment | Classify citizen feedback to spot service problems |

---

## Technology stack

- **Backend:** FastAPI, Uvicorn
- **Frontend:** Streamlit
- **Database:** SQLite now, PostgreSQL later (SQLAlchemy in both cases)
- **Auth:** JWT (PyJWT) with bcrypt password hashing
- **Retrieval:** ChromaDB, sentence-transformers, cross-encoder reranker
- **Knowledge graph:** NetworkX
- **LLM:** Groq API
- **OCR:** Tesseract (pytesseract)
- **ML:** scikit-learn

---

## Folder structure

```
Civic-AI/
├── backend/                        FastAPI application
│   ├── main.py                     app entry point
│   ├── api/
│   │   ├── deps.py                 shared dependencies (DB session, current user)
│   │   └── v1/
│   │       ├── router.py           combines all route files
│   │       └── routes/             one file per module + auth, health
│   ├── core/
│   │   ├── config.py               settings loaded from .env
│   │   └── security.py             JWT and bcrypt helpers
│   ├── db/
│   │   ├── base.py                 SQLAlchemy declarative base
│   │   ├── session.py              engine and session factory
│   │   └── init_db.py              creates the tables
│   ├── models/                     database tables
│   ├── schemas/                    request / response models
│   └── services/                   business logic (one file per module)
├── ai_modules/                     AI and ML code, no FastAPI imports
│   ├── regulation_rag/             ├── queue_prediction/
│   ├── document_verification/      ├── officer_productivity/
│   ├── eligibility_nudge/          └── feedback_sentiment/
├── frontend/                       Streamlit application
│   ├── app.py                      Streamlit entry point
│   ├── pages/                      one page per module
│   └── utils/api_client.py         calls the backend API
├── data/                           SQLite file, uploads, ChromaDB store
├── tests/                          pytest tests
├── requirements.txt
├── .env.example
└── README.md
```

### Why it is split this way

- **Routes are thin.** They only read the request and return a response; the
  logic lives in `backend/services/`.
- **AI code is separate.** `ai_modules/` never imports FastAPI, so each model
  can be built and tested on its own.
- **Only `backend/db/session.py` knows the database.** Switching from SQLite to
  PostgreSQL is a one-line change in `.env`.

---

## Setup

### 1. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # Linux / macOS
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Create the .env file

```powershell
copy .env.example .env          # Windows
# cp .env.example .env          # Linux / macOS
```

Then open `.env` and set `JWT_SECRET_KEY`. `GROQ_API_KEY` is only needed once
Module 1 is implemented.

---

## Running the project

Run both commands **from the project root**, in two terminals.

### Backend (FastAPI)

```powershell
uvicorn backend.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs

### Frontend (Streamlit)

```powershell
streamlit run frontend/app.py
```

- UI: http://localhost:8501

---

## Authentication and roles

`User` is the single login identity. Every user has one role:

| Role | May do |
|------|--------|
| `citizen` | Citizen services (own appointments, documents, queries, feedback) |
| `officer` | Officer functionality, including the productivity dashboard |
| `administrator` | Everything an officer can do, plus scheme and account management |

Rules:

- Passwords are stored only as bcrypt hashes and never appear in any response.
- Logging in returns a JWT; send it as `Authorization: Bearer <token>`.
- Missing, invalid and expired tokens are rejected with `401`. A token whose
  user was deleted is also rejected.
- An inactive account cannot log in and cannot use a token (`403`).
- `POST /auth/register` always creates a **citizen**. Officer and administrator
  accounts are created by an administrator via `POST /auth/users`.

Because only an administrator can create an administrator, create the first one
from the command line:

```powershell
python -m backend.db.create_admin "Your Name" you@example.com
```

Routes declare their own requirement with the shared `require_role`
dependency from `backend/api/deps.py`:

```python
current_user: User = Depends(require_role(Role.OFFICER, Role.ADMINISTRATOR))
```

---

## API endpoints

| Method | Path | Who can use it |
|--------|------|----------------|
| GET | `/` | anyone |
| GET | `/api/v1/health` | anyone |
| POST | `/api/v1/auth/register` | anyone (creates a citizen) |
| POST | `/api/v1/auth/login` | anyone |
| GET | `/api/v1/auth/me` | any signed-in user |
| POST | `/api/v1/auth/users` | administrator |
| GET | `/api/v1/citizens/dashboard` | citizen |
| GET | `/api/v1/officers/dashboard` | officer, administrator |
| POST | `/api/v1/regulations` | administrator |
| GET | `/api/v1/regulations/status` | Module 1 status |
| GET | `/api/v1/documents/status` | anyone |
| POST | `/api/v1/documents/upload` | citizen |
| GET | `/api/v1/documents` | citizen |
| GET | `/api/v1/documents/{id}` | citizen (own documents) |
| POST | `/api/v1/documents/{id}/verify` | citizen (own documents) |
| GET | `/api/v1/officers/documents/review` | officer, administrator |
| POST | `/api/v1/officers/documents/{id}/approve` | officer, administrator |
| POST | `/api/v1/officers/documents/{id}/reject` | officer, administrator |
| GET | `/api/v1/queue/status` | Module 3 status |
| GET | `/api/v1/officers/status` | Module 4 status |
| GET | `/api/v1/eligibility/status` | Module 5 status |
| GET | `/api/v1/feedback/status` | Module 6 status |

---

## Module 1: Regulation RAG Assistant

Citizens ask a question in plain language and get an answer built **only** from
the official regulation documents you have ingested, with citations.

```
citizen question
  -> embed the question (sentence-transformers, all-MiniLM-L6-v2)
  -> search ChromaDB for candidate chunks (top_k)
  -> add knowledge graph facts (NetworkX)
  -> rerank the candidates (cross-encoder, ms-marco-MiniLM-L-6-v2)
  -> keep only chunks scoring above RAG_MIN_SCORE (rerank_top_k)
  -> ask Groq for an answer grounded in that evidence
  -> answer + citations
```

If no chunk clears the score threshold, **the LLM is never called** and the
assistant replies that the available regulations do not answer the question.
It does not guess.

### Adding regulation documents

Put `.txt` or `.md` files in `data/regulations/`. Nothing is downloaded from
the internet. An optional header lets answers cite the scheme and circular:

```
scheme_name: Income Certificate Scheme
department: Revenue
circular_reference: CIRC/2026/11
---
Section 1. Eligibility
...
```

Headings such as `Section 3`, `Clause 2.1` or `3.` are detected and attached to
every chunk, so a citation can name the exact clause. Without a header the file
name becomes the scheme name.

Then ingest them as an administrator:

```powershell
# once, to create an administrator
python -m backend.db.create_admin "Your Name" you@example.com
```

```
POST /api/v1/regulations/ingest      (administrator only)
```

Re-ingesting a file replaces its chunks instead of duplicating them, because
chunk IDs are derived from the document and chunk position.

### Asking a question

```
POST /api/v1/regulations/query       (any signed-in user)
{ "query": "Which documents do I need for an income certificate?" }
```

```json
{
  "answer": "Proof of identity, proof of residence and proof of income ...",
  "citations": [
    {
      "scheme_name": "Income Certificate Scheme",
      "circular_reference": "CIRC/2026/11",
      "section": "Section 3",
      "source": "income_certificate.txt",
      "regulation_id": 1
    }
  ],
  "insufficient_evidence": false,
  "evidence_count": 2
}
```

A citation field is `null` when the source document did not provide it; nothing
is invented. The question and answer are saved as a `CitizenQuery` for the
signed-in citizen, and the owner always comes from the JWT rather than the
request body.

Tuning lives in `.env`: `RAG_TOP_K`, `RAG_RERANK_TOP_K`, `RAG_MIN_SCORE`,
`RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `EMBEDDING_MODEL`, `RERANKER_MODEL`,
`GROQ_MODEL`. The embedding and reranker models download on first use and are
then loaded once per process, not once per request.

---

## Module 2: Document Verification

Citizens upload a PNG, JPG or PDF. CivicAI reads it with OCR, pulls out labelled
fields, and checks them against the rules of the relevant scheme. **No document
text is sent to Groq** — the decision is fully rule-based.

```
upload (PNG / JPG / PDF)
  -> validate type, size and file contents
  -> store under data/documents/ with a server-generated name
  -> OCR (Tesseract for images; PyMuPDF text or rendered pages for PDFs)
  -> extract labelled fields (name, income, certificate number, ...)
  -> match rules for the document type and its regulation
  -> verified / rejected with the exact reason / needs officer review
```

A document is only **verified** when OCR produced usable text, the regulation is
known, rules exist for its type, and every rule passed. OCR succeeding does not
mean the document is verified. If a safe decision cannot be made, the document
goes to officer review rather than being guessed.

| Status | Meaning |
|--------|---------|
| `ocr_status=completed`, `verification_status=verified` | Text was read and every rule passed |
| `ocr_status=completed`, `verification_status=rejected` | Text was read, a named rule failed |
| `ocr_status=failed` or too little text | `verification_status=needs_review` |
| Regulation unknown or no rules for the type | `verification_status=needs_review` |

### Citizen endpoints

```
POST /api/v1/documents/upload     (citizen, multipart: file, document_type, optional regulation_id)
GET  /api/v1/documents            (citizen)
GET  /api/v1/documents/{id}       (citizen, own documents only)
POST /api/v1/documents/{id}/verify  (citizen, re-run checks)
```

Ownership is `JWT → User.id → Citizen.user_id → GovernmentDocument.citizen_id`.
Another citizen's document is reported as **not found**, not as forbidden.

### Officer review

Officer login accounts are still recognised by `User.role`. The ERD `Officer`
row is not linked to `User` yet, so review actions record the reviewing
`User.id` next to the extracted fields rather than as a foreign key.

```
GET  /api/v1/officers/documents/review
POST /api/v1/officers/documents/{id}/approve
POST /api/v1/officers/documents/{id}/reject
```

Officers and administrators may use these. Citizens receive `403`.

Tesseract must be installed separately. On Windows, set `TESSERACT_CMD` in
`.env` to the full path of `tesseract.exe`. Upload size is `MAX_UPLOAD_SIZE_MB`
(default 10).

---

## Module 3: Queue Wait-Time Prediction

Phase 6A adds a **synthetic** historical dataset. Phase 6B trains and compares
models offline. Phase 6C serves live predictions from the selected **queue-v1**
MLP artifact. The Streamlit queue page is still a placeholder; use the API.

The CSV is simulated development data. It is **not** taken from a real
government office, contains **no PII**, and must not be quoted as evidence of
real waiting times. **The model was trained using synthetic development data.
Live predictions are estimates and have not been validated against real
government-office historical data.**

| | |
|--|--|
| File | `data/queue_prediction/synthetic_queue_data.csv` |
| Rows | 15,000 |
| Seed | 42 (re-running the generator produces the same file) |
| Target | `actual_wait_time` (minutes) |
| Features available at prediction time | `service_type`, `day_of_week`, `hour`, `queue_depth`, `historical_service_time` |
| Selected model | MLPRegressor (`mlp.joblib`), version `queue-v1` |

Six counter services are simulated, with Income Certificate the most common and
Welfare Scheme Application the least. Timestamps fall on weekdays between
08:30 and 17:30. Queue depth and waiting time tend to be higher in the morning
rush than over lunch. `historical_service_time` is the typical duration for
that service (known before the visit), not the duration of this visit, and it
is never computed from the target.

Regenerate the dataset with:

```powershell
python -m ai_modules.queue_prediction.dataset_generator
```

Retrain offline (not during API requests) with:

```powershell
python -m ai_modules.queue_prediction.model_training
```

### Live prediction (Phase 6C)

Flow: a citizen books a visit → the server counts **active CivicAI appointments**
for that service and calendar day → it chooses `historical_service_time` → the
**cached** queue-v1 pipeline predicts wait → `Appointment.predicted_wait_time`
and a `QueuePredictionRecord` are stored.

| | |
|--|--|
| Create | `POST /api/v1/queue/appointments` (citizen JWT) |
| Get / list | `GET /api/v1/queue/appointments`, `GET /api/v1/queue/appointments/{id}` |
| Predict | `GET /api/v1/queue/predict/{appointment_id}` |
| Status | `GET /api/v1/queue/status` |
| History | `GET /api/v1/queue/appointments/{id}/history` |
| Staff events | `POST .../start`, `POST .../complete`, `POST .../cancel` |

The client may send only `service_type` and `appointment_date`. `citizen_id`,
`queue_number`, `predicted_wait_time`, `actual_wait_time` and `model_version`
are server-controlled.

**Queue depth** is `COUNT` of appointments with status `scheduled` or
`in_service` for that service on that **office-local calendar day**. The
office timezone is `OFFICE_TIMEZONE` (default `UTC`, the rest of CivicAI's
convention). Appointment instants are still stored as UTC. `completed` and
`cancelled` are excluded. The synthetic CSV is never queried.

**Queue numbers** are `MAX(queue_number)+1` for that service and day, including
cancelled rows so numbers are not reused.

**Historical service time** uses the mean of
`(service_completed_at - service_started_at)` from completed CivicAI visits
when at least five such observations exist for that service. Otherwise the
configured Phase 6A per-service baseline is used. This fallback is a feature
default, not a fabricated live wait, and not the current visit's duration.

**Model cache:** `mlp.joblib` (preprocess + estimator) is loaded lazily once
per process via `load_selected_model()`. Requests do not reload the file.

**Prediction cache:** a timestamped per-appointment result is reused for
**60 seconds** while queue depth is unchanged. After 60 seconds, or when the
live queue changes, the next authorized request recomputes. There is no
background loop. The frontend may poll later; this phase does not.

**Actual wait** is `service_started_at - queue_joined_at` (minutes), stored on
`QueuePredictionRecord` when an officer starts service. It stays `NULL` while
waiting and is never copied from the prediction.

Citizens see only their own appointments (other ids return 404). Officers and
administrators may view predictions. Artifact paths are not exposed.

Appointments are weekday-only, matching the training data.

---

## Database

The schema follows the CivicAI ER diagram. ERD field names such as `CitizenID`
and `OCRStatus` become `citizen_id` and `ocr_status` in the models, which is the
normal Python naming style.

| Entity | Table | File |
|--------|-------|------|
| Citizen | `citizens` | `backend/models/citizen.py` |
| Officer | `officers` | `backend/models/officer.py` |
| Regulation | `regulations` | `backend/models/regulation.py` |
| Appointment | `appointments` | `backend/models/appointment.py` |
| GovernmentDocument | `government_documents` | `backend/models/government_document.py` |
| CitizenQuery | `citizen_queries` | `backend/models/citizen_query.py` |
| EligibilityCheck | `eligibility_checks` | `backend/models/eligibility_check.py` |
| Feedback | `feedback` | `backend/models/feedback.py` |
| QueuePredictionRecord | `queue_prediction_records` | `backend/models/queue_prediction_record.py` |

Relationships:

- **Citizen** has many appointments, documents, queries, eligibility checks and feedback
- **Officer** has many appointments
- **Regulation** has many documents, queries and eligibility checks
- **Appointment** has many eligibility checks, feedback and queue prediction records

The `users` table from Phase 1 still backs login and is separate from
`citizens` for now.

Tables are created automatically when the backend starts. To create them
manually:

```powershell
python -m backend.db.init_db
```

The SQLite file is written to `data/civicai.db`.

---

## Tests

```powershell
pytest
```

---

## Next steps

1. Module 1 - Regulation RAG Assistant
2. Module 2 - Document Verification
3. Module 3 - Queue Wait-Time Prediction
4. Module 4 - Officer Productivity Dashboard
5. Module 5 - Proactive Eligibility Nudge
6. Module 6 - Citizen Feedback Sentiment Analysis
