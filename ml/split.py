"""Date-grouped chronological split for ECO Household 1."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    train_dates: tuple[str, ...]
    validation_dates: tuple[str, ...]
    test_dates: tuple[str, ...]


def chronological_split(frame: pd.DataFrame) -> TemporalSplit:
    """Split sorted unique dates 60/20/20, keeping each full date together."""
    if "date" not in frame:
        raise ValueError("Dataset must contain a date column.")
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"]).dt.normalize()
    days = sorted(data["date"].drop_duplicates())
    if len(days) != 79:
        raise ValueError(f"Expected 79 clean dates from the inspected export, found {len(days)}.")
    train_end = round(.60 * len(days))
    validation_end = round(.80 * len(days))
    train_days, validation_days, test_days = days[:train_end], days[train_end:validation_end], days[validation_end:]
    if (len(train_days), len(validation_days), len(test_days)) != (47, 16, 16):
        raise AssertionError("The date split no longer matches the documented 47/16/16 allocation.")

    def select(partition_days: list[pd.Timestamp]) -> pd.DataFrame:
        return data.loc[data["date"].isin(partition_days)].sort_values(
            ["date", "interval_start_second"]
        ).reset_index(drop=True)

    train, validation, test = select(train_days), select(validation_days), select(test_days)
    expected = [
        (train_days[0], train_days[-1], "2012-07-15", "2012-12-06"),
        (validation_days[0], validation_days[-1], "2012-12-08", "2012-12-23"),
        (test_days[0], test_days[-1], "2012-12-24", "2013-01-09"),
    ]
    for start, end, expected_start, expected_end in expected:
        if start.strftime("%Y-%m-%d") != expected_start or end.strftime("%Y-%m-%d") != expected_end:
            raise ValueError("Dataset date coverage no longer matches the Phase 3A split recommendation.")
    return TemporalSplit(
        train, validation, test,
        tuple(day.strftime("%Y-%m-%d") for day in train_days),
        tuple(day.strftime("%Y-%m-%d") for day in validation_days),
        tuple(day.strftime("%Y-%m-%d") for day in test_days),
    )
