"""SQLite store tests use only temporary databases and synthetic message rows."""

import sqlite3
import uuid

import pytest

from database.store import SQLiteStore, StorageConflictError


READING_ID = "725273ea-ae24-41ee-8aaf-47287c642b25"
PREDICTION_ID = "49cfb91e-aead-49b4-884a-7263c3660230"


def reading(event_id=READING_ID, *, occupancy=0.25, mean=110.0):
    return {
        "event_id": event_id,
        "schema_version": "2.0",
        "timestamp": "2012-06-05T00:15:00",
        "date": "2012-06-05",
        "time_of_day": "00:15:00",
        "interval_start_second": 900,
        "hour": 0,
        "site_id": "hostel-a",
        "meter_id": "eco-household-01",
        "interval_seconds": 900,
        "powerallphases_mean_w": mean,
        "powerallphases_max_w": 140.0,
        "powerallphases_std_w": 5.0,
        "occupancy_fraction": occupancy,
        "source": "eco_household_1_historical_replay",
    }


def prediction(event_id=PREDICTION_ID, source_event_id=READING_ID, *, score=0.72):
    return {
        "event_id": event_id,
        "schema_version": "1.0",
        "source_event_id": source_event_id,
        "timestamp": "2012-06-05T00:15:00",
        "site_id": "hostel-a",
        "meter_id": "eco-household-01",
        "model_version": "iforest-1.0.0-testhash",
        "feature_schema_version": "1.0.0",
        "anomaly": True,
        "score": score,
        "threshold": 0.59,
        "model_variant": "with_occupancy",
        "robust_anomaly": False,
        "robust_score": 2.2,
        "explanation": "synthetic test review candidate",
    }


def test_database_initialization_creates_contract_tables_and_indexes(tmp_path):
    path = tmp_path / "nested" / "storage.sqlite3"
    store = SQLiteStore(path)
    tables = {
        row["name"] for row in store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    indexes = {
        row["name"] for row in store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    assert {"readings", "predictions"} <= tables
    assert "idx_predictions_source_event_id" in indexes
    assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert path.exists()
    store.close()


def test_reading_insert_and_nullable_occupancy(tmp_path):
    with SQLiteStore(tmp_path / "readings.sqlite3") as store:
        assert store.insert_reading(reading(occupancy=None)) is True
        row = store.get_reading(READING_ID)
        assert row["schema_version"] == "2.0"
        assert row["occupancy_fraction"] is None
        assert row["powerallphases_mean_w"] == 110.0
        assert row["received_at"].endswith("Z")


def test_duplicate_reading_event_is_idempotent_and_does_not_overwrite(tmp_path):
    with SQLiteStore(tmp_path / "dedupe-reading.sqlite3") as store:
        assert store.insert_reading(reading(mean=110.0)) is True
        assert store.insert_reading(reading(mean=999.0)) is False
        assert store.get_reading(READING_ID)["powerallphases_mean_w"] == 110.0
        assert store.counts() == (1, 0)


def test_prediction_before_reading_is_saved_then_resolved(tmp_path):
    with SQLiteStore(tmp_path / "prediction-first.sqlite3") as store:
        assert store.insert_prediction(prediction()) is True
        orphan = store.get_prediction(PREDICTION_ID)
        assert orphan["source_event_id"] == READING_ID
        assert orphan["source_reading_event_id"] is None
        assert store.insert_reading(reading()) is True
        resolved = store.get_prediction(PREDICTION_ID)
        assert resolved["source_event_id"] == READING_ID
        assert resolved["source_reading_event_id"] == READING_ID


def test_reading_before_prediction_links_on_prediction_insert(tmp_path):
    with SQLiteStore(tmp_path / "reading-first.sqlite3") as store:
        store.insert_reading(reading())
        store.insert_prediction(prediction())
        assert store.get_prediction(PREDICTION_ID)["source_reading_event_id"] == READING_ID


def test_duplicate_prediction_event_is_idempotent_and_does_not_overwrite(tmp_path):
    with SQLiteStore(tmp_path / "dedupe-prediction.sqlite3") as store:
        store.insert_prediction(prediction(score=0.72))
        assert store.insert_prediction(prediction(score=0.99)) is False
        assert store.get_prediction(PREDICTION_ID)["score"] == 0.72
        assert store.counts() == (0, 1)


def test_predictions_schema_fields_are_preserved(tmp_path):
    with SQLiteStore(tmp_path / "prediction-fields.sqlite3") as store:
        store.insert_prediction(prediction())
        row = store.get_prediction(PREDICTION_ID)
        assert row["schema_version"] == "1.0"
        assert row["source_event_id"] == READING_ID
        assert row["model_version"] == "iforest-1.0.0-testhash"
        assert row["feature_schema_version"] == "1.0.0"
        assert row["anomaly"] == 1
        assert row["robust_anomaly"] == 0


def test_reading_transaction_rolls_back_insert_and_relationship_update(tmp_path):
    with SQLiteStore(tmp_path / "rollback-reading.sqlite3") as store:
        store.insert_prediction(prediction())
        store.connection.execute("""CREATE TRIGGER force_resolution_failure
            BEFORE UPDATE OF source_reading_event_id ON predictions
            BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
            store.insert_reading(reading())
        assert store.get_reading(READING_ID) is None
        assert store.get_prediction(PREDICTION_ID)["source_reading_event_id"] is None
        store.connection.execute("DROP TRIGGER force_resolution_failure")
        assert store.insert_reading(reading()) is True


def test_prediction_insert_transaction_rolls_back_on_sql_failure(tmp_path):
    with SQLiteStore(tmp_path / "rollback-prediction.sqlite3") as store:
        store.connection.execute("""CREATE TRIGGER force_prediction_failure
            BEFORE INSERT ON predictions
            BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
            store.insert_prediction(prediction())
        assert store.counts() == (0, 0)


def test_prediction_existing_source_with_conflicting_ids_is_rejected(tmp_path):
    with SQLiteStore(tmp_path / "relationship-conflict.sqlite3") as store:
        store.insert_reading(reading())
        wrong_site = {**prediction(), "site_id": "other-site"}
        with pytest.raises(StorageConflictError, match="do not match"):
            store.insert_prediction(wrong_site)
        assert store.counts() == (1, 0)


def test_multiple_readings_and_predictions_keep_unique_contract_ids(tmp_path):
    second_reading_id = str(uuid.uuid4())
    second_prediction_id = str(uuid.uuid4())
    with SQLiteStore(tmp_path / "counts.sqlite3") as store:
        store.insert_reading(reading())
        store.insert_reading(reading(second_reading_id))
        store.insert_prediction(prediction())
        store.insert_prediction(prediction(second_prediction_id, second_reading_id))
        assert store.counts() == (2, 2)
