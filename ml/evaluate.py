"""Evaluate trained anomaly scores on chronological validation and test dates."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ml.detector import AnomalyDetector
from ml.split import chronological_split

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data/processed/eco_household_1_15min.parquet"
DEFAULT_MODEL = ROOT / "models/eco_household_1_iforest.joblib"
DEFAULT_REPORT = ROOT / "docs/model-evaluation.md"


def _summary(name: str, scored: pd.DataFrame) -> dict[str, object]:
    return {
        "partition": name,
        "records": len(scored),
        "dates": scored["date"].nunique(),
        "flagged": int(scored["iforest_flag"].sum()),
        "flagged_pct": 100 * float(scored["iforest_flag"].mean()),
        "baseline_flagged": int(scored["robust_flag"].sum()),
        "baseline_flagged_pct": 100 * float(scored["robust_flag"].mean()),
        "score_median": float(scored["anomaly_score"].median()),
        "score_p95": float(scored["anomaly_score"].quantile(.95)),
        "score_p99": float(scored["anomaly_score"].quantile(.99)),
        "score_max": float(scored["anomaly_score"].max()),
        "baseline_overlap": int((scored["iforest_flag"] & scored["robust_flag"]).sum()),
    }


def _sensitivity(model: AnomalyDetector, scored: pd.DataFrame, variant: str) -> list[dict[str, object]]:
    thresholds = model.metadata["training_score_quantile_thresholds"][variant]
    rows = []
    for contamination, cutoff in thresholds.items():
        if variant == "with_occupancy":
            rows_mask = scored["model_variant"] == "with_occupancy"
        else:
            rows_mask = scored["model_variant"] == "without_occupancy"
        target = scored.loc[rows_mask]
        rows.append({
            "training_quantile": contamination,
            "threshold": float(cutoff),
            "scored_records": len(target),
            "flagged_pct": 100 * float((target["anomaly_score"] >= float(cutoff)).mean()) if len(target) else 0.0,
        })
    return rows


def _report(
    model: AnomalyDetector,
    split: object,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    validation_summary: dict[str, object],
    test_summary: dict[str, object],
) -> str:
    cfg = model.config
    lines = [
        "# Isolation Forest baseline evaluation — ECO Household 1", "",
        "## Scope and safeguards", "",
        "This is an unsupervised evaluation. ECO contains no verified anomaly labels for this task, so this report does not calculate classification accuracy, precision, recall, or F1. A flag means the model assigned an unusual score under this fitted baseline, not that a confirmed fault occurred.",
        "The Parquet file was read only. The model and all thresholds were fit from training dates only. Validation and test dates were scored after fitting and were not used to fit features, model parameters, baseline statistics, or the selected threshold.", "",
        "## Verified temporal split", "",
        "| Partition | Dates | Date count | Record count |",
        "| --- | --- | ---: | ---: |",
        f"| Train | {split.train_dates[0]}–{split.train_dates[-1]} | {len(split.train_dates)} | {len(split.train):,} |",
        f"| Validation | {split.validation_dates[0]}–{split.validation_dates[-1]} | {len(split.validation_dates)} | {len(split.validation):,} |",
        f"| Test holdout | {split.test_dates[0]}–{split.test_dates[-1]} | {len(split.test_dates)} | {len(split.test):,} |", "",
        "Whole dates remain together; no adjacent intervals were randomly split. The test block was not used for model or threshold selection.", "",
        "## Configuration and score meaning", "",
        f"- Estimator: Isolation Forest, {cfg['n_estimators']} trees, contamination {cfg['contamination']:.2%}, random seed {cfg['random_state']}, max_samples {cfg['max_samples']}.",
        f"- Score: anomaly_score = negative sklearn score_samples; **higher means more unusual**.",
        f"- Feature schema: version {model.metadata['feature_schema_version']}; both ordered branches are validated at load and inference.",
        f"- Selected threshold: occupancy model {model.threshold_with_occupancy:.6f}; no-occupancy model {model.threshold_without_occupancy:.6f}.",
        f"- Threshold derivation: occupancy={model.metadata['selected_thresholds']['with_occupancy']['method']}; no-occupancy={model.metadata['selected_thresholds']['without_occupancy']['method']}. Threshold provenance is recorded per branch in the model metadata.",
        f"- Baseline: hour-and-occupancy-conditioned median/MAD where training group size is adequate, falling back to hour then global training reference; fixed robust-z threshold {model.baseline.threshold:.2f}.", "",
        "No feature scaler is fitted. Time sine/cosine is a deterministic transform of second-of-day. Unknown occupancy routes to the separately trained model without occupancy; it is never changed to 0.", "",
        "## Feature set", "",
        "Occupancy-aware model: powerallphases_mean_w, powerallphases_max_w, powerallphases_std_w, occupancy_fraction, time_of_day_sin, time_of_day_cos. A separate no-occupancy estimator omits occupancy_fraction for rows where it is unknown.",
        "Energy is omitted because at a fixed 15-minute interval it duplicates mean power × 0.25 hours. Phase means are omitted because their sum reconstructs total mean power within rounding.", "",
        "## Unlabelled score and flag summaries", "",
        "| Period | Records | Dates | IF flagged | IF rate | Robust flagged | Robust rate | Score median | Score p95 | Score p99 | Score max | Both flagged |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in [validation_summary, test_summary]:
        lines.append(
            f"| {row['partition']} | {row['records']:,} | {row['dates']} | {row['flagged']:,} | "
            f"{row['flagged_pct']:.2f}% | {row['baseline_flagged']:,} | {row['baseline_flagged_pct']:.2f}% | "
            f"{row['score_median']:.5f} | {row['score_p95']:.5f} | {row['score_p99']:.5f} | "
            f"{row['score_max']:.5f} | {row['baseline_overlap']:,} |"
        )
    validation_rate = float(validation_summary["flagged_pct"])
    test_rate = float(test_summary["flagged_pct"])
    lines += ["", f"The IF flag rate changes by {abs(test_rate-validation_rate):.2f} percentage points from validation to test. This is a threshold/score stability description, not a performance metric against truth.", "",
        "### Sensitivity to training-derived contamination cutoffs", "",
        "The following thresholds are the 99th, 95th, and 90th percentiles of training scores (approximately 1%, 5%, and 10% training contamination). They are applied unchanged to validation and test scores; no evaluation-period threshold is selected.", "",
        "| Period | Training quantile target | Cutoff | IF flagged rate |",
        "| --- | ---: | ---: | ---: |"]
    for period, scored in [("Validation", validation), ("Test", test)]:
        for variant, label in [("with_occupancy", "known occupancy"), ("without_occupancy", "occupancy unknown")]:
            targets = scored.loc[scored["model_variant"] == label.replace("known occupancy", "with_occupancy").replace("occupancy unknown", "without_occupancy")]
            thresholds = model.metadata["training_score_quantile_thresholds"][variant]
            for quantile, cutoff in thresholds.items():
                rate = (
                    f"{100 * float((targets['anomaly_score'] >= float(cutoff)).mean()):.2f}%"
                    if len(targets) else "n/a (no rows)"
                )
                lines.append(f"| {period} ({label}) | {quantile} | {float(cutoff):.6f} | {rate} |")
    lines += ["", "The occupancy-unknown branch has no rows in this ECO Parquet, but is available for inference when occupancy is missing. Changing contamination changes the training-derived flag cutoff; score rankings are evaluated without labels.", "",
        "## High-scoring test intervals (review examples)", "",
        "These are the ten highest test anomaly scores, whether or not they cross the selected threshold. They are not known faults.", "",
        "| Date | Time | IF score | IF flag | Mean W | Peak W | Std W | Occupancy | Robust z | Context |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | --- |"]
    for _, row in test.nlargest(10, "anomaly_score").iterrows():
        occupancy = "unknown" if pd.isna(row.occupancy_fraction) else f"{row.occupancy_fraction:.2f}"
        lines.append(
            f"| {row.date.date()} | {row.time_of_day} | {row.anomaly_score:.6f} | "
            f"{'yes' if row.iforest_flag else 'no'} | {row.powerallphases_mean_w:.1f} | "
            f"{row.powerallphases_max_w:.1f} | {row.powerallphases_std_w:.1f} | {occupancy} | "
            f"{row.robust_score:.2f} | {row.robust_context} |"
        )
    lines += ["", "Each row can be described by its measured load, peak, variability, occupancy, and time. The IF score is not a feature attribution and cannot establish a cause. The robust baseline provides a more directly interpretable deviation from a training context median, but can miss multivariate combinations and depends on group support.", "",
        "## Baseline comparison and limitations", "",
        "The contextual median/MAD baseline is simple to explain and can compare a reading with a training reference for its hour and occupancy state. It detects unusual total mean power in either direction. It is less capable of detecting unusual combinations among mean, peak, and variability; sparse contexts fall back to broader groups.",
        "Isolation Forest uses multiple electricity and context features and can find unusual combinations, but its ranking and cutoff are not causal explanations. Neither method is supervised or validated against confirmed anomalies. Differences in flag rates or overlap do not show which method is correct.",
        "The dataset contains one household, 79 clean matched days, seasonal gaps, and only a winter validation/test block. Occupancy labels can be imperfect; live systems may not have occupancy. These results do not establish generalization to hostels or operational alert quality.", "",
        "## Reproduce", "",
        "From the repository root, activate the virtual environment, then run the evaluation command documented in docs/setup-ml.md. The report is regenerated from the Parquet and saved model.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    frame = pd.read_parquet(args.data)
    split = chronological_split(frame)
    model = AnomalyDetector.load(args.model)
    validation = model.predict(split.validation)
    test = model.predict(split.test)
    validation_summary = _summary("Validation", validation)
    test_summary = _summary("Test", test)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        _report(model, split, validation, test, validation_summary, test_summary),
        encoding="utf-8",
    )
    print(f"Validation: {validation_summary['flagged']}/{validation_summary['records']} IF flags ({validation_summary['flagged_pct']:.2f}%).")
    print(f"Test: {test_summary['flagged']}/{test_summary['records']} IF flags ({test_summary['flagged_pct']:.2f}%).")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
