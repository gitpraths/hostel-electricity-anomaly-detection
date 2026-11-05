# Processed ECO Household 1 data dictionary

The default output is an interval-level Parquet file containing the 79 matched
dates without any `-1` electricity sentinel samples. Each day produces 96
15-minute records by default. The source CSVs remain unchanged under the raw
input directories.

| Column | Type | Unit / values | Definition |
| --- | --- | --- | --- |
| `date` | date | Calendar date | Date parsed from the smart-meter filename and matched occupancy row. No timezone is attached. |
| `interval_start_second` | integer | seconds since day start | Zero-based start position of the interval. |
| `time_of_day` | string | `HH:MM:SS` | Wall-clock-style time label derived from the sample position; no UTC offset is implied. |
| `hour` | integer | 0–23 | Hour derived from `interval_start_second`. |
| `day_of_week` | integer | 0–6 | Python weekday numbering: Monday 0, Sunday 6. |
| `day_name` | string | Monday–Sunday | English weekday name. |
| `is_weekend` | boolean | true/false | True for Saturday or Sunday. |
| `powerallphases_mean_w` | float | W | Arithmetic mean of total real power samples in the interval. |
| `powerallphases_max_w` | float | W | Maximum total real power sample in the interval. |
| `powerallphases_min_w` | float | W | Minimum total real power sample in the interval. |
| `powerallphases_std_w` | float | W | Sample standard deviation (`ddof=1`) of total real power samples. |
| `energy_wh` | float | Wh | Sum of each one-second total power reading divided by 3,600. One sample is one second; this is energy, not mean power. |
| `occupancy_fraction` | float | 0.0–1.0 | Mean of the 0/1 occupancy labels across the interval; fraction of seconds labelled occupied. |
| `occupancy_state` | string | `unoccupied`, `occupied`, `mixed` | `unoccupied` if fraction is 0, `occupied` if 1, otherwise `mixed`. |
| `interval_seconds` | integer | seconds | Number of one-second source positions represented by this record (900 at the default). |
| `powerl1_mean_w` | float | W | Mean phase 1 real power. |
| `powerl2_mean_w` | float | W | Mean phase 2 real power. |
| `powerl3_mean_w` | float | W | Mean phase 3 real power. |

The source names for all 16 raw columns are preserved in
`data/preprocess_eco.py` and documented in `dataset-inspection.md`. Current,
voltage, and phase-angle channels are validated and read but are not emitted in
this initial feature set; they are not needed for the first household-load
baseline and can be added after feature utility is assessed.

The Parquet metadata JSON records source counts, selected/excluded dates,
sampling interval, energy formula, and explicit `null` timezone/UTC offset. It
does not store absolute source paths.
