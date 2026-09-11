# Synthetic queue dataset

This folder holds **simulated** historical queue observations for CivicAI
wait-time model development.

It is not real government-office data, it contains no personal information, and
it is not evidence of how any real office performs. Production use would
require real historical logs.

The file `synthetic_queue_data.csv` has 15,000 rows, generated with seed 42.

```powershell
python -m ai_modules.queue_prediction.dataset_generator
```
