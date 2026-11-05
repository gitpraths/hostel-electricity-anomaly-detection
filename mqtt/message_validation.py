"""Validate MQTT message envelopes before passing exact contracts to storage."""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime
from typing import Any

READING_SCHEMA_VERSION = "2.0"
PREDICTION_SCHEMA_VERSION = "1.0"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class InvalidMessage(ValueError):
    """Raised when a topic or MQTT payload violates its documented contract."""


def _topic_ids(topic: str, kind: str) -> tuple[str, str]:
    parts = topic.split("/")
    expected_prefix = ["hostel", "v1", kind]
    if len(parts) != 5 or parts[:3] != expected_prefix:
        raise InvalidMessage(f"Unexpected {kind} topic {topic!r}.")
    site_id, meter_id = parts[3:]
    if not IDENTIFIER_RE.fullmatch(site_id) or not IDENTIFIER_RE.fullmatch(meter_id):
        raise InvalidMessage("Topic site_id and meter_id must be URL-safe identifiers.")
    return site_id, meter_id


def _identifier(payload: dict[str, Any], key: str, topic_value: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise InvalidMessage(f"{key} must be a URL-safe identifier.")
    if value != topic_value:
        raise InvalidMessage(f"Payload {key} does not match the topic.")
    return value


def _uuid(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise InvalidMessage(f"{key} must be a UUID string.")
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidMessage(f"{key} must be a UUID string.") from exc
    return value


def _number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidMessage(f"{key} must be a JSON number.")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidMessage(f"{key} must be finite.")
    return number


def _timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidMessage("timestamp must be a timezone-naive ISO timestamp string.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise InvalidMessage("timestamp must be timezone-naive YYYY-MM-DDTHH:MM:SS.") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S") != value:
        raise InvalidMessage("timestamp must use canonical YYYY-MM-DDTHH:MM:SS formatting.")
    return value


def validate_reading(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate schema 2.0, preserving field names and nullable occupancy."""
    site_topic, meter_topic = _topic_ids(topic, "readings")
    if payload.get("schema_version") != READING_SCHEMA_VERSION:
        raise InvalidMessage(
            f"Unsupported reading schema_version {payload.get('schema_version')!r}; expected 2.0."
        )
    event_id = _uuid(payload, "event_id")
    site_id = _identifier(payload, "site_id", site_topic)
    meter_id = _identifier(payload, "meter_id", meter_topic)
    timestamp = _timestamp(payload.get("timestamp"))

    date = payload.get("date")
    time_of_day = payload.get("time_of_day")
    if not isinstance(date, str) or not isinstance(time_of_day, str):
        raise InvalidMessage("date and time_of_day must be strings.")
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        parsed_time = datetime.strptime(time_of_day, "%H:%M:%S").time()
        parsed_timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise InvalidMessage("date or time_of_day has an invalid format.") from exc
    if (parsed_timestamp.date(), parsed_timestamp.time()) != (parsed_date, parsed_time):
        raise InvalidMessage("timestamp must agree with date and time_of_day.")

    interval_start = _number(payload, "interval_start_second")
    hour = _number(payload, "hour")
    interval_seconds = _number(payload, "interval_seconds")
    if not interval_start.is_integer() or not 0 <= interval_start < 86_400:
        raise InvalidMessage("interval_start_second must be a whole second in [0, 86400).")
    if not hour.is_integer() or int(hour) != int(interval_start) // 3600:
        raise InvalidMessage("hour must match interval_start_second.")
    if not interval_seconds.is_integer() or interval_seconds <= 0:
        raise InvalidMessage("interval_seconds must be a positive integer.")
    expected_time = (
        f"{int(interval_start) // 3600:02d}:"
        f"{(int(interval_start) // 60) % 60:02d}:"
        f"{int(interval_start) % 60:02d}"
    )
    if time_of_day != expected_time:
        raise InvalidMessage("time_of_day must match interval_start_second.")

    power_mean = _number(payload, "powerallphases_mean_w")
    power_max = _number(payload, "powerallphases_max_w")
    power_std = _number(payload, "powerallphases_std_w")
    occupancy_value = payload.get("occupancy_fraction")
    occupancy = None if occupancy_value is None else _number(payload, "occupancy_fraction")
    if occupancy is not None and not 0 <= occupancy <= 1:
        raise InvalidMessage("occupancy_fraction must be in [0, 1] or null.")
    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise InvalidMessage("source must be a non-empty string.")

    return {
        "event_id": event_id,
        "schema_version": READING_SCHEMA_VERSION,
        "timestamp": timestamp,
        "date": date,
        "time_of_day": time_of_day,
        "interval_start_second": int(interval_start),
        "hour": int(hour),
        "site_id": site_id,
        "meter_id": meter_id,
        "interval_seconds": int(interval_seconds),
        "powerallphases_mean_w": power_mean,
        "powerallphases_max_w": power_max,
        "powerallphases_std_w": power_std,
        "occupancy_fraction": occupancy,
        "source": source,
    }


def validate_prediction(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the exact prediction contract emitted by mqtt.inference_service."""
    site_topic, meter_topic = _topic_ids(topic, "predictions")
    if payload.get("schema_version") != PREDICTION_SCHEMA_VERSION:
        raise InvalidMessage(
            f"Unsupported prediction schema_version {payload.get('schema_version')!r}; expected 1.0."
        )
    event_id = _uuid(payload, "event_id")
    source_event_id = _uuid(payload, "source_event_id")
    site_id = _identifier(payload, "site_id", site_topic)
    meter_id = _identifier(payload, "meter_id", meter_topic)
    timestamp = _timestamp(payload.get("timestamp"))
    model_version = payload.get("model_version")
    feature_schema_version = payload.get("feature_schema_version")
    explanation = payload.get("explanation")
    if not isinstance(model_version, str) or not model_version:
        raise InvalidMessage("model_version must be a non-empty string.")
    if not isinstance(feature_schema_version, str) or not feature_schema_version:
        raise InvalidMessage("feature_schema_version must be a non-empty string.")
    if not isinstance(explanation, str):
        raise InvalidMessage("explanation must be a string.")
    for key in ("anomaly", "robust_anomaly"):
        if not isinstance(payload.get(key), bool):
            raise InvalidMessage(f"{key} must be a JSON boolean.")
    model_variant = payload.get("model_variant")
    if model_variant not in {"with_occupancy", "without_occupancy"}:
        raise InvalidMessage("model_variant must be with_occupancy or without_occupancy.")

    return {
        "event_id": event_id,
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "source_event_id": source_event_id,
        "timestamp": timestamp,
        "site_id": site_id,
        "meter_id": meter_id,
        "model_version": model_version,
        "feature_schema_version": feature_schema_version,
        "anomaly": payload["anomaly"],
        "score": _number(payload, "score"),
        "threshold": _number(payload, "threshold"),
        "model_variant": model_variant,
        "robust_anomaly": payload["robust_anomaly"],
        "robust_score": _number(payload, "robust_score"),
        "explanation": explanation,
    }
