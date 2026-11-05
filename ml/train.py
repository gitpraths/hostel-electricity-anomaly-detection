"""Fit the ECO Household 1 Isolation Forest using training dates only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from ml.detector import AnomalyDetector
from ml.split import chronological_split

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data/processed/eco_household_1_15min.parquet"
DEFAULT_MODEL = ROOT / "models/eco_household_1_iforest.joblib"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--contamination", type=float, default=0.05)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-samples", default="auto")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Legacy shared cutoff applied to both occupancy branches; use branch-specific options instead.")
    parser.add_argument("--threshold-with-occupancy", type=float, default=None,
                        help="Optional anomaly_score cutoff for rows with known occupancy.")
    parser.add_argument("--threshold-without-occupancy", type=float, default=None,
                        help="Optional anomaly_score cutoff for rows with unknown occupancy.")
    parser.add_argument("--robust-z-threshold", type=float, default=3.5)
    args = parser.parse_args()

    raw = pd.read_parquet(args.data)
    split = chronological_split(raw)
    if len(split.train) != 4_512 or len(split.validation) != 1_536 or len(split.test) != 1_536:
        raise ValueError("Unexpected record counts for the documented temporal split.")
    max_samples: int | str = args.max_samples
    if max_samples != "auto":
        max_samples = int(max_samples)
    model = AnomalyDetector.fit(
        split.train,
        contamination=args.contamination,
        n_estimators=args.n_estimators,
        random_state=args.random_state,
        max_samples=max_samples,
        threshold=args.threshold,
        threshold_with_occupancy=args.threshold_with_occupancy,
        threshold_without_occupancy=args.threshold_without_occupancy,
        robust_z_threshold=args.robust_z_threshold,
    )
    model.metadata.update({
        "dataset": "ETH Zurich ECO Household 1",
        "dataset_file": args.data.name,
        "dataset_sha256": sha256_file(args.data),
        "dataset_rows": len(raw),
        "ground_truth_anomaly_labels_available": False,
        "temporal_split": {
            "method": "sorted unique dates, 60/20/20, whole dates kept together",
            "training": {"count_dates": len(split.train_dates), "start": split.train_dates[0],
                         "end": split.train_dates[-1], "record_count": len(split.train)},
            "validation": {"count_dates": len(split.validation_dates), "start": split.validation_dates[0],
                           "end": split.validation_dates[-1], "record_count": len(split.validation)},
            "test": {"count_dates": len(split.test_dates), "start": split.test_dates[0],
                     "end": split.test_dates[-1], "record_count": len(split.test)},
            "validation_and_test_used_for_fit_or_threshold_selection": False,
        },
        "limitations": [
            "No verified anomaly ground truth; flags are model suggestions, not confirmed faults.",
            "One household and two separated seasonal blocks; do not generalize to all hostels.",
            "Source time is date plus second-of-day with no timezone or UTC offset.",
        ],
    })
    model_path, metadata_path = model.save(args.model_output)
    print(f"Training dates: {len(split.train_dates)} ({split.train_dates[0]} to {split.train_dates[-1]})")
    print(f"Validation dates reserved: {len(split.validation_dates)} ({split.validation_dates[0]} to {split.validation_dates[-1]})")
    print(f"Test dates reserved: {len(split.test_dates)} ({split.test_dates[0]} to {split.test_dates[-1]})")
    print(f"Saved model: {model_path}")
    print(f"Saved metadata: {metadata_path}")
    print(f"Score direction: {model.metadata['score_direction']}")
    print(f"Selected train-derived thresholds: occupancy={model.threshold_with_occupancy:.6f}, no-occupancy={model.threshold_without_occupancy:.6f}")
    print(f"Feature schema: {model.metadata['feature_schema_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
