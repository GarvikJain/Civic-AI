# Officer Productivity Dashboard

Phase 9 is an **analytics layer**, not a new AI model.

It aggregates live SQLite/SQLAlchemy rows for officers and administrators.
It does **not** call Groq, retrain the queue model, or read the synthetic
queue training CSV.

## Access

JWT authentication plus existing RBAC: `officer` or `administrator`.
Citizens receive **403**. The Streamlit page also hides metrics after a 403;
backend enforcement is the real control.

## API

| Method | Path |
|--------|------|
| `GET` | `/api/v1/officers/dashboard/summary` |
| `GET` | `/api/v1/officers/dashboard` (same payload) |
| `GET` | `/api/v1/officers/feedback/flagged` (Phase 8, unfiltered flagged list) |
| `GET` | `/api/v1/officers/status` |

Query parameters:

- `period`: `today` | `last_7_days` | `last_30_days` | `all` (default `all`)
- `service_type`: one of the existing Appointment service types, optional

Time windows use the existing `OFFICE_TIMEZONE` calendar (default UTC).
Database timestamps stay UTC.

## Analytics and data sources

| Section | Source tables | Notes |
|---------|---------------|--------|
| Documents | `government_documents` | Counts by `verification_status`; top `rejection_reason` values. No OCR text, filenames, or paths. |
| Queue | `appointments`, `queue_prediction_records` | Predicted wait from appointments. Actual wait and absolute error only where `actual_wait_time` is not null. |
| Queries | `citizen_queries`, `regulations` | Grouped by scheme name. There is **no topic column**; no LLM topic classifier. |
| Feedback | `feedback` + `appointments.service_type` | Escalation remains `negative` AND `high`. Classification is not recomputed. |
| Flagged | same as Phase 8 | Negative + high urgency only. Comments and appointment/service ids; no `citizen_id`. |

`service_type` filters appointments, wait records, feedback, and documents
whose `document_type` equals that service name. Regulation queries are not
service-typed, so that section stays unfiltered when a service is selected.

## Privacy

The summary omits passwords, hashes, JWTs, stored filenames, filesystem
paths, and OCR payloads. Recent queries include a short preview, not the
stored RAG answer and not `citizen_id`.

## Limitations

- `Appointment.officer_id` is not set by the live queue API, so the dashboard
  cannot honestly report applications handled per officer row.
- Prediction error exists only after service start recorded an actual wait.
- Query "topics" are scheme frequencies, not NLP categories.
- Document `service_type` filtering uses `document_type`, which is the closest
  existing field; identity/residence proofs are not appointment services.
