"""Publisher unit tests use mocked MQTT clients and synthetic unit rows only."""

import json
from pathlib import Path

import pandas as pd
import pytest

from iot import publisher
from iot.publisher import (
    EcoMqttPublisher,
    PublishError,
    PublisherConfig,
    build_payload,
    load_records,
)


def sample_rows() -> pd.DataFrame:
    """Small synthetic fixture for interface tests; not ECO measurement data."""
    return pd.DataFrame([
        {
            "date": "2012-06-05",
            "time_of_day": "00:15:00",
            "interval_start_second": 900,
            "hour": 0,
            "interval_seconds": 900,
            "powerallphases_mean_w": 110.5,
            "powerallphases_max_w": 140.0,
            "powerallphases_std_w": 5.5,
            "occupancy_fraction": float("nan"),
        },
        {
            "date": "2012-06-05",
            "time_of_day": "00:00:00",
            "interval_start_second": 0,
            "hour": 0,
            "interval_seconds": 900,
            "powerallphases_mean_w": 100.0,
            "powerallphases_max_w": 125.0,
            "powerallphases_std_w": 4.0,
            "occupancy_fraction": 0.0,
        },
    ])


class FakePublishInfo:
    def __init__(self, rc: int = 0, published: bool = True):
        self.rc = rc
        self._published = published

    def wait_for_publish(self, timeout=None):
        return None

    def is_published(self):
        return self._published


class FakeMqttClient:
    def __init__(self, infos=None):
        self.infos = list(infos or [])
        self.messages = []

    def publish(self, topic, payload, qos, retain):
        self.messages.append((topic, payload, qos, retain))
        return self.infos.pop(0) if self.infos else FakePublishInfo()


def test_load_records_reads_parquet_and_sorts_chronologically(monkeypatch, tmp_path):
    path = tmp_path / "small.parquet"
    path.touch()
    source = sample_rows()
    calls = []

    def fake_read_parquet(received_path):
        calls.append(Path(received_path))
        return source

    monkeypatch.setattr(publisher.pd, "read_parquet", fake_read_parquet)
    loaded = load_records(path)
    assert calls == [path]
    assert loaded["time_of_day"].tolist() == ["00:00:00", "00:15:00"]
    assert loaded["interval_start_second"].tolist() == [0, 900]


def test_load_records_supports_max_records(monkeypatch, tmp_path):
    path = tmp_path / "small.parquet"
    path.touch()
    monkeypatch.setattr(publisher.pd, "read_parquet", lambda _: sample_rows())
    loaded = load_records(path, max_records=1)
    assert len(loaded) == 1
    assert loaded.iloc[0]["time_of_day"] == "00:00:00"


def test_topic_json_features_units_and_timestamp():
    record = sample_rows().iloc[0]
    payload = build_payload(
        record, site_id="north_hostel", meter_id="meter_01", event_id="event-1"
    )
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)
    assert f"hostel/v1/readings/{decoded['site_id']}/{decoded['meter_id']}" == (
        "hostel/v1/readings/north_hostel/meter_01"
    )
    assert decoded["schema_version"] == "2.0"
    assert decoded["timestamp"] == "2012-06-05T00:15:00"
    assert decoded["date"] == "2012-06-05"
    assert decoded["time_of_day"] == "00:15:00"
    assert decoded["interval_start_second"] == 900
    assert decoded["interval_seconds"] == 900
    assert decoded["powerallphases_mean_w"] == 110.5
    assert decoded["powerallphases_max_w"] == 140.0
    assert decoded["powerallphases_std_w"] == 5.5
    assert decoded["occupancy_fraction"] is None
    assert decoded["source"] == "eco_household_1_historical_replay"
    assert "Z" not in decoded["timestamp"]


def test_unknown_occupancy_is_json_null():
    payload = build_payload(sample_rows().iloc[0], site_id="site", meter_id="meter")
    assert json.loads(json.dumps(payload, allow_nan=False))["occupancy_fraction"] is None


def test_publisher_sends_chronologically_unique_ids_and_qos_one():
    client = FakeMqttClient()
    config = PublisherConfig(replay_delay_seconds=0, site_id="site-a", meter_id="meter-a")
    publisher_instance = EcoMqttPublisher(client, config)
    assert publisher_instance.publish_records(load_records_from_frame(sample_rows())) == 2
    payloads = [json.loads(message[1]) for message in client.messages]
    assert [row["interval_start_second"] for row in payloads] == [0, 900]
    assert len({row["event_id"] for row in payloads}) == 2
    assert all(message[0] == "hostel/v1/readings/site-a/meter-a" for message in client.messages)
    assert all(message[2:] == (1, False) for message in client.messages)


def load_records_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Use the same validation/sort path as file ingestion without filesystem data."""
    # load_records intentionally owns parquet reading, so tests explicitly sort this unit frame.
    return frame.sort_values(["date", "interval_start_second"], kind="stable").reset_index(drop=True)


def test_configurable_replay_delay_applies_between_messages_only():
    waits = []
    client = FakeMqttClient()
    config = PublisherConfig(replay_delay_seconds=0.125)
    replay = EcoMqttPublisher(client, config, sleep=waits.append)
    replay.publish_records(load_records_from_frame(sample_rows()))
    assert waits == [0.125]


def test_publish_failure_raises_instead_of_silently_dropping():
    client = FakeMqttClient(infos=[FakePublishInfo(rc=4)])
    replay = EcoMqttPublisher(client, PublisherConfig(replay_delay_seconds=0))
    with pytest.raises(PublishError, match="error code 4"):
        replay.publish_records(load_records_from_frame(sample_rows()))
    assert replay.published_count == 0


def test_qos_one_acknowledgement_timeout_raises():
    client = FakeMqttClient(infos=[FakePublishInfo(published=False)])
    replay = EcoMqttPublisher(client, PublisherConfig(replay_delay_seconds=0))
    with pytest.raises(PublishError, match="Timed out waiting for QoS 1 acknowledgement"):
        replay.publish_records(load_records_from_frame(sample_rows()))


def test_connection_failure_raises_actionable_error():
    class FailingClient(FakeMqttClient):
        def connect(self, host, port, keepalive):
            raise OSError("connection refused")

    replay = EcoMqttPublisher(FailingClient(), PublisherConfig())
    with pytest.raises(ConnectionError, match="127.0.0.1:1883.*connection refused"):
        replay.connect()


def test_configuration_defaults_to_loopback_and_validates_delay():
    config = PublisherConfig()
    assert (config.broker_host, config.broker_port) == ("127.0.0.1", 1883)
    with pytest.raises(ValueError, match="non-negative"):
        PublisherConfig(replay_delay_seconds=-0.1)
