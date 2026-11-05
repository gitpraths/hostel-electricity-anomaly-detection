"""Interpretable training-only robust baseline conditioned on hour/occupancy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

POWER = "powerallphases_mean_w"


def _state(value: object) -> str | None:
    if pd.isna(value):
        return None
    value = float(value)
    if value == 0:
        return "unoccupied"
    if value == 1:
        return "occupied"
    return "mixed"


@dataclass
class RobustContext:
    median: float
    scale: float
    count: int


class ContextualRobustBaseline:
    """Two-sided modified-z score using only training-day robust statistics.

    The reference is grouped by hour and occupancy state when enough training
    observations exist; otherwise it falls back to hour, then global training
    statistics. Unknown occupancy uses the hour-only branch and remains unknown.
    """

    def __init__(self, threshold: float = 3.5, min_group_size: int = 20) -> None:
        if threshold <= 0:
            raise ValueError("Robust baseline threshold must be positive.")
        self.threshold = float(threshold)
        self.min_group_size = int(min_group_size)
        self.hour_state: dict[tuple[int, str], RobustContext] = {}
        self.hour: dict[int, RobustContext] = {}
        self.global_context: RobustContext | None = None
        self.global_scale: float | None = None

    @staticmethod
    def _stats(values: pd.Series, fallback_scale: float = 1.0) -> RobustContext:
        values = values.astype(float)
        median = float(values.median())
        mad = float((values - median).abs().median())
        scale = 1.4826 * mad
        if not np.isfinite(scale) or scale < 1e-9:
            scale = fallback_scale
        return RobustContext(median, max(float(scale), 1.0), int(len(values)))

    def fit(self, training: pd.DataFrame) -> "ContextualRobustBaseline":
        required = {POWER, "hour", "occupancy_fraction"}
        if required - set(training.columns):
            raise ValueError(f"Training data missing robust baseline fields: {sorted(required-set(training.columns))}")
        if training.empty or training[POWER].isna().any():
            raise ValueError("Robust baseline requires nonempty training power data.")
        self.global_context = self._stats(training[POWER])
        self.global_scale = self.global_context.scale
        for hour, group in training.groupby("hour"):
            self.hour[int(hour)] = self._stats(group[POWER], self.global_scale)
            known = group.loc[group["occupancy_fraction"].notna()].copy()
            known["_state"] = known["occupancy_fraction"].map(_state)
            for state, subgroup in known.groupby("_state"):
                if len(subgroup) >= self.min_group_size:
                    self.hour_state[(int(hour), str(state))] = self._stats(
                        subgroup[POWER], self.hour[int(hour)].scale
                    )
        return self

    def score(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.global_context is None:
            raise RuntimeError("Fit the robust baseline on training data before scoring.")
        rows = []
        for _, row in frame.iterrows():
            hour = int(row["hour"])
            state = _state(row.get("occupancy_fraction", np.nan))
            context = self.hour_state.get((hour, state)) if state is not None else None
            context_name = f"hour={hour:02d},occupancy={state}" if context else None
            if context is None:
                context = self.hour.get(hour, self.global_context)
                context_name = f"hour={hour:02d}" if hour in self.hour else "global"
            score = abs(float(row[POWER]) - context.median) / context.scale
            rows.append({
                "robust_score": score,
                "robust_threshold": self.threshold,
                "robust_flag": score >= self.threshold,
                "robust_context": context_name,
                "robust_reference_median_w": context.median,
                "robust_reference_scale_w": context.scale,
            })
        return pd.DataFrame(rows, index=frame.index)

    def metadata(self) -> dict[str, object]:
        return {
            "method": "absolute modified-z score of total interval mean power",
            "threshold": self.threshold,
            "min_group_size": self.min_group_size,
            "groups_fit_from_training_only": {
                "hour_and_occupancy": len(self.hour_state),
                "hour": len(self.hour),
            },
            "occupancy_missing_behavior": "use hour-only training reference; never impute as unoccupied",
            "scale": "1.4826 * median absolute deviation; falls back to broader training scale when zero/unstable",
        }
