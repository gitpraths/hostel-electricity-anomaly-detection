"""Receive versioned MQTT readings/predictions and persist them on Computer 1."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import paho.mqtt.client as mqtt

from database.store import DEFAULT_DATABASE_PATH, SQLiteStore, StorageConflictError
from mqtt.message_validation import InvalidMessage, validate_prediction, validate_reading

READINGS_TOPIC = "hostel/v1/readings/+/+"
PREDICTIONS_TOPIC = "hostel/v1/predictions/+/+"
QOS = 1
LOGGER = logging.getLogger("mqtt.storage")


@dataclass(frozen=True)
class StorageServiceConfig:
    database_path: Path = DEFAULT_DATABASE_PATH
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    client_id: str = "hostel-storage-service"
    keepalive_seconds: int = 30
    connect_timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not 1 <= self.broker_port <= 65535:
            raise ValueError("Broker port must be between 1 and 65535.")

    @classmethod
    def from_environment(cls) -> "StorageServiceConfig":
        return cls(
            database_path=Path(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))).expanduser(),
            broker_host=os.getenv("STORAGE_MQTT_HOST", "127.0.0.1"),
            broker_port=int(os.getenv("STORAGE_MQTT_PORT", "1883")),
            client_id=os.getenv("STORAGE_MQTT_CLIENT_ID", "hostel-storage-service"),
            keepalive_seconds=int(os.getenv("MQTT_KEEPALIVE_SECONDS", "60")),
        )


class MqttStorageService:
    """MQTT callbacks validate, transact, then acknowledge QoS 1 deliveries."""

    def __init__(self, store: SQLiteStore, client: mqtt.Client, config: StorageServiceConfig) -> None:
        self.store = store
        self.client = client
        self.config = config
        self.connected = threading.Event()
        self.stop_requested = threading.Event()
        self.stored_readings = 0
        self.stored_predictions = 0
        self.duplicates = 0
        self.invalid_messages = 0
        self.database_failures = 0
        self._closed = False
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        value = getattr(reason_code, "value", reason_code)
        try:
            accepted = int(value) == 0
        except (TypeError, ValueError):
            accepted = False
        if not accepted:
            LOGGER.error("MQTT connection refused (reason code %s)", reason_code)
            return
        for topic in (READINGS_TOPIC, PREDICTIONS_TOPIC):
            result = client.subscribe(topic, qos=QOS)
            rc = result[0] if isinstance(result, tuple) else result
            if rc != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.error("Subscription failed for %s (error code %s)", topic, rc)
                return
        self.connected.set()
        LOGGER.info("Subscribed QoS 1 to %s and %s", READINGS_TOPIC, PREDICTIONS_TOPIC)

    def on_disconnect(self, client, userdata, disconnect_flags=None, reason_code=None, properties=None) -> None:
        self.connected.clear()
        value = getattr(reason_code, "value", reason_code)
        if value not in (None, 0):
            LOGGER.warning("MQTT disconnected (reason code %s)", reason_code)

    def _ack(self, message) -> bool:
        if int(getattr(message, "qos", 0)) == 0:
            return True
        ack = getattr(self.client, "ack", None)
        if ack is None:
            LOGGER.error("Client was not created with manual acknowledgements; refusing to claim durable storage")
            return False
        try:
            result = ack(message.mid, message.qos)
        except Exception:
            LOGGER.exception("Failed to acknowledge MQTT message mid=%s", message.mid)
            return False
        if result != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("MQTT acknowledgement failed for mid=%s (error code %s)", message.mid, result)
            return False
        return True

    def on_message(self, client, userdata, message) -> None:
        try:
            decoded = message.payload.decode("utf-8")
            payload = json.loads(decoded)
            if not isinstance(payload, dict):
                raise InvalidMessage("Message JSON must be an object.")
            if message.topic.startswith("hostel/v1/readings/"):
                record = validate_reading(message.topic, payload)
                inserted = self.store.insert_reading(record)
                if inserted:
                    self.stored_readings += 1
                    LOGGER.info("Stored reading event %s", record["event_id"])
                else:
                    self.duplicates += 1
                    LOGGER.info("Duplicate reading event %s; existing row preserved", record["event_id"])
            elif message.topic.startswith("hostel/v1/predictions/"):
                record = validate_prediction(message.topic, payload)
                inserted = self.store.insert_prediction(record)
                if inserted:
                    self.stored_predictions += 1
                    if self.store.get_prediction(record["event_id"])["source_reading_event_id"] is None:
                        LOGGER.info(
                            "Stored prediction %s with unresolved source_event_id %s",
                            record["event_id"], record["source_event_id"],
                        )
                    else:
                        LOGGER.info("Stored prediction event %s", record["event_id"])
                else:
                    self.duplicates += 1
                    LOGGER.info("Duplicate prediction event %s; existing row preserved", record["event_id"])
            else:
                raise InvalidMessage(f"Unsupported MQTT topic {message.topic!r}.")
        except (UnicodeDecodeError, json.JSONDecodeError, InvalidMessage) as exc:
            self.invalid_messages += 1
            LOGGER.warning("Rejected malformed MQTT message on %s: %s", message.topic, exc)
            # Invalid events are intentionally acknowledged after logging to avoid poison-message loops.
            self._ack(message)
            return
        except StorageConflictError as exc:
            self.invalid_messages += 1
            LOGGER.error("Rejected inconsistent prediction on %s: %s", message.topic, exc)
            self._ack(message)
            return
        except (sqlite3.Error, OSError):
            self.database_failures += 1
            LOGGER.exception(
                "Database write failed for MQTT message mid=%s; leaving QoS message unacknowledged",
                getattr(message, "mid", "unknown"),
            )
            # With manual_ack and a persistent MQTT session, the broker can redeliver it.
            return
        except Exception:
            self.database_failures += 1
            LOGGER.exception(
                "Unexpected storage failure for MQTT message mid=%s; not acknowledging",
                getattr(message, "mid", "unknown"),
            )
            return

        self._ack(message)

    def run(self) -> None:
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
                f"Could not subscribe to storage topics through {self.config.broker_host}:"
                f"{self.config.broker_port} within {self.config.connect_timeout_seconds:g} seconds."
            )
        LOGGER.info("Storage service ready; SQLite path is %s", self.store.path)
        try:
            while not self.stop_requested.wait(0.25):
                pass
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.stop_requested.set()
        try:
            self.client.disconnect()
        finally:
            try:
                self.client.loop_stop()
            finally:
                self.store.close()


def _make_client(client_id: str) -> mqtt.Client:
    common = {
        "client_id": client_id,
        "protocol": mqtt.MQTTv311,
        "clean_session": False,
        "manual_ack": True,
    }
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, **common)
    else:  # pragma: no cover - compatibility with older Paho versions
        client = mqtt.Client(**common)
    username = os.getenv("MQTT_USERNAME", "")
    password = os.getenv("MQTT_PASSWORD", "")
    if username:
        client.username_pw_set(username, password or None)
    return client


def parse_args(argv: Iterable[str] | None = None) -> StorageServiceConfig:
    defaults = StorageServiceConfig.from_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-path", type=Path, default=defaults.database_path)
    parser.add_argument("--broker-host", default=defaults.broker_host)
    parser.add_argument("--broker-port", type=int, default=defaults.broker_port)
    parser.add_argument("--client-id", default=defaults.client_id)
    args = parser.parse_args(argv)
    return StorageServiceConfig(
        database_path=args.database_path,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        client_id=args.client_id,
        keepalive_seconds=defaults.keepalive_seconds,
        connect_timeout_seconds=defaults.connect_timeout_seconds,
    )


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store: SQLiteStore | None = None
    service: MqttStorageService | None = None
    try:
        config = parse_args(argv)
        store = SQLiteStore(config.database_path)
        client = _make_client(config.client_id)
        service = MqttStorageService(store, client, config)
        LOGGER.info(
            "Starting SQLite MQTT receiver at %s:%d; database=%s",
            config.broker_host, config.broker_port, config.database_path,
        )
        service.run()
        return 0
    except KeyboardInterrupt:
        LOGGER.info("Storage service interrupted")
        return 0
    except (ConnectionError, OSError, sqlite3.Error, ValueError) as exc:
        LOGGER.error("Storage service stopped: %s", exc)
        return 1
    finally:
        if service is not None:
            service.close()
        elif store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
