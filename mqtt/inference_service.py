"""Consume MQTT reading intervals, score them, and publish anomaly predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt

from ml.detector import AnomalyDetector

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models/eco_household_1_iforest.joblib"
READING_SCHEMA_VERSION = "2.0"
PREDICTION_SCHEMA_VERSION = "1.0"
READING_TOPIC_FILTER = "hostel/v1/readings/+/+"
PREDICTION_TOPIC_PREFIX = "hostel/v1/predictions"
MODEL_INTERVAL_SECONDS = 900
QOS = 1
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
LOGGER = logging.getLogger("mqtt.inference")


class InvalidReading(ValueError):
    """Raised for malformed or incompatible reading messages."""


@dataclass(frozen=True)
class ServiceConfig:
    model_path: Path = DEFAULT_MODEL
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    readings_topic: str = READING_TOPIC_FILTER
    client_id: str = "hostel-ml-inference"
    keepalive_seconds: int = 30
    connect_timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not 1 <= self.broker_port <= 65535:
            raise ValueError("Broker port must be between 1 and 65535.")
        if not self.readings_topic.startswith("hostel/v1/readings/"):
            raise ValueError("Readings subscription must use the hostel/v1/readings topic namespace.")

    @classmethod
    def from_environment(cls) -> "ServiceConfig":
        return cls(
            model_path=Path(os.getenv("ML_MODEL_PATH", str(DEFAULT_MODEL))).expanduser(),
            broker_host=os.getenv("ML_MQTT_HOST", os.getenv("MQTT_HOST", "127.0.0.1")),
            broker_port=int(os.getenv("ML_MQTT_PORT", os.getenv("MQTT_PORT", "1883"))),
            readings_topic=os.getenv("ML_READINGS_TOPIC", READING_TOPIC_FILTER),
            client_id=os.getenv("ML_MQTT_CLIENT_ID", "hostel-ml-inference"),
            keepalive_seconds=int(os.getenv("MQTT_KEEPALIVE_SECONDS", "30")),
        )


def model_version_for(model_path: Path, detector: AnomalyDetector) -> str:
    """Create a compact reproducible model identifier without exposing paths."""
    digest = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()[:16]
    schema_version = detector.metadata["feature_schema_version"]
    return f"iforest-{schema_version}-{digest}"


def _number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidReading(f"{key} must be a JSON number.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise InvalidReading(f"{key} must be finite.")
    return numeric


def _reason_code_value(reason_code: Any) -> int:
    """Normalize Paho 1.x integers and Paho 2.x ReasonCode objects."""
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def reading_to_frame(topic: str, payload: dict[str, Any]) -> pd.DataFrame:
    """Validate schema and map one reading into AnomalyDetector's raw columns."""
    parts = topic.split("/")
    if len(parts) != 5 or parts[:3] != ["hostel", "v1", "readings"]:
        raise InvalidReading(f"Unexpected reading topic: {topic!r}.")
    topic_site, topic_meter = parts[3], parts[4]
    if payload.get("schema_version") != READING_SCHEMA_VERSION:
        raise InvalidReading(
            f"Unsupported reading schema_version {payload.get('schema_version')!r}; "
            f"expected {READING_SCHEMA_VERSION}."
        )
    event_id = payload.get("event_id")
    try:
        uuid.UUID(str(event_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidReading("event_id must be a UUID string.") from exc
    for key, topic_value in (("site_id", topic_site), ("meter_id", topic_meter)):
        value = payload.get(key)
        if not isinstance(value, str) or not ID_RE.fullmatch(value):
            raise InvalidReading(f"{key} must be a URL-safe identifier.")
        if value != topic_value:
            raise InvalidReading(f"Payload {key} does not match the MQTT topic.")

    day = payload.get("date")
    time_of_day = payload.get("time_of_day")
    timestamp = payload.get("timestamp")
    if not isinstance(day, str) or not isinstance(time_of_day, str):
        raise InvalidReading("date and time_of_day must be strings.")
    try:
        parsed_timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError) as exc:
        raise InvalidReading("timestamp must be timezone-naive YYYY-MM-DDTHH:MM:SS.") from exc
    try:
        parsed_day = datetime.strptime(day, "%Y-%m-%d").date()
        parsed_time = datetime.strptime(time_of_day, "%H:%M:%S").time()
    except ValueError as exc:
        raise InvalidReading("date or time_of_day has an invalid format.") from exc
    if (parsed_timestamp.date(), parsed_timestamp.time()) != (parsed_day, parsed_time):
        raise InvalidReading("timestamp must agree with date and time_of_day.")

    interval_start_second = _number(payload, "interval_start_second")
    hour = _number(payload, "hour")
    interval_seconds = _number(payload, "interval_seconds")
    if not interval_start_second.is_integer() or not 0 <= interval_start_second < 86_400:
        raise InvalidReading("interval_start_second must be a whole second in [0, 86400).")
    if not hour.is_integer() or int(hour) != int(interval_start_second) // 3600:
        raise InvalidReading("hour must match interval_start_second.")
    if not interval_seconds.is_integer() or interval_seconds <= 0:
        raise InvalidReading("interval_seconds must be a positive integer.")
    if int(interval_seconds) != MODEL_INTERVAL_SECONDS:
        raise InvalidReading(
            f"Current model expects {MODEL_INTERVAL_SECONDS}-second intervals; "
            f"received {int(interval_seconds)}."
        )
    expected_tod = (
        f"{int(interval_start_second) // 3600:02d}:"
        f"{(int(interval_start_second) // 60) % 60:02d}:"
        f"{int(interval_start_second) % 60:02d}"
    )
    if time_of_day != expected_tod:
        raise InvalidReading("time_of_day must match interval_start_second.")

    power_mean = _number(payload, "powerallphases_mean_w")
    power_max = _number(payload, "powerallphases_max_w")
    power_std = _number(payload, "powerallphases_std_w")
    occupancy_value = payload.get("occupancy_fraction")
    if occupancy_value is None:
        occupancy: float = np.nan
    else:
        occupancy = _number(payload, "occupancy_fraction")
        if not 0 <= occupancy <= 1:
            raise InvalidReading("occupancy_fraction must be in [0, 1] or null.")

    # These are exactly the raw fields expected by AnomalyDetector.predict.
    return pd.DataFrame([{
        "date": pd.Timestamp(parsed_day),
        "time_of_day": time_of_day,
        "interval_start_second": int(interval_start_second),
        "hour": int(hour),
        "powerallphases_mean_w": power_mean,
        "powerallphases_max_w": power_max,
        "powerallphases_std_w": power_std,
        "occupancy_fraction": occupancy,
    }])


class MqttInferenceService:
    """Subscribe to reading events and publish one linked model result per valid event."""

    def __init__(
        self,
        detector: AnomalyDetector,
        client: mqtt.Client,
        *,
        model_version: str,
        config: ServiceConfig,
    ) -> None:
        self.detector = detector
        self.client = client
        self.model_version = model_version
        self.config = config
        self.connected = threading.Event()
        self.stop_requested = threading.Event()
        self.readings_scored = 0
        self.invalid_readings = 0
        self.prediction_publish_failures = 0
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    @staticmethod
    def prediction_topic(site_id: str, meter_id: str) -> str:
        return f"{PREDICTION_TOPIC_PREFIX}/{site_id}/{meter_id}"

    def on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        code = _reason_code_value(reason_code)
        if code != 0:
            LOGGER.error("MQTT connection refused (reason code %s)", reason_code)
            return
        result = client.subscribe(self.config.readings_topic, qos=QOS)
        rc = result[0] if isinstance(result, tuple) else result
        if rc != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("Could not subscribe to %s (error code %s)", self.config.readings_topic, rc)
            return
        self.connected.set()
        LOGGER.info("Subscribed QoS 1 to %s", self.config.readings_topic)

    def on_disconnect(self, client, userdata, disconnect_flags=None, reason_code=None, properties=None) -> None:
        self.connected.clear()
        if reason_code is not None and _reason_code_value(reason_code) != 0:
            LOGGER.warning("MQTT disconnected (reason code %s); client will reconnect if configured", reason_code)

    def handle_reading(self, topic: str, raw_payload: bytes | str) -> dict[str, Any]:
        try:
            decoded = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else raw_payload
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise InvalidReading(f"Message is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise InvalidReading("Reading JSON must be an object.")

        model_input = reading_to_frame(topic, payload)
        scored = self.detector.predict(model_input).iloc[0]
        prediction: dict[str, Any] = {
            "schema_version": PREDICTION_SCHEMA_VERSION,
            "event_id": str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"hostel-prediction:{self.model_version}:{payload['event_id']}",
            )),
            "source_event_id": payload["event_id"],
            "timestamp": payload["timestamp"],
            "site_id": payload["site_id"],
            "meter_id": payload["meter_id"],
            "model_version": self.model_version,
            "feature_schema_version": self.detector.metadata["feature_schema_version"],
            "anomaly": bool(scored["iforest_flag"]),
            "score": float(scored["anomaly_score"]),
            "threshold": float(scored["anomaly_threshold"]),
            "model_variant": str(scored["model_variant"]),
            "robust_anomaly": bool(scored["robust_flag"]),
            "robust_score": float(scored["robust_score"]),
            "explanation": str(scored["explanation"]),
        }
        return prediction

    def on_message(self, client, userdata, message) -> None:
        try:
            prediction = self.handle_reading(message.topic, message.payload)
        except InvalidReading as exc:
            self.invalid_readings += 1
            LOGGER.warning("Rejected reading on %s: %s", message.topic, exc)
            return
        except Exception:
            self.invalid_readings += 1
            LOGGER.exception("Inference failed for reading on %s", message.topic)
            return

        topic = self.prediction_topic(prediction["site_id"], prediction["meter_id"])
        try:
            encoded = json.dumps(prediction, allow_nan=False, separators=(",", ":"))
            result = client.publish(topic, encoded, qos=QOS, retain=False)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"publish returned error code {result.rc}")
        except Exception:
            self.prediction_publish_failures += 1
            LOGGER.exception("Failed to queue prediction for source event %s", prediction["source_event_id"])
            return

        self.readings_scored += 1
        if self.readings_scored == 1 or self.readings_scored % 100 == 0:
            LOGGER.info("Scored %d readings; latest anomaly=%s", self.readings_scored, prediction["anomaly"])

    def run(self) -> None:
        """Connect and service messages until interrupted or stop is requested."""
        self.client.connect(
            self.config.broker_host,
            self.config.broker_port,
            keepalive=self.config.keepalive_seconds,
        )
        loop_result = self.client.loop_start()
        if loop_result not in (None, mqtt.MQTT_ERR_SUCCESS):
            raise ConnectionError(f"Could not start MQTT network loop (error code {loop_result}).")
        if not self.connected.wait(self.config.connect_timeout_seconds):
            raise ConnectionError(
                f"Could not subscribe through {self.config.broker_host}:{self.config.broker_port} "
                f"within {self.config.connect_timeout_seconds:g} seconds."
            )
        LOGGER.info("Inference service ready; predictions publish to %s/{site_id}/{meter_id}", PREDICTION_TOPIC_PREFIX)
        try:
            while not self.stop_requested.wait(0.25):
                pass
        finally:
            self.close()

    def close(self) -> None:
        self.stop_requested.set()
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()


def _make_client(client_id: str) -> mqtt.Client:
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    else:  # pragma: no cover - compatibility with Paho 1.x
        client = mqtt.Client(client_id=client_id)
    username, password = os.getenv("MQTT_USERNAME", ""), os.getenv("MQTT_PASSWORD", "")
    if username:
        client.username_pw_set(username, password or None)
    return client


def parse_args(argv: Iterable[str] | None = None) -> ServiceConfig:
    defaults = ServiceConfig.from_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=defaults.model_path)
    parser.add_argument("--broker-host", default=defaults.broker_host)
    parser.add_argument("--broker-port", type=int, default=defaults.broker_port)
    parser.add_argument("--readings-topic", default=defaults.readings_topic)
    parser.add_argument("--client-id", default=defaults.client_id)
    args = parser.parse_args(argv)
    return ServiceConfig(
        model_path=args.model,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        readings_topic=args.readings_topic,
        client_id=args.client_id,
        keepalive_seconds=defaults.keepalive_seconds,
        connect_timeout_seconds=defaults.connect_timeout_seconds,
    )


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service: MqttInferenceService | None = None
    try:
        config = parse_args(argv)
        detector = AnomalyDetector.load(config.model_path)
        model_version = model_version_for(config.model_path, detector)
        client = _make_client(config.client_id)
        service = MqttInferenceService(detector, client, model_version=model_version, config=config)
        LOGGER.info("Loaded model %s with feature schema %s", model_version, detector.metadata["feature_schema_version"])
        service.run()
        return 0
    except KeyboardInterrupt:
        LOGGER.info("Inference service interrupted")
        if service is not None:
            service.close()
        return 0
    except (ConnectionError, OSError, ValueError) as exc:
        LOGGER.error("Inference service stopped: %s", exc)
        if service is not None:
            service.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
