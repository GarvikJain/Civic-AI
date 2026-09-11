# Queue wait-time data

This folder holds **simulated** historical queue observations for CivicAI
wait-time model development, plus evaluation reports from offline training.

It is not real government-office data, it contains no personal information, and
it is not evidence of how any real office performs. Production use would
require real historical logs.

The file `synthetic_queue_data.csv` has 15,000 rows, generated with seed 42.

```powershell
python -m ai_modules.queue_prediction.dataset_generator
python -m ai_modules.queue_prediction.model_training
```

- Live queue depth and queue numbers follow the office business day in
  `OFFICE_TIMEZONE` (default UTC). Appointment instants remain UTC.

## Live serving (Phase 6C)

- Selected model: **queue-v1** MLP (`mlp.joblib`), preprocessing included.
- Loaded once per process and cached. Not loaded on every API request.
- Predictions are reused for about **60 seconds** while queue depth is
  unchanged, then recomputed on the next authorized request.
- Historical service time uses completed CivicAI service history when
  available; otherwise the configured service baseline is used.
- Predicted wait is stored on the appointment and on
  `queue_prediction_records`. Actual wait stays NULL until an officer starts
  service (`service_started_at - queue_joined_at`).
- The model was trained using synthetic development data. Live predictions are
  estimates and have not been validated against real government-office
  historical data.
