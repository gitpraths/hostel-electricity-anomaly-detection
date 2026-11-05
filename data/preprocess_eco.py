"""Validate and aggregate the supplied ECO Household 1 exports.

The original CSV exports remain untouched. Electricity is indexed by date and
second-of-day because the source files do not contain independent timestamps.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


SAMPLES_PER_DAY = 86_400
SMART_METER_COLUMNS = [
    "powerallphases",
    "powerl1",
    "powerl2",
    "powerl3",
    "currentneutral",
    "currentl1",
    "currentl2",
    "currentl3",
    "voltagel1",
    "voltagel2",
    "voltagel3",
    "phaseanglevoltagel21l",
    "phaseanglevoltagel31l",
    "phaseanglecurrentvoltagel1l",
    "phaseanglecurrentvoltagel2",
    "phaseanglecurrentvoltagel3",
]
PHASE_POWER_COLUMNS = ["powerl1", "powerl2", "powerl3"]
DEFAULT_INTERVAL_MINUTES = 15
DATE_FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")


class DataValidationError(ValueError):
    """Raised when an input file does not match the documented ECO format."""


@dataclass
class ValidationSummary:
    electricity_files: int = 0
    electricity_rows: int = 0
    electricity_bad_files: list[str] = field(default_factory=list)
    electricity_non_numeric_cells: int = 0
    electricity_non_finite_cells: int = 0
    electricity_wrong_width_rows: int = 0
    electricity_sentinel_samples: int = 0
    electricity_sentinel_dates: dict[str, int] = field(default_factory=dict)
    occupancy_files: int = 0
    occupancy_days: int = 0
    occupancy_invalid_labels: int = 0
    occupancy_bad_dates: list[str] = field(default_factory=list)
    occupancy_bad_width_rows: int = 0
    occupancy_duplicate_dates: list[str] = field(default_factory=list)
    electricity_days: int = 0
    matching_days: int = 0
    electricity_without_occupancy: list[str] = field(default_factory=list)
    occupancy_without_electricity: list[str] = field(default_factory=list)
    clean_days: list[str] = field(default_factory=list)
    excluded_sentinel_days: list[str] = field(default_factory=list)
    output_intervals: int = 0
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES


def parse_electricity_date(path: Path) -> date:
    """Extract the date from an ECO daily filename (YYYY-MM-DD.csv)."""
    match = DATE_FILENAME.fullmatch(path.name)
    if not match:
        raise DataValidationError(f"Unexpected electricity filename: {path.name}")
    try:
        return date.fromisoformat(match.group(1))
    except ValueError as exc:
        raise DataValidationError(f"Invalid date in filename: {path.name}") from exc


def validate_interval_minutes(interval_minutes: int) -> int:
    if interval_minutes < 1 or 1440 % interval_minutes != 0:
        raise ValueError("Interval minutes must be a positive divisor of 1440.")
    return interval_minutes


def _clean_occupancy_time_label(label: str) -> str:
    # Export headers contain literal single quotes around each HH:MM:SS value.
    return label.strip().strip("'").strip('"').strip()


def read_occupancy(occupancy_dir: Path, summary: ValidationSummary | None = None) -> dict[date, np.ndarray]:
    """Read the two occupancy CSVs as date -> int8 0/1 vector.

    Parsing one CSV row at a time avoids loading the full wide matrix as an
    object-heavy DataFrame.
    """
    occupancy_dir = Path(occupancy_dir)
    paths = sorted(occupancy_dir.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"No occupancy CSV files found in {occupancy_dir}")
    if summary is not None:
        summary.occupancy_files = len(paths)

    result: dict[date, np.ndarray] = {}
    for path in paths:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise DataValidationError(f"Empty occupancy file: {path.name}") from exc
            time_labels = [_clean_occupancy_time_label(value) for value in header[1:]]
            expected_labels = [
                f"{second // 3600:02d}:{(second // 60) % 60:02d}:{second % 60:02d}"
                for second in range(SAMPLES_PER_DAY)
            ]
            if len(header) != SAMPLES_PER_DAY + 1 or time_labels != expected_labels:
                raise DataValidationError(
                    f"{path.name}: expected a blank first header and ordered "
                    "00:00:00 through 23:59:59 time columns."
                )

            for line_number, row in enumerate(reader, start=2):
                if len(row) != SAMPLES_PER_DAY + 1:
                    if summary is not None:
                        summary.occupancy_bad_width_rows += 1
                    raise DataValidationError(
                        f"{path.name}:{line_number}: expected date plus "
                        f"{SAMPLES_PER_DAY} labels, got {len(row)} fields."
                    )
                raw_date = row[0].strip()
                try:
                    day = datetime.strptime(raw_date, "%d-%b-%Y").date()
                except ValueError as exc:
                    if summary is not None:
                        summary.occupancy_bad_dates.append(f"{path.name}:{line_number}:{raw_date}")
                    raise DataValidationError(
                        f"{path.name}:{line_number}: invalid occupancy date {raw_date!r}."
                    ) from exc
                if day in result:
                    if summary is not None:
                        summary.occupancy_duplicate_dates.append(day.isoformat())
                    raise DataValidationError(f"Duplicate occupancy date: {day.isoformat()}")
                labels = row[1:]
                invalid = [value for value in labels if value not in {"0", "1"}]
                if invalid:
                    if summary is not None:
                        summary.occupancy_invalid_labels += len(invalid)
                    raise DataValidationError(
                        f"{path.name}:{line_number}: occupancy labels must be 0 or 1; "
                        f"found {invalid[0]!r}."
                    )
                result[day] = np.fromiter((int(value) for value in labels), dtype=np.int8)

    if summary is not None:
        summary.occupancy_days = len(result)
    return result


def read_electricity_day(path: Path) -> tuple[date, pd.DataFrame, int]:
    """Read and validate one headerless 16-column electricity file.

    Returns date, numeric frame, and count of rows with a -1 sentinel in any
    column. It does not replace sentinel values.
    """
    day = parse_electricity_date(Path(path))
    try:
        frame = pd.read_csv(path, header=None, dtype="float64", skip_blank_lines=False)
    except (ValueError, pd.errors.ParserError) as exc:
        raise DataValidationError(f"{Path(path).name}: malformed or nonnumeric CSV data: {exc}") from exc
    if frame.shape != (SAMPLES_PER_DAY, len(SMART_METER_COLUMNS)):
        raise DataValidationError(
            f"{Path(path).name}: expected {SAMPLES_PER_DAY} rows and "
            f"{len(SMART_METER_COLUMNS)} columns, got {frame.shape[0]} rows and {frame.shape[1]} columns."
        )
    frame.columns = SMART_METER_COLUMNS
    values = frame.to_numpy(copy=False)
    if not np.isfinite(values).all():
        bad = int((~np.isfinite(values)).sum())
        raise DataValidationError(f"{Path(path).name}: found {bad} non-finite readings.")
    sentinel_rows = int(frame.eq(-1.0).any(axis=1).sum())
    return day, frame, sentinel_rows


def aggregate_day(
    day: date,
    electricity: pd.DataFrame,
    occupancy: np.ndarray,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
) -> pd.DataFrame:
    """Aggregate an aligned clean day into fixed intervals.

    Energy is sum(power in W * 1 second) / 3600, yielding Wh. Occupancy state
    is a categorical summary: occupied, unoccupied, or mixed within interval.
    """
    validate_interval_minutes(interval_minutes)
    interval_seconds = interval_minutes * 60
    if electricity.shape != (SAMPLES_PER_DAY, len(SMART_METER_COLUMNS)):
        raise DataValidationError("Electricity day must contain exactly 86,400 rows and 16 columns.")
    if len(occupancy) != SAMPLES_PER_DAY:
        raise DataValidationError("Occupancy day must contain exactly 86,400 labels.")
    if not np.isin(occupancy, [0, 1]).all():
        raise DataValidationError("Occupancy labels must be binary 0/1.")
    if (electricity.to_numpy(copy=False) == -1).any():
        raise DataValidationError(f"{day.isoformat()}: cannot aggregate a day containing -1 sentinels.")

    frame = electricity
    total_power = frame["powerallphases"].to_numpy(dtype=np.float64, copy=False)
    count = SAMPLES_PER_DAY // interval_seconds
    grouped_power = total_power.reshape(count, interval_seconds)
    grouped_occupancy = occupancy.reshape(count, interval_seconds)
    starts = np.arange(count, dtype=np.int64) * interval_seconds

    out: dict[str, object] = {
        "date": [day] * count,
        "interval_start_second": starts,
        "time_of_day": [
            f"{second // 3600:02d}:{(second // 60) % 60:02d}:{second % 60:02d}"
            for second in starts
        ],
        "hour": starts // 3600,
        "day_of_week": [day.weekday()] * count,
        "day_name": [day.strftime("%A")] * count,
        "is_weekend": [day.weekday() >= 5] * count,
        "powerallphases_mean_w": grouped_power.mean(axis=1),
        "powerallphases_max_w": grouped_power.max(axis=1),
        "powerallphases_min_w": grouped_power.min(axis=1),
        "powerallphases_std_w": grouped_power.std(axis=1, ddof=1),
        "energy_wh": grouped_power.sum(axis=1) / 3600.0,
        "occupancy_fraction": grouped_occupancy.mean(axis=1, dtype=np.float64),
        "occupancy_state": [
            "unoccupied" if value == 0 else "occupied" if value == 1 else "mixed"
            for value in grouped_occupancy.mean(axis=1, dtype=np.float64)
        ],
        "interval_seconds": [interval_seconds] * count,
    }
    for column in PHASE_POWER_COLUMNS:
        out[f"{column}_mean_w"] = frame[column].to_numpy(dtype=np.float64).reshape(
            count, interval_seconds
        ).mean(axis=1)
    return pd.DataFrame(out)


def _markdown_validation_report(summary: ValidationSummary, interval_minutes: int) -> str:
    clean = summary.clean_days
    excluded = summary.excluded_sentinel_days
    rows = [
        "# ECO Household 1 preprocessing validation report",
        "",
        "Generated from the original supplied CSV exports. The script did not modify raw files.",
        "",
        "## Summary",
        "",
        "| Check | Result |",
        "| --- | ---: |",
        f"| Electricity files discovered | {summary.electricity_files} |",
        f"| Electricity dates with valid 86,400 × 16 files | {summary.electricity_days} |",
        f"| Electricity input rows inspected | {summary.electricity_rows:,} |",
        f"| Occupancy files | {summary.occupancy_files} |",
        f"| Occupancy dates and 86,400-label rows | {summary.occupancy_days} |",
        f"| Dates present in both sources | {summary.matching_days} |",
        f"| Clean matched dates included | {len(clean)} |",
        f"| Matched dates excluded for -1 sentinel | {len(excluded)} |",
        f"| Output interval | {interval_minutes} minutes |",
        f"| Output interval records | {summary.output_intervals:,} |",
        "",
        "## Validation checks",
        "",
        f"- Non-finite electricity cells: {summary.electricity_non_finite_cells}.",
        f"- Nonnumeric electricity cells: {summary.electricity_non_numeric_cells}.",
        f"- Electricity rows with wrong width: {summary.electricity_wrong_width_rows}.",
        f"- Occupancy labels outside 0/1: {summary.occupancy_invalid_labels}.",
        f"- Occupancy rows with wrong width: {summary.occupancy_bad_width_rows}.",
        f"- Electricity samples with -1 sentinel (rows, any channel): {summary.electricity_sentinel_samples:,}.",
        f"- Electricity files rejected: {len(summary.electricity_bad_files)}.",
        "- Occupancy dates are aligned to electricity by filename date and sample position 0–86,399.",
        "- Electricity files have no independent timestamps; no timezone/UTC offset was assigned.",
        "",
        "### Sentinel dates",
        "",
        "| Date | Rows with sentinel | Action |",
        "| --- | ---: | --- |",
    ]
    if summary.electricity_sentinel_dates:
        for day, count in sorted(summary.electricity_sentinel_dates.items()):
            action = "excluded (matched date)" if day in excluded else "not emitted (no complete clean match)"
            rows.append(f"| {day} | {count:,} | {action} |")
    else:
        rows.append("| None | 0 | — |")
    rows.extend(["", "### Date matching", "", "#### Included dates", ""])
    rows.extend(f"- {day}" for day in clean)
    rows.extend(["", "#### Excluded matched dates", ""])
    rows.extend(f"- {day} ({summary.electricity_sentinel_dates.get(day, 0):,} sentinel rows)" for day in excluded)
    rows.extend(["", "#### Electricity dates without occupancy", ""])
    rows.extend(f"- {day}" for day in summary.electricity_without_occupancy)
    rows.extend(["", "#### Occupancy dates without electricity", ""])
    rows.extend(f"- {day}" for day in summary.occupancy_without_electricity)
    if not summary.occupancy_without_electricity:
        rows.append("- None")
    if summary.electricity_bad_files or summary.occupancy_bad_dates or summary.occupancy_duplicate_dates:
        rows.extend(["", "## Input issues", ""])
        rows.extend(f"- Electricity issue: {issue}" for issue in summary.electricity_bad_files)
        rows.extend(f"- Occupancy date issue: {issue}" for issue in summary.occupancy_bad_dates)
        rows.extend(f"- Duplicate occupancy date: {issue}" for issue in summary.occupancy_duplicate_dates)
    else:
        rows.extend(["", "## Input issues", "", "No structural, numeric, or occupancy-label issues were found."])
    rows.extend([
        "",
        "## Interpretation notes",
        "",
        "- `-1` is the dataset's missing-data sentinel and was never used as a measurement.",
        "- Sentinel-containing matching dates were excluded in full; no zeros were substituted and no interpolation was performed.",
        "- Energy is calculated as the sum of one-second watt readings divided by 3,600, reported in Wh.",
        "- Date and second-of-day are retained as wall-clock fields only. No timezone is inferred.",
        "",
    ])
    return "\n".join(rows)


def run_preprocessing(
    electricity_dir: Path,
    occupancy_dir: Path,
    output_dir: Path,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    report_path: Path | None = None,
) -> tuple[Path, Path, Path, ValidationSummary]:
    """Validate inputs, emit clean matched intervals to Parquet and metadata."""
    validate_interval_minutes(interval_minutes)
    electricity_dir = Path(electricity_dir)
    occupancy_dir = Path(occupancy_dir)
    output_dir = Path(output_dir)
    if not electricity_dir.is_dir():
        raise FileNotFoundError(f"Electricity input directory not found: {electricity_dir}")
    paths = sorted(electricity_dir.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"No electricity daily CSV files found in {electricity_dir}")

    summary = ValidationSummary(interval_minutes=interval_minutes)
    occupancy = read_occupancy(occupancy_dir, summary)
    occupancy_dates = set(occupancy)
    file_by_date: dict[date, Path] = {}
    for path in paths:
        day = parse_electricity_date(path)
        if day in file_by_date:
            raise DataValidationError(f"Duplicate electricity date: {day.isoformat()}")
        file_by_date[day] = path
    electricity_dates = set(file_by_date)
    summary.electricity_files = len(paths)
    summary.electricity_days = len(file_by_date)
    summary.matching_days = len(electricity_dates & occupancy_dates)
    summary.electricity_without_occupancy = [
        day.isoformat() for day in sorted(electricity_dates - occupancy_dates)
    ]
    summary.occupancy_without_electricity = [
        day.isoformat() for day in sorted(occupancy_dates - electricity_dates)
    ]

    interval_frames: list[pd.DataFrame] = []
    for day in sorted(electricity_dates):
        path = file_by_date[day]
        try:
            _, frame, sentinel_rows = read_electricity_day(path)
        except DataValidationError as exc:
            summary.electricity_bad_files.append(str(exc))
            continue
        summary.electricity_rows += len(frame)
        summary.electricity_sentinel_samples += sentinel_rows
        if sentinel_rows:
            summary.electricity_sentinel_dates[day.isoformat()] = sentinel_rows
        if day not in occupancy_dates:
            continue
        if sentinel_rows:
            summary.excluded_sentinel_days.append(day.isoformat())
            continue
        summary.clean_days.append(day.isoformat())
        interval_frames.append(aggregate_day(day, frame, occupancy[day], interval_minutes))

    result = pd.concat(interval_frames, ignore_index=True) if interval_frames else pd.DataFrame()
    summary.output_intervals = len(result)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / f"eco_household_1_{interval_minutes}min.parquet"
    metadata_path = output_dir / f"eco_household_1_{interval_minutes}min.metadata.json"
    try:
        result.to_parquet(parquet_path, index=False, engine="pyarrow")
    except ImportError as exc:
        raise RuntimeError("Parquet output requires pyarrow. Install requirements.txt first.") from exc

    metadata = {
        "dataset": "ETH Zurich ECO Household 1",
        "source_files": {
            "electricity_directory": electricity_dir.name,
            "electricity_file_count": summary.electricity_files,
            "occupancy_directory": occupancy_dir.name,
            "occupancy_file_count": summary.occupancy_files,
        },
        "sampling": {
            "source_hz": 1,
            "source_samples_per_day": SAMPLES_PER_DAY,
            "aggregation_interval_minutes": interval_minutes,
            "timestamp_semantics": "date plus second-of-day; source has no independent timestamp column",
            "timezone": None,
            "utc_offset": None,
        },
        "selection": {
            "electricity_dates": summary.electricity_days,
            "occupancy_dates": summary.occupancy_days,
            "matching_dates": summary.matching_days,
            "included_clean_dates": summary.clean_days,
            "excluded_sentinel_dates": summary.excluded_sentinel_days,
            "electricity_dates_without_occupancy": summary.electricity_without_occupancy,
            "occupancy_dates_without_electricity": summary.occupancy_without_electricity,
        },
        "quality": asdict(summary),
        "energy_unit": "Wh",
        "energy_formula": "sum(powerallphases_w for 1-second samples) / 3600",
        "columns": list(result.columns),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if report_path is None:
        report_path = output_dir / "dataset-validation-report.md"
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_markdown_validation_report(summary, interval_minutes), encoding="utf-8")
    return parquet_path, metadata_path, report_path, summary


def _default_path(env_name: str, relative_default: str, repo_root: Path) -> Path:
    configured = os.getenv(env_name)
    path = Path(configured).expanduser() if configured else Path(relative_default)
    return path if path.is_absolute() else (repo_root / path).resolve()


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--electricity-dir",
        type=Path,
        default=_default_path("ECO_ELECTRICITY_DIR", "database/01", repo_root),
        help="Directory of YYYY-MM-DD.csv smart-meter files (env: ECO_ELECTRICITY_DIR).",
    )
    parser.add_argument(
        "--occupancy-dir",
        type=Path,
        default=_default_path("ECO_OCCUPANCY_DIR", "database/01_occupancy_csv (1)", repo_root),
        help="Directory containing occupancy CSVs (env: ECO_OCCUPANCY_DIR).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_path("ECO_OUTPUT_DIR", "data/processed", repo_root),
        help="Processed Parquet/metadata output directory (env: ECO_OUTPUT_DIR).",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=int(os.getenv("ECO_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES)),
        help="Aggregation interval; must divide 1,440 (env: ECO_INTERVAL_MINUTES).",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=repo_root / "docs/dataset-validation-report.md",
        help="Markdown validation report path.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        parquet, metadata, report, summary = run_preprocessing(
            args.electricity_dir,
            args.occupancy_dir,
            args.output_dir,
            args.interval_minutes,
            args.report_path,
        )
    except (FileNotFoundError, DataValidationError, ValueError, RuntimeError) as exc:
        print(f"Preprocessing failed: {exc}", file=sys.stderr)
        return 2
    print(f"Parquet: {parquet}")
    print(f"Metadata: {metadata}")
    print(f"Validation report: {report}")
    print(
        f"Processed {len(summary.clean_days)} clean matched days into "
        f"{summary.output_intervals:,} {summary.interval_minutes}-minute intervals; "
        f"excluded {len(summary.excluded_sentinel_days)} matched sentinel days."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
