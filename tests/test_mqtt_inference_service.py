"""MQTT inference service tests use mock detector/client objects, never a broker."""

import json
import uuid

import numpy as np
import pandas as pd
import pytest

from mqtt.inference_service import (
    InvalidReading,
    MqttInferenceService,
    ServiceConfig,
    reading_to_frame,
)


READING = {
    "schema_version": "2.0",
    "event_id": "8a86c0f9-6d10-41ec-8503-8a4f7bf7d114",
    "timestamp": "2012-12-24T17:45:00",
    "date": "2012-12-24",
    "time_of_day": "17:45:00",
    "interval_start_second": 63900,
    "hour": 17,
    "site_id": "hostel-a",
    "meter_id": "eco-household-01",
    "interval_seconds": 900,
    "powerallphases_mean_w": 322.63967,
    "powerallphases_max_w": 402.654,
    "powerallphases_std_w": 25.34958,
    "occupancy_fraction": 1.0,
    "source": "eco_household_1_historical_replay",
}
READING_TOPIC = "hostel/v1/readings/hostel-a/eco-household-01"


class FakeDetector:
    metadata = {"feature_schema_version": "1.0.0"}

    def __init__(self):
        self.received = []

    def predict(self, frame):
        self.received.append(frame.copy())
        return pd.DataFrame([{
            "iforest_flag": True,
            "anomaly_score": 0.72,
            "anomaly_threshold": 0.59,
            "model_variant": "with_occupancy" if pd.notna(frame.iloc[0]["occupancy_fraction"]) else "without_occupancy",
            "robust_flag": True,
            "robust_score": 4.2,
            "explanation": "high load in occupied period; review candidate",
        }])


class FakeMqttClient:
    def __init__(self):
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.subscriptions = []
        self.published = []

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))
        return (0, 1)

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return type("Info", (), {"rc": 0})()


class FakeMessage:
    topic = READING_TOPIC
    payload = json.dumps(READING).encode("utf-8")


def create_service():
    detector = FakeDetector()
    client = FakeMqttClient()
    service = MqttInferenceService(
        detector,
        client,
        model_version="iforest-1.0.0-testhash",
        config=ServiceConfig(),
    )
    return service, detector, client


def test_reading_mapping_matches_detector_raw_input_contract():
    model_input = reading_to_frame(READING_TOPIC, READING)
    assert model_input.columns.tolist() == [
        "date", "time_of_day", "interval_start_second", "hour",
        "powerallphases_mean_w", "powerallphases_max_w",
        "powerallphases_std_w", "occupancy_fraction",
    ]
    row = model_input.iloc[0]
    assert row["date"] == pd.Timestamp("2012-12-24")
    assert row["interval_start_second"] == 63900
    assert row["powerallphases_mean_w"] == 322.63967
    assert row["powerallphases_max_w"] == 402.654
    assert row["powerallphases_std_w"] == 25.34958
    assert row["occupancy_fraction"] == 1.0


def test_null_occupancy_stays_missing_for_model_input():
    reading = {**READING, "occupancy_fraction": None}
    model_input = reading_to_frame(READING_TOPIC, reading)
    assert np.isnan(model_input.iloc[0]["occupancy_fraction"])


def test_invalid_schema_topic_or_timestamp_is_rejected():
    with pytest.raises(InvalidReading, match="Unsupported reading schema"):
        reading_to_frame(READING_TOPIC, {**READING, "schema_version": "1.0"})
    with pytest.raises(InvalidReading, match="does not match the MQTT topic"):
        reading_to_frame(READING_TOPIC, {**READING, "site_id": "other-site"})
    with pytest.raises(InvalidReading, match="timezone-naive"):
        reading_to_frame(READING_TOPIC, {**READING, "timestamp": "2012-12-24T17:45:00Z"})
    with pytest.raises(InvalidReading, match="expects 900-second intervals"):
        reading_to_frame(READING_TOPIC, {**READING, "interval_seconds": 60})


def test_subscribes_to_reading_filter_with_qos_one():
    service, _, client = create_service()
    service.on_connect(client, None, {}, 0, None)
    assert client.subscriptions == [("hostel/v1/readings/+/+", 1)]
    assert service.connected.is_set()


def test_paho_v2_success_reason_code_object_is_accepted():
    service, _, client = create_service()
    success_reason = type("ReasonCode", (), {"value": 0, "__str__": lambda self: "Success"})()
    service.on_connect(client, None, {}, success_reason, None)
    assert service.connected.is_set()
    assert client.subscriptions == [("hostel/v1/readings/+/+", 1)]


def test_valid_reading_is_scored_and_prediction_is_published():
    service, detector, client = create_service()
    service.on_message(client, None, FakeMessage())
    assert len(detector.received) == 1
    assert len(client.published) == 1
    topic, encoded, qos, retain = client.published[0]
    prediction = json.loads(encoded)
    assert topic == "hostel/v1/predictions/hostel-a/eco-household-01"
    assert qos == 1 and retain is False
    assert prediction["source_event_id"] == READING["event_id"]
    assert prediction["timestamp"] == READING["timestamp"]
    assert prediction["model_version"] == "iforest-1.0.0-testhash"
    assert prediction["feature_schema_version"] == "1.0.0"
    assert prediction["anomaly"] is True
    assert prediction["score"] == 0.72
    assert prediction["threshold"] == 0.59
    assert uuid.UUID(prediction["event_id"])
    assert service.readings_scored == 1


def test_prediction_event_id_is_stable_for_qos_redelivery():
    service, _, _ = create_service()
    first = service.handle_reading(READING_TOPIC, json.dumps(READING))
    repeated = service.handle_reading(READING_TOPIC, json.dumps(READING))
    assert first["event_id"] == repeated["event_id"]


def test_malformed_reading_is_logged_and_not_published():
    service, _, client = create_service()
    message = type("Message", (), {"topic": READING_TOPIC, "payload": b"{bad json"})()
    service.on_message(client, None, message)
    assert client.published == []
    assert service.invalid_readings == 1
