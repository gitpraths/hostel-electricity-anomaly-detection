"""Read-only readiness checks for the single-machine local demo."""

from __future__ import annotations

import argparse
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

import paho.mqtt.client as mqtt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data/processed/eco_household_1_15min.parquet"
DEFAULT_MODEL = ROOT / "models/eco_household_1_iforest.joblib"
DEFAULT_DATABASE = ROOT / "database/hostel_electricity.sqlite3"
DEFAULT_DASHBOARD_URL = "http://127.0.0.1:1880/dashboard/hostel-electricity"


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_file(name: str, path: Path) -> CheckResult:
    path = Path(path).expanduser()
    if path.is_file():
        return CheckResult(name, True, f"present ({path})")
    return CheckResult(name, False, f"missing file: {path}")


def check_mqtt(host: str, port: int, timeout: float = 3.0) -> CheckResult:
    """Complete an MQTT CONNECT/CONNACK handshake; publish no messages."""
    connected = threading.Event()
    result_code: list[int] = []
    client_id = f"hostel-health-{uuid.uuid4().hex[:12]}"
    try:
        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )
        else:  # pragma: no cover - compatibility with Paho 1.x
            client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

        username = os.getenv("MQTT_USERNAME", "")
        password = os.getenv("MQTT_PASSWORD", "")
        if username:
            client.username_pw_set(username, password or None)

        def on_connect(_client, _userdata, _flags, reason_code, *_extra) -> None:
            value = getattr(reason_code, "value", reason_code)
            try:
                result_code.append(int(value))
            except (TypeError, ValueError):
                result_code.append(1)
            connected.set()

        client.on_connect = on_connect
        client.connect(host, port, keepalive=5)
        loop_result = client.loop_start()
        if loop_result not in (None, mqtt.MQTT_ERR_SUCCESS):
            raise ConnectionError(f"MQTT network loop returned {loop_result}.")
        if not connected.wait(timeout):
            raise TimeoutError("MQTT CONNACK was not received before timeout.")
        if not result_code or result_code[0] != 0:
            raise ConnectionError(f"Broker rejected MQTT connection (reason {result_code}).")
        return CheckResult("Mosquitto MQTT", True, f"connected to {host}:{port}; no publish performed")
    except Exception as exc:
        return CheckResult("Mosquitto MQTT", False, f"{host}:{port}: {exc}")
    finally:
        if "client" in locals():
            try:
                client.disconnect()
            except Exception:
                pass
            try:
                client.loop_stop()
            except Exception:
                pass


def check_dashboard(url: str, timeout: float = 3.0) -> CheckResult:
    try:
        with urlopen(url, timeout=timeout) as response:
            status = int(response.status)
        return CheckResult(
            "Node-RED dashboard",
            200 <= status < 400,
            f"HTTP {status} at {url}" if 200 <= status < 400 else f"HTTP {status} at {url}",
        )
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return CheckResult("Node-RED dashboard", False, f"{url}: {exc}")


def check_sqlite(path: Path) -> CheckResult:
    path = Path(path).expanduser()
    if not path.is_file():
        return CheckResult("SQLite storage", False, f"database not created yet: {path}")
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0)
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if integrity != "ok":
            return CheckResult("SQLite storage", False, f"quick_check returned {integrity!r}")
        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_issues:
            return CheckResult(
                "SQLite storage",
                False,
                f"foreign_key_check found {len(foreign_key_issues)} violation(s)",
            )
        if not {"readings", "predictions"}.issubset(tables):
            return CheckResult("SQLite storage", False, "readings/predictions tables are missing")
        readings, predictions = connection.execute(
            "SELECT (SELECT COUNT(*) FROM readings), (SELECT COUNT(*) FROM predictions)"
        ).fetchone()
        return CheckResult(
            "SQLite storage",
            True,
            f"quick_check and foreign_key_check ok; readings={readings}, predictions={predictions}; opened read-only",
        )
    except (sqlite3.Error, OSError) as exc:
        return CheckResult("SQLite storage", False, str(exc))
    finally:
        if connection is not None:
            connection.close()


def build_checks(
    *, dataset: Path, model: Path, database: Path, broker_host: str, broker_port: int,
    dashboard_url: str, timeout: float,
) -> list[CheckResult]:
    return [
        check_file("Processed ECO Parquet", dataset),
        check_file("Model artifact", model),
        check_file("Model metadata sidecar", Path(model).with_suffix(".metadata.json")),
        check_mqtt(broker_host, broker_port, timeout),
        check_dashboard(dashboard_url, timeout),
        check_sqlite(database),
    ]


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(os.getenv("ECO_DATASET_PATH", DEFAULT_DATASET)))
    parser.add_argument("--model", type=Path, default=Path(os.getenv("ML_MODEL_PATH", DEFAULT_MODEL)))
    parser.add_argument("--database", type=Path, default=Path(os.getenv("DATABASE_PATH", DEFAULT_DATABASE)))
    parser.add_argument("--broker-host", default=os.getenv("ML_MQTT_HOST", "127.0.0.1"))
    parser.add_argument("--broker-port", type=int, default=int(os.getenv("ML_MQTT_PORT", "1883")))
    parser.add_argument("--dashboard-url", default=os.getenv("NODE_RED_DASHBOARD_URL", DEFAULT_DASHBOARD_URL))
    parser.add_argument("--timeout", type=float, default=3.0)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive.")
    results = build_checks(
        dataset=args.dataset,
        model=args.model,
        database=args.database,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        dashboard_url=args.dashboard_url,
        timeout=args.timeout,
    )
    for result in results:
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.name}: {result.detail}")
    print("NOTE  Confirm 'Inference service ready' and 'Storage service ready' in their terminals.")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
