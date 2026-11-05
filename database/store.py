"""Transactional SQLite storage for versioned MQTT reading/prediction events."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "hostel_electricity.sqlite3"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS readings (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (schema_version = '2.0'),
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    interval_start_second INTEGER NOT NULL CHECK (interval_start_second BETWEEN 0 AND 86399),
    hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    site_id TEXT NOT NULL,
    meter_id TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL CHECK (interval_seconds > 0),
    powerallphases_mean_w REAL NOT NULL,
    powerallphases_max_w REAL NOT NULL,
    powerallphases_std_w REAL NOT NULL,
    occupancy_fraction REAL CHECK (occupancy_fraction IS NULL OR occupancy_fraction BETWEEN 0 AND 1),
    source TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
    source_event_id TEXT NOT NULL,
    source_reading_event_id TEXT REFERENCES readings(event_id) ON UPDATE CASCADE ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    site_id TEXT NOT NULL,
    meter_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_schema_version TEXT NOT NULL,
    anomaly INTEGER NOT NULL CHECK (anomaly IN (0, 1)),
    score REAL NOT NULL,
    threshold REAL NOT NULL,
    model_variant TEXT NOT NULL CHECK (model_variant IN ('with_occupancy', 'without_occupancy')),
    robust_anomaly INTEGER NOT NULL CHECK (robust_anomaly IN (0, 1)),
    robust_score REAL NOT NULL,
    explanation TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_readings_site_meter_timestamp
    ON readings(site_id, meter_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_received_at ON readings(received_at);
CREATE INDEX IF NOT EXISTS idx_predictions_source_event_id ON predictions(source_event_id);
CREATE INDEX IF NOT EXISTS idx_predictions_source_reading_event_id
    ON predictions(source_reading_event_id);
CREATE INDEX IF NOT EXISTS idx_predictions_site_meter_timestamp
    ON predictions(site_id, meter_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_predictions_anomaly_received_at
    ON predictions(anomaly, received_at);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class StorageConflictError(RuntimeError):
    """Raised when an existing source reading contradicts prediction identifiers."""


class SQLiteStore:
    """One thread-safe connection with explicit transactions and idempotent inserts."""

    def __init__(self, path: str | Path = DEFAULT_DATABASE_PATH, *, timeout_seconds: float = 5.0) -> None:
        self.path = str(Path(path).expanduser()) if str(path) != ":memory:" else ":memory:"
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            self.path,
            timeout=timeout_seconds,
            check_same_thread=False,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        if self.path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def initialize(self) -> None:
        """Create the schema idempotently; keep DDL in the database layer."""
        with self._lock:
            self.connection.executescript(SCHEMA_SQL)
            self.connection.execute("PRAGMA user_version = 1")

    @staticmethod
    def _reading_values(message: dict[str, Any], received_at: str) -> tuple[Any, ...]:
        return (
            message["event_id"], message["schema_version"], message["timestamp"],
            message["date"], message["time_of_day"], message["interval_start_second"],
            message["hour"], message["site_id"], message["meter_id"],
            message["interval_seconds"], message["powerallphases_mean_w"],
            message["powerallphases_max_w"], message["powerallphases_std_w"],
            message["occupancy_fraction"], message["source"], received_at,
        )

    @staticmethod
    def _prediction_values(
        message: dict[str, Any], source_reading_event_id: str | None, received_at: str
    ) -> tuple[Any, ...]:
        return (
            message["event_id"], message["schema_version"], message["source_event_id"],
            source_reading_event_id, message["timestamp"], message["site_id"],
            message["meter_id"], message["model_version"], message["feature_schema_version"],
            int(message["anomaly"]), message["score"], message["threshold"],
            message["model_variant"], int(message["robust_anomaly"]),
            message["robust_score"], message["explanation"], received_at,
        )

    def insert_reading(self, message: dict[str, Any], *, received_at: str | None = None) -> bool:
        """Insert once; return False for an existing event without overwriting it."""
        received = received_at or utc_now_iso()
        sql = """INSERT INTO readings (
            event_id, schema_version, timestamp, date, time_of_day,
            interval_start_second, hour, site_id, meter_id, interval_seconds,
            powerallphases_mean_w, powerallphases_max_w, powerallphases_std_w,
            occupancy_fraction, source, received_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO NOTHING"""
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = self.connection.execute(sql, self._reading_values(message, received))
                inserted = cursor.rowcount == 1
                if inserted:
                    # Resolve out-of-order predictions only when event and identifiers agree.
                    self.connection.execute(
                        """UPDATE predictions SET source_reading_event_id = ?
                           WHERE source_event_id = ? AND site_id = ? AND meter_id = ?
                             AND source_reading_event_id IS NULL""",
                        (message["event_id"], message["event_id"], message["site_id"], message["meter_id"]),
                    )
                self.connection.commit()
                return inserted
            except Exception:
                self.connection.rollback()
                raise

    def insert_prediction(self, message: dict[str, Any], *, received_at: str | None = None) -> bool:
        """Insert prediction, preserving an unresolved source link until reading arrives."""
        received = received_at or utc_now_iso()
        sql = """INSERT INTO predictions (
            event_id, schema_version, source_event_id, source_reading_event_id,
            timestamp, site_id, meter_id, model_version, feature_schema_version,
            anomaly, score, threshold, model_variant, robust_anomaly, robust_score,
            explanation, received_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO NOTHING"""
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                source = self.connection.execute(
                    "SELECT event_id, site_id, meter_id FROM readings WHERE event_id = ?",
                    (message["source_event_id"],),
                ).fetchone()
                if source is not None and (
                    source["site_id"] != message["site_id"] or source["meter_id"] != message["meter_id"]
                ):
                    raise StorageConflictError(
                        "Prediction source reading exists but site_id/meter_id do not match."
                    )
                source_reading_event_id = None if source is None else source["event_id"]
                cursor = self.connection.execute(
                    sql, self._prediction_values(message, source_reading_event_id, received)
                )
                inserted = cursor.rowcount == 1
                self.connection.commit()
                return inserted
            except Exception:
                self.connection.rollback()
                raise

    def get_reading(self, event_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute(
                "SELECT * FROM readings WHERE event_id = ?", (event_id,)
            ).fetchone()

    def get_prediction(self, event_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute(
                "SELECT * FROM predictions WHERE event_id = ?", (event_id,)
            ).fetchone()

    def counts(self) -> tuple[int, int]:
        with self._lock:
            readings = self.connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            predictions = self.connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            return int(readings), int(predictions)

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
