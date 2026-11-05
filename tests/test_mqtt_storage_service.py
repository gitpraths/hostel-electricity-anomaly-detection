"""Storage receiver tests use mocked Paho clients and temporary SQLite files."""

import json
import sqlite3

import pytest

from database.store import SQLiteStore
from mqtt.storage_service import MqttStorageService, StorageServiceConfig

READING_ID = "725273ea-ae24-41ee-8aaf-47287c642b25"
PREDICTION_ID = "49cfb91e-aead-49b4-884a-7263c3660230"
READING_TOPIC = "hostel/v1/readings/hostel-a/eco-household-01"
PREDICTION_TOPIC = "hostel/v1/predictions/hostel-a/eco-household-01"


def reading(*, event_id=READING_ID, occupancy=0.25, mean=110.0):
    return {
        "schema_version": "2.0",
        "event_id": event_id,
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


def prediction(*, event_id=PREDICTION_ID, source_event_id=READING_ID, score=0.72):
    return {
        "schema_version": "1.0",
        "event_id": event_id,
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


class FakeClient:
    def __init__(self):
        self.subscriptions = []
        self.acks = []

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))
        return (0, len(self.subscriptions))

    def ack(self, mid, qos):
        self.acks.append((mid, qos))
        return 0


class FakeMessage:
    def __init__(self, topic, payload, *, mid=1, qos=1):
        self.topic = topic
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.mid = mid
        self.qos = qos


@pytest.fixture
def service(tmp_path):
    store = SQLiteStore(tmp_path / "service.sqlite3")
    client = FakeClient()
    instance = MqttStorageService(store, client, StorageServiceConfig(database_path=tmp_path / "service.sqlite3"))
    yield instance, store, client
    store.close()


def test_storage_service_subscribes_to_both_topics_at_qos_one(service):
    instance, _, client = service
    instance.on_connect(client, None, {}, 0, None)
    assert client.subscriptions == [
        ("hostel/v1/readings/+/+", 1),
        ("hostel/v1/predictions/+/+", 1),
    ]
    assert instance.connected.is_set()


def test_valid_reading_is_committed_before_qos_ack(service):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(READING_TOPIC, reading()))
    assert store.get_reading(READING_ID)["event_id"] == READING_ID
    assert client.acks == [(1, 1)]
    assert instance.stored_readings == 1


def test_valid_prediction_is_stored_with_all_contract_fields(service):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(PREDICTION_TOPIC, prediction()))
    row = store.get_prediction(PREDICTION_ID)
    assert row["schema_version"] == "1.0"
    assert row["source_event_id"] == READING_ID
    assert row["score"] == 0.72
    assert row["threshold"] == 0.59
    assert row["anomaly"] == 1
    assert row["robust_anomaly"] == 0
    assert row["received_at"].endswith("Z")
    assert row["source_reading_event_id"] is None
    assert client.acks == [(1, 1)]


def test_prediction_before_reading_is_retained_then_linked(service):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(PREDICTION_TOPIC, prediction(), mid=1))
    assert store.get_prediction(PREDICTION_ID)["source_reading_event_id"] is None
    instance.on_message(client, None, FakeMessage(READING_TOPIC, reading(), mid=2))
    assert store.get_prediction(PREDICTION_ID)["source_reading_event_id"] == READING_ID
    assert client.acks == [(1, 1), (2, 1)]


def test_reading_before_prediction_is_linked_immediately(service):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(READING_TOPIC, reading(), mid=1))
    instance.on_message(client, None, FakeMessage(PREDICTION_TOPIC, prediction(), mid=2))
    assert store.get_prediction(PREDICTION_ID)["source_reading_event_id"] == READING_ID


def test_duplicate_delivery_is_acknowledged_without_overwrite(service):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(READING_TOPIC, reading(mean=110), mid=1))
    instance.on_message(client, None, FakeMessage(READING_TOPIC, reading(mean=999), mid=2))
    assert store.get_reading(READING_ID)["powerallphases_mean_w"] == 110
    assert instance.duplicates == 1
    assert client.acks == [(1, 1), (2, 1)]


@pytest.mark.parametrize("payload", [b"{bad json", b"[]"])
def test_invalid_json_or_non_object_is_logged_and_acknowledged(service, payload):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(READING_TOPIC, payload))
    assert store.counts() == (0, 0)
    assert instance.invalid_messages == 1
    assert client.acks == [(1, 1)]


@pytest.mark.parametrize(
    "topic,message,expected_text",
    [
        (READING_TOPIC, {**reading(), "schema_version": "99"}, "Unsupported reading schema_version"),
        (READING_TOPIC, {key: value for key, value in reading().items() if key != "hour"}, "hour"),
        ("hostel/v1/readings/other/meter", reading(), "does not match the topic"),
        (PREDICTION_TOPIC, {**prediction(), "schema_version": "9"}, "Unsupported prediction schema_version"),
        ("hostel/v1/predictions/hostel-b/eco-household-01", prediction(), "does not match the topic"),
    ],
)
def test_contract_errors_are_logged_and_do_not_crash(topic, message, expected_text, service, caplog):
    instance, store, client = service
    instance.on_message(client, None, FakeMessage(topic, message))
    assert store.counts() == (0, 0)
    assert expected_text in caplog.text
    assert instance.invalid_messages == 1
    assert client.acks == [(1, 1)]


def test_database_failure_is_not_acknowledged(service, monkeypatch, caplog):
    instance, store, client = service

    def fail_insert(_):
        raise sqlite3.OperationalError("injected disk error")

    monkeypatch.setattr(store, "insert_reading", fail_insert)
    instance.on_message(client, None, FakeMessage(READING_TOPIC, reading()))
    assert client.acks == []
    assert instance.database_failures == 1
    assert "unacknowledged" in caplog.text


def test_database_path_environment_configuration(monkeypatch, tmp_path):
    configured_path = tmp_path / "configured.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(configured_path))
    monkeypatch.setenv("STORAGE_MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("STORAGE_MQTT_PORT", "1883")
    config = StorageServiceConfig.from_environment()
    assert config.database_path == configured_path
    assert config.broker_host == "127.0.0.1"
    assert config.broker_port == 1883

