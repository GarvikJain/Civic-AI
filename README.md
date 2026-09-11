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

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Basic app information |
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/auth/register` | Create an account |
| POST | `/api/v1/auth/login` | Get a JWT |
| GET | `/api/v1/auth/me` | Current user (needs a token) |
| GET | `/api/v1/regulations/status` | Module 1 status |
| GET | `/api/v1/documents/status` | Module 2 status |
| GET | `/api/v1/queue/status` | Module 3 status |
| GET | `/api/v1/officers/status` | Module 4 status |
| GET | `/api/v1/eligibility/status` | Module 5 status |
| GET | `/api/v1/feedback/status` | Module 6 status |

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

Relationships:

- **Citizen** has many appointments, documents, queries, eligibility checks and feedback
- **Officer** has many appointments
- **Regulation** has many documents, queries and eligibility checks
- **Appointment** has many eligibility checks and feedback

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
