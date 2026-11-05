"""Load a saved model and score one stored interval or all rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ml.detector import AnomalyDetector

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data/processed/eco_household_1_15min.parquet"
DEFAULT_MODEL = ROOT / "models/eco_household_1_iforest.joblib"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--date", help="Select date YYYY-MM-DD.")
    parser.add_argument("--time", help="Select interval start HH:MM:SS.")
    args = parser.parse_args()
    detector = AnomalyDetector.load(args.model)
    frame = pd.read_parquet(args.data)
    if args.date or args.time:
        if not (args.date and args.time):
            parser.error("--date and --time must be supplied together.")
        frame["date"] = pd.to_datetime(frame["date"])
        selected = frame.loc[
            (frame["date"].dt.strftime("%Y-%m-%d") == args.date)
            & (frame["time_of_day"] == args.time)
        ]
        if len(selected) != 1:
            parser.error(f"Expected one interval for {args.date} {args.time}; found {len(selected)}.")
        frame = selected
    scored = detector.predict(frame)
    columns = [
        "date", "time_of_day", "powerallphases_mean_w", "powerallphases_max_w",
        "powerallphases_std_w", "occupancy_fraction", "model_variant",
        "anomaly_score", "anomaly_threshold", "iforest_flag", "robust_score",
        "robust_flag", "explanation",
    ]
    for _, row in scored[columns].iterrows():
        print(json.dumps({key: (value.isoformat() if hasattr(value, "isoformat") else value)
                          for key, value in row.items()}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
