"""Baseline tests use actual supplied ECO Parquet records, not fabricated labels."""

from pathlib import Path
import copy
import json

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.detector import AnomalyDetector
from ml.features import FEATURE_SCHEMA_VERSION, make_features
from ml.split import chronological_split

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/eco_household_1_15min.parquet"


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    if not DATA.exists():
        pytest.skip("Actual processed ECO Parquet is not present.")
    return pd.read_parquet(DATA)


@pytest.fixture(scope="module")
def split(frame: pd.DataFrame):
    return chronological_split(frame)


def test_verified_date_grouped_split(split):
    assert (len(split.train_dates), len(split.validation_dates), len(split.test_dates)) == (47, 16, 16)
    assert (len(split.train), len(split.validation), len(split.test)) == (4512, 1536, 1536)
    assert (split.train_dates[0], split.train_dates[-1]) == ("2012-07-15", "2012-12-06")
    assert (split.validation_dates[0], split.validation_dates[-1]) == ("2012-12-08", "2012-12-23")
    assert (split.test_dates[0], split.test_dates[-1]) == ("2012-12-24", "2013-01-09")
    assert set(split.train.date).isdisjoint(split.validation.date)
    assert set(split.validation.date).isdisjoint(split.test.date)


def test_feature_selection_and_cyclic_encoding(frame):
    features = make_features(frame.iloc[[0]], include_occupancy=True)
    assert features.columns.tolist() == [
        "powerallphases_mean_w", "powerallphases_max_w", "powerallphases_std_w",
        "occupancy_fraction", "time_of_day_sin", "time_of_day_cos",
    ]
    assert np.isclose(features.loc[features.index[0], "time_of_day_sin"], 0.0, atol=1e-12)
    assert np.isclose(features.loc[features.index[0], "time_of_day_cos"], 1.0, atol=1e-12)


def test_feature_builder_rejects_wrong_names_or_order(frame):
    with pytest.raises(ValueError, match="names or ordering"):
        make_features(frame.iloc[[0]], True, feature_names=[
            "powerallphases_max_w", "powerallphases_mean_w", "powerallphases_std_w",
            "occupancy_fraction", "time_of_day_sin", "time_of_day_cos",
        ])


@pytest.fixture(scope="module")
def detector(split):
    return AnomalyDetector.fit(
        split.train, n_estimators=50, random_state=7, contamination=0.05
    )


def test_score_direction_threshold_and_explanation(detector, split):
    prediction = detector.predict(split.validation.iloc[:12])
    assert (prediction.anomaly_score >= 0).all()
    assert (prediction.iforest_flag == (prediction.anomaly_score >= prediction.anomaly_threshold)).all()
    assert prediction.explanation.str.contains("time").all()
    assert prediction.model_variant.eq("with_occupancy").all()


def test_missing_occupancy_uses_separate_model_without_imputation(detector, split):
    row = split.test.iloc[[0]].copy()
    row.loc[row.index[0], "occupancy_fraction"] = np.nan
    prediction = detector.predict(row)
    assert prediction.occupancy_fraction.isna().all()
    assert prediction.model_variant.eq("without_occupancy").all()
    assert prediction.explanation.str.contains("occupancy unknown").all()


def test_model_save_load_round_trip(detector, split, tmp_path):
    path = tmp_path / "baseline.joblib"
    detector.save(path)
    loaded = AnomalyDetector.load(path)
    before = detector.predict(split.test.iloc[:5]).anomaly_score.to_numpy()
    after = loaded.predict(split.test.iloc[:5]).anomaly_score.to_numpy()
    np.testing.assert_allclose(before, after)
    assert path.with_suffix(".metadata.json").exists()
    assert loaded.metadata["feature_schema_version"] == FEATURE_SCHEMA_VERSION


def _write_artifact_pair(detector, path: Path, mutate):
    artifact = copy.deepcopy(detector)
    mutate(artifact)
    joblib.dump(artifact, path)
    path.with_suffix(".metadata.json").write_text(
        json.dumps(artifact.metadata, indent=2), encoding="utf-8"
    )


def test_load_rejects_incompatible_schema_version(detector, tmp_path):
    path = tmp_path / "bad-version.joblib"

    def mutate(model):
        model.metadata["feature_schema_version"] = "99.0.0"
        model.metadata["feature_schema"]["version"] = "99.0.0"

    _write_artifact_pair(detector, path, mutate)
    with pytest.raises(ValueError, match="Unsupported feature schema version"):
        AnomalyDetector.load(path)


@pytest.mark.parametrize("change", ["name", "order"])
def test_load_rejects_incompatible_feature_declaration(detector, tmp_path, change):
    path = tmp_path / f"bad-feature-{change}.joblib"

    def mutate(model):
        names = model.metadata["feature_schema"]["branches"]["with_occupancy"]
        if change == "name":
            names[0] = "unrecognized_power_feature"
        else:
            names[0], names[1] = names[1], names[0]

    _write_artifact_pair(detector, path, mutate)
    with pytest.raises(ValueError, match="Declared feature names/order"):
        AnomalyDetector.load(path)


def test_load_rejects_declared_schema_that_disagrees_with_estimator(detector, tmp_path):
    path = tmp_path / "estimator-mismatch.joblib"

    def mutate(model):
        model.model_with_occupancy.feature_names_in_ = model.model_with_occupancy.feature_names_in_[::-1]

    _write_artifact_pair(detector, path, mutate)
    with pytest.raises(ValueError, match="Fitted estimator schema mismatch"):
        AnomalyDetector.load(path)


def test_branch_threshold_overrides_round_trip_and_prediction(detector, split, tmp_path):
    overridden = AnomalyDetector.fit(
        split.train,
        n_estimators=30,
        random_state=17,
        threshold_with_occupancy=0.71,
        threshold_without_occupancy=0.63,
    )
    path = tmp_path / "thresholds.joblib"
    overridden.save(path)
    loaded = AnomalyDetector.load(path)
    metadata = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert loaded.threshold_with_occupancy == 0.71
    assert loaded.threshold_without_occupancy == 0.63
    assert metadata["selected_thresholds"]["with_occupancy"]["value"] == 0.71
    assert metadata["selected_thresholds"]["without_occupancy"]["value"] == 0.63
    assert metadata["selected_thresholds"]["with_occupancy"]["fit_scope"] == "user_supplied"
    assert metadata["selected_thresholds"]["with_occupancy"]["derived_from_training_data"] is False
    assert metadata["feature_schema_version"] == FEATURE_SCHEMA_VERSION

    known = loaded.predict(split.validation.iloc[[0]])
    unknown_row = split.validation.iloc[[0]].copy()
    unknown_row.loc[unknown_row.index[0], "occupancy_fraction"] = np.nan
    unknown = loaded.predict(unknown_row)
    assert known.anomaly_threshold.iloc[0] == 0.71
    assert unknown.anomaly_threshold.iloc[0] == 0.63
    assert known.model_variant.iloc[0] == "with_occupancy"
    assert unknown.model_variant.iloc[0] == "without_occupancy"


def test_legacy_shared_threshold_is_deliberately_applied_to_both(detector, split):
    shared = AnomalyDetector.fit(split.train, n_estimators=20, threshold=0.58)
    assert shared.threshold_with_occupancy == shared.threshold_without_occupancy == 0.58
    with pytest.raises(ValueError, match="either the legacy shared threshold"):
        AnomalyDetector.fit(
            split.train, n_estimators=10, threshold=0.58, threshold_with_occupancy=0.60
        )


def test_default_threshold_metadata_confirms_training_only(detector):
    for item in detector.metadata["selected_thresholds"].values():
        assert item["fit_scope"] == "training_only"
        assert item["derived_from_training_data"] is True


@pytest.mark.parametrize("value", ["not-a-number", float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_threshold_overrides_are_rejected(split, value):
    with pytest.raises(ValueError, match=r"finite number in \[0, 1\]"):
        AnomalyDetector.fit(split.train, n_estimators=5, threshold_with_occupancy=value)


def test_load_rejects_mismatched_metadata_sidecar(detector, tmp_path):
    path = tmp_path / "sidecar-mismatch.joblib"
    detector.save(path)
    sidecar_path = path.with_suffix(".metadata.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["selected_thresholds"]["with_occupancy"]["value"] += 0.01
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the joblib artifact"):
        AnomalyDetector.load(path)


def test_fixed_seed_training_is_reproducible(split):
    first = AnomalyDetector.fit(split.train, n_estimators=25, random_state=29)
    second = AnomalyDetector.fit(split.train, n_estimators=25, random_state=29)
    sample = split.test.iloc[:20]
    np.testing.assert_array_equal(
        first.predict(sample).anomaly_score.to_numpy(),
        second.predict(sample).anomaly_score.to_numpy(),
    )
    assert first.threshold_with_occupancy == second.threshold_with_occupancy
