"""Tests for ECO preprocessing; synthetic unit inputs are explicitly test-only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.preprocess_eco import (
    DEFAULT_INTERVAL_MINUTES,
    SAMPLES_PER_DAY,
    SMART_METER_COLUMNS,
    DataValidationError,
    aggregate_day,
    parse_electricity_date,
    read_electricity_day,
    read_occupancy,
    validate_interval_minutes,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_ELECTRICITY = ROOT / "database/01"
REAL_OCCUPANCY = ROOT / "database/01_occupancy_csv (1)"


def synthetic_electricity(power: float = 3600.0) -> pd.DataFrame:
    """Return a deterministic synthetic frame for formula unit tests only."""
    values = np.zeros((SAMPLES_PER_DAY, len(SMART_METER_COLUMNS)), dtype=np.float64)
    values[:, 0] = power
    values[:, 1] = power / 2
    values[:, 2] = power / 3
    values[:, 3] = power / 6
    return pd.DataFrame(values, columns=SMART_METER_COLUMNS)


def test_column_assignment_uses_documented_names_on_real_file() -> None:
    path = REAL_ELECTRICITY / "2012-07-15.csv"
    if not path.exists():
        pytest.skip("Supplied ECO files are not present in this checkout.")
    day, frame, sentinels = read_electricity_day(path)
    assert day == date(2012, 7, 15)
    assert list(frame.columns) == SMART_METER_COLUMNS
    assert frame.shape == (SAMPLES_PER_DAY, 16)
    assert sentinels == 0


def test_occupancy_csv_parser_handles_quoted_headers_and_real_labels() -> None:
    if not REAL_OCCUPANCY.exists():
        pytest.skip("Supplied ECO occupancy files are not present in this checkout.")
    occupancy = read_occupancy(REAL_OCCUPANCY)
    assert len(occupancy) == 85
    assert occupancy[date(2012, 7, 15)].shape == (SAMPLES_PER_DAY,)
    assert set(np.unique(occupancy[date(2012, 7, 15)])) <= {0, 1}


def test_date_matching_against_real_files() -> None:
    if not REAL_ELECTRICITY.exists() or not REAL_OCCUPANCY.exists():
        pytest.skip("Supplied ECO files are not present in this checkout.")
    electricity = {parse_electricity_date(path) for path in REAL_ELECTRICITY.glob("*.csv")}
    occupancy = set(read_occupancy(REAL_OCCUPANCY))
    matching = electricity & occupancy
    assert len(electricity) == 245
    assert len(occupancy) == 85
    assert len(matching) == 85
    assert len(electricity - occupancy) == 160


def test_86400_row_validation_rejects_short_day(tmp_path: Path) -> None:
    path = tmp_path / "2012-07-15.csv"
    row = ",".join(["1"] * 16) + "\n"
    path.write_text(row * (SAMPLES_PER_DAY - 1), encoding="utf-8")
    with pytest.raises(DataValidationError, match="expected 86400 rows and 16 columns"):
        read_electricity_day(path)


def test_electricity_validation_rejects_extra_columns(tmp_path: Path) -> None:
    path = tmp_path / "2012-07-15.csv"
    row = ",".join(["1"] * 17) + "\n"
    path.write_text(row * SAMPLES_PER_DAY, encoding="utf-8")
    with pytest.raises(DataValidationError, match="expected 86400 rows and 16 columns"):
        read_electricity_day(path)


def test_electricity_validation_rejects_nonnumeric_field(tmp_path: Path) -> None:
    path = tmp_path / "2012-07-15.csv"
    valid = ",".join(["1"] * 16) + "\n"
    invalid = ",".join(["bad"] + ["1"] * 15) + "\n"
    path.write_text(valid * (SAMPLES_PER_DAY - 1) + invalid, encoding="utf-8")
    with pytest.raises(DataValidationError, match="nonnumeric CSV data"):
        read_electricity_day(path)


def test_sentinel_detection_on_real_matched_date() -> None:
    path = REAL_ELECTRICITY / "2012-07-21.csv"
    if not path.exists():
        pytest.skip("Supplied ECO files are not present in this checkout.")
    _, frame, sentinel_rows = read_electricity_day(path)
    assert sentinel_rows == 2299
    assert (frame == -1).any(axis=1).sum() == 2299


def test_energy_calculation_is_watt_seconds_converted_to_wh() -> None:
    # Synthetic formula fixture: 3,600 W for 900 seconds equals 900 Wh.
    frame = synthetic_electricity(3600.0)
    labels = np.zeros(SAMPLES_PER_DAY, dtype=np.int8)
    result = aggregate_day(date(2012, 7, 15), frame, labels)
    assert len(result) == 96
    assert result.loc[0, "powerallphases_mean_w"] == pytest.approx(3600.0)
    assert result.loc[0, "energy_wh"] == pytest.approx(900.0)


def test_15_minute_aggregation_and_occupancy_fraction() -> None:
    # Synthetic test-only alternating labels yield 0.5 occupancy in each slot.
    frame = synthetic_electricity()
    labels = np.tile(np.array([0, 1], dtype=np.int8), SAMPLES_PER_DAY // 2)
    result = aggregate_day(date(2012, 7, 15), frame, labels, DEFAULT_INTERVAL_MINUTES)
    assert len(result) == 96
    assert result.loc[0, "interval_start_second"] == 0
    assert result.loc[1, "interval_start_second"] == 900
    assert result.loc[0, "occupancy_fraction"] == pytest.approx(0.5)
    assert result.loc[0, "occupancy_state"] == "mixed"
    assert result.loc[0, "powerl1_mean_w"] == pytest.approx(1800.0)
    assert result.loc[0, "day_of_week"] == 6


def test_interval_must_divide_day_evenly() -> None:
    assert validate_interval_minutes(15) == 15
    with pytest.raises(ValueError, match="divisor of 1440"):
        validate_interval_minutes(17)
