# Citizen Feedback Sentiment Analysis

Local, deterministic classification of citizen comments after a completed
appointment.

This module is **not** a transformer, LLM, or trained scikit-learn model. It
does **not** call Groq, OpenAI, or any other external API. Feedback text stays
on the CivicAI server.

## Sentiment method

File: `sentiment.py` — `analyze_sentiment(text)`

A fixed lexicon scores unigrams and a few multi-word phrases. Negators in the
three tokens before a lexicon hit flip the sign (`not helpful` is negative;
`not bad` is positive). Intensifiers in the two tokens before a hit multiply
the weight by 1.5.

Numeric score thresholds (fixed):

| Score | Label |
|-------|--------|
| `>= 0.8` | `positive` |
| `<= -0.8` | `negative` |
| otherwise | `neutral` |

The output is always exactly one of `positive`, `neutral`, `negative`.

## Urgency method

File: `urgency.py` — `analyze_urgency(text)`

Urgency is a separate phrase/token matcher. It is **not** copied from
sentiment. A complaint can be negative and still `low` urgency.

| Priority | Label | Examples of indicators |
|----------|--------|------------------------|
| 1 | `high` | immediate action, emergency, unsafe, threat, harassment, fraud, corruption, serious issue |
| 2 | `medium` | pending for weeks, no response, still waiting, ignored, repeated attempts |
| 3 | `low` | no explicit urgency language |

A negator before an indicator suppresses it (`this is not urgent` stays `low`).

The output is always exactly one of `low`, `medium`, `high`.

## Escalation

File: `analyzer.py` — `analyze_feedback(text)`

```
escalation_required = (sentiment == "negative") AND (urgency == "high")
```

Escalation is derived when feedback is read. The client cannot submit or
override it. Negative + medium/low does not escalate. Neutral or positive +
high urgency does not escalate.

## API

| Method | Path | Who |
|--------|------|-----|
| `POST` | `/api/v1/feedback` | citizen |
| `GET` | `/api/v1/feedback` | citizen (own); officer/admin (all) |
| `GET` | `/api/v1/feedback/{feedback_id}` | owner, or officer/admin |
| `GET` | `/api/v1/officers/feedback/flagged` | officer/admin; negative + high only |
| `GET` | `/api/v1/feedback/status` | anyone |

Request body for `POST`:

```json
{ "appointment_id": 123, "comments": "..." }
```

The client may not send `citizen_id`, `sentiment`, `urgency`, escalation, or
`date_submitted`. Comments are required, stripped of surrounding whitespace,
and rejected (not truncated) above 2000 characters.

## Ownership

A citizen may submit feedback only when:

1. The appointment exists.
2. It belongs to the authenticated citizen (`User.id` → `Citizen.user_id` →
   `Citizen.citizen_id` → `Appointment.citizen_id`). Email is not used.
3. `Appointment.status` is `completed`.
4. No feedback row already exists for that appointment.

Other citizens' appointment IDs return the same `404` as a missing id.
Officers cannot submit citizen feedback.

## Storage

Results are stored on the existing `feedback` table:

`feedback_id`, `citizen_id`, `appointment_id`, `sentiment`, `urgency`,
`comments`, `date_submitted`.

`service_type` is read from the linked `Appointment` when feedback is
returned. It is not duplicated onto `Feedback`.

## Limitations

- The lexicon will miss sarcasm, mixed-language comments, and unseen slang.
- Urgency only fires on explicit listed indicators, so some real emergencies
  that use other wording will stay `low` or `medium`.
- This is suitable for a student/office prototype, not a substitute for a
  moderated complaints process.
