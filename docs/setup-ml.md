# ML computer setup and commands

These instructions apply to Computer 2 (the ML laptop). They use the checked-in
Python entry points and the authorized processed ECO Parquet file. Do not place
raw data or model artifacts in Git.

## Environment

Install Python 3.11 or newer, then from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate                 # macOS/Linux
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Put `data/processed/eco_household_1_15min.parquet` at that path, or pass a
different location with `--data`. The repository ignores processed data and
model files. No complete ECO archive is required for these commands.

## Train

From the repository root:

```bash
python -m ml.train
```

The default artifact is `models/eco_household_1_iforest.joblib`; metadata is
written alongside it. Configure the run with `--contamination`,
`--n-estimators`, `--random-state`, `--max-samples`, branch threshold options,
and `--robust-z-threshold`. For example:

```bash
python -m ml.train --threshold-with-occupancy 0.61 --threshold-without-occupancy 0.64
```

Thresholds are finite anomaly-score cutoffs in `[0, 1]`. If a branch option is
omitted, that branch keeps its training-only Isolation Forest contamination
offset. The legacy `--threshold VALUE` remains available and deliberately
applies the same override to both branches; do not combine it with either
branch-specific option. Use `--model-output PATH` to change the artifact path.

The JSON sidecar records the schema version and ordered features, both selected
threshold values and derivation methods, the training-only fit scope, split
dates, estimator configuration, and dataset hash. Keep the `.joblib` and
`.metadata.json` files from the same training run.

## Evaluate

```bash
python -m ml.evaluate
```

This loads the saved model, scores validation and test partitions, and writes
`docs/model-evaluation.md`. It does not refit, tune thresholds on those
partitions, or use anomaly labels. Optional paths: `--data`, `--model`, and
`--report`.

## Load and score one interval

The Python API is:

```python
import pandas as pd
from ml.detector import AnomalyDetector

model = AnomalyDetector.load("models/eco_household_1_iforest.joblib")
one_interval = pd.read_parquet("data/processed/eco_household_1_15min.parquet")
one_interval = one_interval[
    (one_interval["date"].astype(str) == "2012-12-24")
    & (one_interval["time_of_day"] == "17:45:00")
]
print(model.predict(one_interval)[[
    "anomaly_score", "anomaly_threshold", "iforest_flag", "explanation"
]])
```

Or use the command line:

```bash
python -m ml.predict --date 2012-12-24 --time 17:45:00
```

To score another Parquet-compatible frame, ensure it contains the columns in
`docs/data-dictionary.md`, including date, time of day, second-of-day, hour,
three power summary fields, and occupancy fraction. A missing occupancy fraction
stays missing and invokes the no-occupancy model branch.

## Tests

With the actual processed file available:

```bash
python -m pytest -q
```

ML tests use real Parquet rows and the fixed chronological split. They may
create a temporary missing-occupancy copy of a real row solely to exercise the
unknown-occupancy inference path; it is not represented as an ECO observation.

## Artifact handoff

Feature schema `1.0.0` defines exact ordered input features for the occupancy
and no-occupancy estimators. Loading validates the schema version, names and
order, estimator fitted feature names, selected thresholds, training metadata,
and agreement with the JSON sidecar. Older or incompatible artifacts are
rejected; retrain them with the current code. The saved artifact is local and
Git-ignored. Transfer the joblib model and metadata together through an approved
private file transfer or controlled artifact store. Only Python environments
with compatible scikit-learn versions should load the artifact. MQTT deployment
is not part of this phase.
