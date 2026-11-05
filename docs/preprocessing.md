# Reproduce ECO Household 1 preprocessing

## Requirements

Use Python 3.11 or newer. Install the project stack, including pandas, NumPy,
PyArrow, and pytest:

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

## Run with the supplied checkout layout

From the repository root:

```bash
python -m data.preprocess_eco
```

Defaults use `database/01/` for electricity, `database/01_occupancy_csv (1)/`
for occupancy, `data/processed/` for Parquet and metadata, a 15-minute
aggregation interval, and `docs/dataset-validation-report.md` for the generated
validation report.

The same locations can be set with `ECO_ELECTRICITY_DIR`, `ECO_OCCUPANCY_DIR`,
`ECO_OUTPUT_DIR`, and `ECO_INTERVAL_MINUTES`. Command-line arguments override
these values:

```bash
python -m data.preprocess_eco \
  --electricity-dir ./database/01 \
  --occupancy-dir './database/01_occupancy_csv (1)' \
  --output-dir ./data/processed \
  --interval-minutes 15 \
  --report-path ./docs/dataset-validation-report.md
```

The interval must be a positive number of minutes that divides 1,440. Input
directories are read only. The default output is ignored by Git; the Markdown
validation report is intentionally written to `docs/` so the real-data audit is
reviewable.

## Outputs

- `data/processed/eco_household_1_15min.parquet`
- `data/processed/eco_household_1_15min.metadata.json`
- `docs/dataset-validation-report.md`

The pipeline matches by date and sample position. It validates 86,400 rows and
16 numeric columns per electricity day, validates 86,400 binary occupancy
labels per date, and rejects malformed inputs. Matched electricity days with
any `-1` are excluded in full. It never replaces missing values with zero or
interpolates them. No timezone or UTC offset is assigned.

## Tests

```bash
python -m pytest -q
```

Tests include actual ECO file checks when the supplied raw directories are
present. Deterministic synthetic arrays are used only in formula unit tests;
they are not emitted or described as ECO observations.
