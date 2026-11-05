"""Isolation Forest scoring wrapper with explicit unknown-occupancy handling."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest

from ml.features import (
    FEATURE_SCHEMA_VERSION,
    canonical_feature_schema,
    make_features,
)
from ml.robust_baseline import ContextualRobustBaseline


class AnomalyDetector:
    """Train two training-only IF variants and route missing occupancy safely."""

    def __init__(
        self,
        model_with_occupancy: IsolationForest,
        model_without_occupancy: IsolationForest,
        threshold_with_occupancy: float,
        threshold_without_occupancy: float,
        baseline: ContextualRobustBaseline,
        config: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.model_with_occupancy = model_with_occupancy
        self.model_without_occupancy = model_without_occupancy
        self.threshold_with_occupancy = float(threshold_with_occupancy)
        self.threshold_without_occupancy = float(threshold_without_occupancy)
        self.baseline = baseline
        self.config = config
        self.metadata = metadata or {}

    def _validate_artifact_contract(self) -> None:
        """Fail closed unless metadata, canonical schema, and fitted estimators agree."""
        schema = self.metadata.get("feature_schema")
        if not isinstance(schema, dict):
            raise ValueError(
                "Model artifact has no feature_schema metadata. Retrain it with the current ML code."
            )
        if schema.get("version") != FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported feature schema version {schema.get('version')!r}; "
                f"this runtime requires {FEATURE_SCHEMA_VERSION}. Retrain the model."
            )
        if self.metadata.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            raise ValueError("feature_schema_version is missing or inconsistent; retrain the model.")
        if not isinstance(self.metadata.get("configuration"), dict):
            raise ValueError("Model metadata has no training configuration; retrain the model.")
        training_info = self.metadata.get("training")
        if (
            not isinstance(training_info, dict)
            or not isinstance(training_info.get("record_count"), int)
            or training_info["record_count"] < 1
            or training_info.get("fit_data_scope") != "training_partition_only"
        ):
            raise ValueError("Model metadata has incomplete training information; retrain the model.")
        expected_schema = canonical_feature_schema()
        if schema != expected_schema:
            raise ValueError(
                "Declared feature names/order do not match the canonical feature schema "
                f"{FEATURE_SCHEMA_VERSION}. Retrain the model with current ml/features.py."
            )

        estimators = {
            "with_occupancy": self.model_with_occupancy,
            "without_occupancy": self.model_without_occupancy,
        }
        for branch, estimator in estimators.items():
            expected_names = expected_schema["branches"][branch]
            actual_names = getattr(estimator, "feature_names_in_", None)
            actual_count = getattr(estimator, "n_features_in_", None)
            if actual_names is None or list(actual_names) != expected_names or actual_count != len(expected_names):
                raise ValueError(
                    f"Fitted estimator schema mismatch for {branch}: expected ordered features "
                    f"{expected_names}, received {None if actual_names is None else list(actual_names)}. "
                    "Retrain the model."
                )

        thresholds = self.metadata.get("selected_thresholds")
        if not isinstance(thresholds, dict):
            raise ValueError("Model metadata has no selected_thresholds; retrain the model.")
        effective = {
            "with_occupancy": self.threshold_with_occupancy,
            "without_occupancy": self.threshold_without_occupancy,
        }
        for branch, expected_value in effective.items():
            item = thresholds.get(branch)
            if not isinstance(item, dict):
                raise ValueError(f"Missing selected threshold metadata for {branch}; retrain the model.")
            try:
                declared = float(item["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid selected threshold metadata for {branch}.") from exc
            if not math.isfinite(declared) or declared != expected_value:
                raise ValueError(
                    f"Selected threshold metadata for {branch} does not match the model artifact. "
                    "Keep the joblib and metadata files from the same training run."
                )
            derived_from_training = item.get("derived_from_training_data")
            expected_scope = "training_only" if derived_from_training else "user_supplied"
            if (
                not item.get("method")
                or item.get("fit_scope") != expected_scope
                or not isinstance(derived_from_training, bool)
            ):
                raise ValueError(f"Threshold derivation metadata for {branch} is incomplete.")

    @classmethod
    def fit(
        cls,
        training: pd.DataFrame,
        *,
        contamination: float = 0.05,
        n_estimators: int = 300,
        random_state: int = 42,
        max_samples: int | str = "auto",
        threshold: float | None = None,
        threshold_with_occupancy: float | None = None,
        threshold_without_occupancy: float | None = None,
        robust_z_threshold: float = 3.5,
    ) -> "AnomalyDetector":
        if not 0 < contamination <= 0.5:
            raise ValueError("contamination must be in (0, 0.5].")
        if n_estimators < 1:
            raise ValueError("n_estimators must be positive.")
        if training.empty:
            raise ValueError("Training data is empty.")
        if threshold is not None and (
            threshold_with_occupancy is not None or threshold_without_occupancy is not None
        ):
            raise ValueError("Use either the legacy shared threshold or separate branch thresholds, not both.")
        if threshold is not None:
            threshold_with_occupancy = threshold_without_occupancy = threshold

        def validate_threshold(value: float | None, branch: str) -> float | None:
            if value is None:
                return None
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{branch} threshold must be a finite number in [0, 1].") from exc
            if not math.isfinite(numeric) or not 0 <= numeric <= 1:
                raise ValueError(f"{branch} threshold must be a finite number in [0, 1].")
            return numeric

        threshold_with_occupancy = validate_threshold(threshold_with_occupancy, "Occupancy-model")
        threshold_without_occupancy = validate_threshold(threshold_without_occupancy, "No-occupancy-model")
        if training["occupancy_fraction"].isna().any():
            known_occupancy = training.loc[training["occupancy_fraction"].notna()]
        else:
            known_occupancy = training
        if known_occupancy.empty:
            raise ValueError("At least one training row must have known occupancy.")

        params = {
            "n_estimators": int(n_estimators),
            "contamination": float(contamination),
            "random_state": int(random_state),
            "max_samples": max_samples,
            "threshold_with_occupancy": threshold_with_occupancy,
            "threshold_without_occupancy": threshold_without_occupancy,
            "legacy_shared_threshold": threshold,
        }

        def fit_model(
            data: pd.DataFrame,
            with_occupancy: bool,
            override: float | None,
        ) -> tuple[IsolationForest, float, dict[str, float]]:
            features = make_features(data, include_occupancy=with_occupancy)
            if with_occupancy and features["occupancy_fraction"].isna().any():
                raise ValueError("Known-occupancy model received missing occupancy during fit.")
            estimator = IsolationForest(
                n_estimators=n_estimators,
                contamination=contamination,
                random_state=random_state,
                max_samples=max_samples,
                n_jobs=-1,
            )
            estimator.fit(features)
            # sklearn score_samples is lower for more unusual records. Negation
            # gives one documented convention: larger anomaly_score = stranger.
            training_scores = -estimator.score_samples(features)
            fitted_cutoff = float(-estimator.offset_)
            selected_cutoff = float(override) if override is not None else fitted_cutoff
            sensitivity = {
                f"{rate:.2f}": float(np.quantile(training_scores, 1 - rate))
                for rate in (0.01, 0.05, 0.10)
            }
            return estimator, selected_cutoff, sensitivity

        with_occ, threshold_occ, thresholds_occ = fit_model(known_occupancy, True, threshold_with_occupancy)
        without_occ, threshold_no_occ, thresholds_no_occ = fit_model(training, False, threshold_without_occupancy)
        baseline = ContextualRobustBaseline(robust_z_threshold).fit(training)
        dates = pd.to_datetime(training["date"]).dt.strftime("%Y-%m-%d") if "date" in training else None
        threshold_method_occ = (
            "explicit user override applied to occupancy branch"
            if threshold_with_occupancy is not None
            else "negative fitted IsolationForest offset (-offset_) from training scores"
        )
        threshold_method_no_occ = (
            "explicit user override applied to no-occupancy branch"
            if threshold_without_occupancy is not None
            else "negative fitted IsolationForest offset (-offset_) from training scores"
        )
        metadata = {
            "configuration": params,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_schema": canonical_feature_schema(),
            "selected_thresholds": {
                "with_occupancy": {
                    "value": threshold_occ,
                    "method": threshold_method_occ,
                    "fit_scope": "training_only" if threshold_with_occupancy is None else "user_supplied",
                    "derived_from_training_data": threshold_with_occupancy is None,
                },
                "without_occupancy": {
                    "value": threshold_no_occ,
                    "method": threshold_method_no_occ,
                    "fit_scope": "training_only" if threshold_without_occupancy is None else "user_supplied",
                    "derived_from_training_data": threshold_without_occupancy is None,
                },
            },
            "score_direction": "higher anomaly_score means more unusual; anomaly_score = -IsolationForest.score_samples",
            "threshold_source": "branch-specific explicit override or training-only IsolationForest contamination offset",
            "training_score_quantile_thresholds": {
                "with_occupancy": thresholds_occ,
                "without_occupancy": thresholds_no_occ,
            },
            "training": {
                "record_count": int(len(training)),
                "date_count": int(training["date"].nunique()) if "date" in training else None,
                "date_start": None if dates is None else dates.min(),
                "date_end": None if dates is None else dates.max(),
                "fit_data_scope": "training_partition_only",
            },
            "baseline": baseline.metadata(),
            "sklearn_version": sklearn.__version__,
        }
        return cls(
            with_occ, without_occ, threshold_occ, threshold_no_occ, baseline, params,
            metadata=metadata,
        )

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Score rows; missing occupancy routes to the no-occupancy estimator."""
        self._validate_artifact_contract()
        required = {
            "date", "time_of_day", "interval_start_second", "hour",
            "powerallphases_mean_w", "powerallphases_max_w", "powerallphases_std_w",
            "occupancy_fraction",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Prediction input missing columns: {sorted(missing)}")
        if frame.empty:
            return frame.assign(
                anomaly_score=pd.Series(dtype=float), anomaly_threshold=pd.Series(dtype=float),
                iforest_flag=pd.Series(dtype=bool), model_variant=pd.Series(dtype=str),
                robust_score=pd.Series(dtype=float), robust_flag=pd.Series(dtype=bool),
            )
        result = frame.copy()
        score = pd.Series(index=frame.index, dtype=float)
        threshold_values = pd.Series(index=frame.index, dtype=float)
        variant = pd.Series(index=frame.index, dtype=object)
        known = frame["occupancy_fraction"].notna()
        for mask, estimator, use_occupancy, cutoff, label in [
            (known, self.model_with_occupancy, True, self.threshold_with_occupancy, "with_occupancy"),
            (~known, self.model_without_occupancy, False, self.threshold_without_occupancy, "without_occupancy"),
        ]:
            if not mask.any():
                continue
            branch = "with_occupancy" if use_occupancy else "without_occupancy"
            features = make_features(
                frame.loc[mask],
                include_occupancy=use_occupancy,
                feature_names=self.metadata["feature_schema"]["branches"][branch],
            )
            score.loc[mask] = -estimator.score_samples(features)
            threshold_values.loc[mask] = cutoff
            variant.loc[mask] = label
        result["anomaly_score"] = score
        result["anomaly_threshold"] = threshold_values
        result["iforest_flag"] = score >= threshold_values
        result["model_variant"] = variant
        robust = self.baseline.score(frame)
        for column in robust:
            result[column] = robust[column]
        result["explanation"] = [
            self._explain(row) for _, row in result.iterrows()
        ]
        return result

    @staticmethod
    def _explain(row: pd.Series) -> str:
        occupancy = (
            "occupancy unknown; no-occupancy model used"
            if pd.isna(row["occupancy_fraction"])
            else f"occupancy fraction {row['occupancy_fraction']:.2f}"
        )
        return (
            f"mean {row['powerallphases_mean_w']:.1f} W; "
            f"15-min peak {row['powerallphases_max_w']:.1f} W; "
            f"within-interval std {row['powerallphases_std_w']:.1f} W; "
            f"{occupancy}; time {row['time_of_day']}. "
            "The score indicates unusualness, not its cause."
        )

    def save(self, path: Path) -> tuple[Path, Path]:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = path.with_suffix(".metadata.json")
        self.metadata["configuration"] = self.config
        self._validate_artifact_contract()
        joblib.dump(self, path)
        metadata_path.write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")
        return path, metadata_path

    @staticmethod
    def load(path: Path) -> "AnomalyDetector":
        path = Path(path)
        model = joblib.load(path)
        if not isinstance(model, AnomalyDetector):
            raise TypeError(f"Artifact at {path} is not an AnomalyDetector.")
        model._validate_artifact_contract()
        metadata_path = path.with_suffix(".metadata.json")
        if not metadata_path.exists():
            raise ValueError(
                f"Metadata sidecar not found at {metadata_path}. Keep the model and metadata from the same training run."
            )
        try:
            sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read model metadata sidecar {metadata_path}: {exc}") from exc
        if not isinstance(sidecar, dict):
            raise ValueError(f"Model metadata sidecar {metadata_path} must contain a JSON object.")
        for field in ("feature_schema_version", "feature_schema", "selected_thresholds", "configuration", "training"):
            if field not in sidecar or sidecar.get(field) != model.metadata.get(field):
                raise ValueError(
                    f"Model metadata sidecar field {field!r} does not match the joblib artifact. "
                    "Keep the model and metadata from the same training run."
                )
        return model
