"""Deterministic feature construction for the first Isolation Forest baseline."""

from __future__ import annotations

import numpy as np
import pandas as pd
from copy import deepcopy

POWER_FEATURES = [
    "powerallphases_mean_w",
    "powerallphases_max_w",
    "powerallphases_std_w",
]
TIME_FEATURES = ["time_of_day_sin", "time_of_day_cos"]
OCCUPANCY_FEATURES = ["occupancy_fraction"]
FEATURES_WITH_OCCUPANCY = POWER_FEATURES + OCCUPANCY_FEATURES + TIME_FEATURES
FEATURES_WITHOUT_OCCUPANCY = POWER_FEATURES + TIME_FEATURES
FEATURE_SCHEMA_VERSION = "1.0.0"
FEATURE_SCHEMA = {
    "version": FEATURE_SCHEMA_VERSION,
    "branches": {
        "with_occupancy": FEATURES_WITH_OCCUPANCY,
        "without_occupancy": FEATURES_WITHOUT_OCCUPANCY,
    },
}


def canonical_feature_schema() -> dict[str, object]:
    """Return an independent copy of the versioned schema contract."""
    return deepcopy(FEATURE_SCHEMA)


def add_cyclic_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add sine/cosine time features from the timezone-naive second-of-day."""
    if "interval_start_second" not in frame:
        raise ValueError("interval_start_second is required to derive cyclic time.")
    seconds = pd.to_numeric(frame["interval_start_second"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(seconds).all() or ((seconds < 0) | (seconds >= 86_400)).any():
        raise ValueError("interval_start_second must be finite and in [0, 86400).")
    radians = 2 * np.pi * seconds / 86_400
    result = frame.copy()
    result["time_of_day_sin"] = np.sin(radians)
    result["time_of_day_cos"] = np.cos(radians)
    return result


def make_features(
    frame: pd.DataFrame,
    include_occupancy: bool,
    feature_names: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Select model fields without filling unknown occupancy."""
    engineered = add_cyclic_time_features(frame)
    expected = FEATURES_WITH_OCCUPANCY if include_occupancy else FEATURES_WITHOUT_OCCUPANCY
    columns = list(expected if feature_names is None else feature_names)
    if columns != expected:
        raise ValueError(
            "Incompatible feature names or ordering for the selected branch; "
            f"expected {expected}, received {columns}. Retrain with the current feature schema."
        )
    missing = set(columns) - set(engineered.columns)
    if missing:
        raise ValueError(f"Missing model features: {sorted(missing)}")
    output = engineered.loc[:, columns].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(output.drop(columns=OCCUPANCY_FEATURES, errors="ignore").to_numpy()).all():
        raise ValueError("Electrical and cyclic-time model features must be finite.")
    if include_occupancy:
        known = output["occupancy_fraction"].dropna()
        if not known.between(0, 1).all():
            raise ValueError("Known occupancy_fraction values must be within [0, 1].")
    return output
