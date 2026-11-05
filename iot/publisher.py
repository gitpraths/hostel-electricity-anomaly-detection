"""Replay processed ECO intervals to the configured MQTT readings topic.

This is a historical replay simulator; it does not represent a live meter.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data/processed/eco_household_1_15min.parquet"
SCHEMA_VERSION = "2.0"
QOS = 1
TOPIC_ROOT = "hostel/v1/readings"
REQUIRED_COLUMNS = {
    "date",
    "time_of_day",
    "interval_start_second",
    "hour",
    "interval_seconds",
    "powerallphases_mean_w",
    "powerallphases_max_w",
    "powerallphases_std_w",
    "occupancy_fraction",
}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")
LOGGER = logging.getLogger("iot.publisher")


class PublishError(RuntimeError):
    """Raised when a reading could not be delivered with QoS 1."""


@dataclass(frozen=True)
class PublisherConfig:
    dataset: Path = DEFAULT_DATASET
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    site_id: str = "hostel-a"
    meter_id: str = "eco-household-01"
    replay_delay_seconds: float = 0.25
    max_records: int | None = None
    client_id: str = "eco-replay-publisher"
    keepalive_seconds: int = 30
    connect_timeout_seconds: float = 10.0
    publish_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not 1 <= self.broker_port <= 65535:
            raise ValueError("Broker port must be between 1 and 65535.")
        if not math.isfinite(self.replay_delay_seconds) or self.replay_delay_seconds < 0:
            raise ValueError("Replay delay must be a finite non-negative number.")
        if self.max_records is not None and self.max_records < 1:
            raise ValueError("Maximum records must be at least 1.")
        for label, value in (("site_id", self.site_id), ("meter_id", self.meter_id)):
            if not IDENTIFIER_RE.fullmatch(value):
                raise ValueError(f"{label} must contain only letters, digits, underscores, or hyphens.")

    @property
    def topic(self) -> str:
        return f"{TOPIC_ROOT}/{self.site_id}/{self.meter_id}"

    @classmethod
    def from_environment(cls) -> "PublisherConfig":
        """Build defaults from environment variables; CLI arguments can override them."""
        dataset = Path(os.getenv("ECO_DATASET_PATH", str(DEFAULT_DATASET))).expanduser()
        max_records_value = os.getenv("ECO_MAX_RECORDS", "").strip()
        return cls(
            dataset=dataset,
            broker_host=os.getenv("ECO_MQTT_HOST", os.getenv("MQTT_HOST", "127.0.0.1")),
            broker_port=int(os.getenv("ECO_MQTT_PORT", os.getenv("MQTT_PORT", "1883"))),
            site_id=os.getenv("ECO_SITE_ID", "hostel-a"),
            meter_id=os.getenv("ECO_METER_ID", "eco-household-01"),
            replay_delay_seconds=float(os.getenv("ECO_REPLAY_INTERVAL_SECONDS", "0.25")),
            max_records=int(max_records_value) if max_records_value else None,
            client_id=os.getenv("ECO_MQTT_CLIENT_ID", f"eco-replay-{uuid.uuid4().hex[:10]}"),
            keepalive_seconds=int(os.getenv("MQTT_KEEPALIVE_SECONDS", "30")),
        )


def load_records(dataset: Path, max_records: int | None = None) -> pd.DataFrame:
    """Read, validate, and chronologically order processed interval rows."""
    dataset = Path(dataset)
    if not dataset.is_file():
        raise FileNotFoundError(f"Processed dataset not found: {dataset}")
    frame = pd.read_parquet(dataset)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Processed dataset missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Processed dataset contains no records.")

    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    if result["date"].isna().any():
        raise ValueError("Dataset date contains a missing value.")
    if result["date"].dt.tz is not None:
        raise ValueError("ECO date values must remain timezone-naive; do not assign a timezone.")
    result["interval_start_second"] = pd.to_numeric(
        result["interval_start_second"], errors="raise"
    )
    result["hour"] = pd.to_numeric(result["hour"], errors="raise")
    result["interval_seconds"] = pd.to_numeric(result["interval_seconds"], errors="raise")
    for column in (
        "powerallphases_mean_w",
        "powerallphases_max_w",
        "powerallphases_std_w",
    ):
        result[column] = pd.to_numeric(result[column], errors="raise")
        if not result[column].map(math.isfinite).all():
            raise ValueError(f"Dataset column {column} contains a non-finite value.")
    if result["occupancy_fraction"].notna().any():
        known_occupancy = pd.to_numeric(result["occupancy_fraction"], errors="raise")
        if not known_occupancy.dropna().between(0, 1).all():
            raise ValueError("Known occupancy_fraction values must be within [0, 1].")
        result["occupancy_fraction"] = known_occupancy

    if result["interval_start_second"].isna().any() or not result["interval_start_second"].between(0, 86_399).all():
        raise ValueError("interval_start_second must be in [0, 86399].")
    if not (result["interval_start_second"] % 1 == 0).all():
        raise ValueError("interval_start_second must contain whole seconds.")
    if result["hour"].isna().any() or not result["hour"].between(0, 23).all() or not (result["hour"] % 1 == 0).all():
        raise ValueError("hour must be a whole number in [0, 23].")
    if not (result["hour"] == result["interval_start_second"] // 3600).all():
        raise ValueError("hour must match interval_start_second for every row.")
    expected_time = result["interval_start_second"].map(
        lambda second: f"{int(second) // 3600:02d}:{(int(second) // 60) % 60:02d}:{int(second) % 60:02d}"
    )
    if not expected_time.equals(result["time_of_day"].astype(str)):
        raise ValueError("time_of_day must match interval_start_second for every row.")
    if (
        result["interval_seconds"].isna().any()
        or (result["interval_seconds"] <= 0).any()
        or not (result["interval_seconds"] % 1 == 0).all()
    ):
        raise ValueError("interval_seconds must be a positive integer.")
    result["interval_seconds"] = result["interval_seconds"].astype(int)

    result = result.sort_values(
        ["date", "interval_start_second"], kind="stable"
    ).reset_index(drop=True)
    if max_records is not None:
        if max_records < 1:
            raise ValueError("Maximum records must be at least 1.")
        result = result.head(max_records).copy()
    return result


def build_payload(
    record: pd.Series | dict[str, object],
    *,
    site_id: str,
    meter_id: str,
    event_id: str | None = None,
) -> dict[str, object]:
    """Map a processed row to the versioned message and exact ML raw inputs."""
    get = record.get
    day = pd.Timestamp(get("date")).date().isoformat()
    time_of_day = str(get("time_of_day"))
    occupancy_value = get("occupancy_fraction")
    occupancy = None if pd.isna(occupancy_value) else float(occupancy_value)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id or str(uuid.uuid4()),
        # ECO timestamps are date + second-of-day only; intentionally no offset/Z.
        "timestamp": f"{day}T{time_of_day}",
        "date": day,
        "time_of_day": time_of_day,
        "interval_start_second": int(get("interval_start_second")),
        "hour": int(get("hour")),
        "site_id": site_id,
        "meter_id": meter_id,
        "interval_seconds": int(get("interval_seconds")),
        "powerallphases_mean_w": float(get("powerallphases_mean_w")),
        "powerallphases_max_w": float(get("powerallphases_max_w")),
        "powerallphases_std_w": float(get("powerallphases_std_w")),
        "occupancy_fraction": occupancy,
        "source": "eco_household_1_historical_replay",
    }
    return payload


class EcoMqttPublisher:
    """Publish chronological ECO intervals with QoS 1 and fail-fast delivery."""

    def __init__(
        self,
        client: mqtt.Client,
        config: PublisherConfig,
        *,
        sleep: Callable[[float], None] = time.sleep,
        event_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.sleep = sleep
        self.event_id_factory = event_id_factory or (lambda: str(uuid.uuid4()))
        self.published_count = 0

    def connect(self) -> None:
        """Connect only to the configured broker and fail clearly on timeout."""
        try:
            result = self.client.connect(
                self.config.broker_host,
                self.config.broker_port,
                keepalive=self.config.keepalive_seconds,
            )
        except Exception as exc:
            raise ConnectionError(
                f"Could not connect to MQTT broker {self.config.broker_host}:{self.config.broker_port}: {exc}"
            ) from exc
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT connect returned error code {result}.")
        loop_result = self.client.loop_start()
        if loop_result not in (None, mqtt.MQTT_ERR_SUCCESS):
            raise ConnectionError(f"Could not start MQTT network loop (error code {loop_result}).")
        deadline = time.monotonic() + self.config.connect_timeout_seconds
        while not self.client.is_connected() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not self.client.is_connected():
            raise ConnectionError(
                f"Could not connect to MQTT broker {self.config.broker_host}:{self.config.broker_port} "
                f"within {self.config.connect_timeout_seconds:g} seconds."
            )

    def publish_records(self, records: pd.DataFrame) -> int:
        total = len(records)
        for index, (_, record) in enumerate(records.iterrows()):
            payload = build_payload(
                record,
                site_id=self.config.site_id,
                meter_id=self.config.meter_id,
                event_id=self.event_id_factory(),
            )
            encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
            try:
                info = self.client.publish(self.config.topic, encoded, qos=QOS, retain=False)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise PublishError(f"MQTT publish returned error code {info.rc}.")
                info.wait_for_publish(timeout=self.config.publish_timeout_seconds)
                if hasattr(info, "is_published") and not info.is_published():
                    raise PublishError(
                        f"Timed out waiting for QoS 1 acknowledgement for event {payload['event_id']}."
                    )
            except PublishError:
                raise
            except Exception as exc:
                raise PublishError(
                    f"Failed to publish event {payload['event_id']} to {self.config.topic}: {exc}"
                ) from exc

            self.published_count += 1
            if self.published_count == 1 or self.published_count % 100 == 0 or self.published_count == total:
                LOGGER.info("Published %d/%d readings", self.published_count, total)
            if self.config.replay_delay_seconds and index + 1 < total:
                self.sleep(self.config.replay_delay_seconds)
        return self.published_count

    def close(self) -> None:
        """Stop Paho's network loop and disconnect cleanly."""
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()


def _client_from_environment(client_id: str) -> mqtt.Client:
    # Paho 2.x is preferred; fall back to the compatible Paho 1.x constructor.
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    else:  # pragma: no cover - compatibility with older supported environments
        client = mqtt.Client(client_id=client_id)
    username = os.getenv("MQTT_USERNAME", "")
    password = os.getenv("MQTT_PASSWORD", "")
    if username:
        client.username_pw_set(username, password or None)
    return client


def parse_args(argv: Iterable[str] | None = None) -> PublisherConfig:
    defaults = PublisherConfig.from_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=defaults.dataset)
    parser.add_argument("--broker-host", default=defaults.broker_host)
    parser.add_argument("--broker-port", type=int, default=defaults.broker_port)
    parser.add_argument("--site-id", default=defaults.site_id)
    parser.add_argument("--meter-id", default=defaults.meter_id)
    parser.add_argument("--replay-delay", type=float, default=defaults.replay_delay_seconds)
    parser.add_argument("--max-records", type=int, default=defaults.max_records)
    parser.add_argument("--client-id", default=defaults.client_id)
    args = parser.parse_args(argv)
    return PublisherConfig(
        dataset=args.dataset,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        site_id=args.site_id,
        meter_id=args.meter_id,
        replay_delay_seconds=args.replay_delay,
        max_records=args.max_records,
        client_id=args.client_id,
        keepalive_seconds=defaults.keepalive_seconds,
    )


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    publisher_instance: EcoMqttPublisher | None = None
    try:
        config = parse_args(argv)
        records = load_records(config.dataset, config.max_records)
        client = _client_from_environment(config.client_id)
        publisher_instance = EcoMqttPublisher(client, config)
        LOGGER.info(
            "Starting historical ECO replay: %d records to %s at %s:%d (delay %.3fs)",
            len(records), config.topic, config.broker_host, config.broker_port,
            config.replay_delay_seconds,
        )
        try:
            publisher_instance.connect()
            publisher_instance.publish_records(records)
        except KeyboardInterrupt:
            LOGGER.info(
                "Replay interrupted by user after %d published readings",
                publisher_instance.published_count,
            )
        finally:
            publisher_instance.close()
        LOGGER.info("Replay finished: %d readings published", publisher_instance.published_count)
        return 0
    except (ConnectionError, FileNotFoundError, ValueError, PublishError) as exc:
        count = 0 if publisher_instance is None else publisher_instance.published_count
        LOGGER.error("Publisher stopped after %d readings: %s", count, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
