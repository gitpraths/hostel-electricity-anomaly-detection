"""Tests for read-only local readiness checks."""

from __future__ import annotations

import sqlite3

from scripts import check_local_pipeline as health


def test_check_file_reports_missing_and_present_paths(tmp_path):
    path = tmp_path / "artifact.bin"
    assert not health.check_file("artifact", path).passed
    path.write_bytes(b"ok")
    result = health.check_file("artifact", path)
    assert result.passed
    assert str(path) in result.detail


def test_mqtt_check_performs_connect_only_and_disconnects(monkeypatch):
    state = {"published": 0, "disconnected": False}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, host, port, keepalive):
            assert (host, port) == ("127.0.0.1", 1883)

        def loop_start(self):
            self.on_connect(self, None, {}, 0, None)
            return 0

        def disconnect(self):
            state["disconnected"] = True

        def loop_stop(self):
            pass

        def publish(self, *args, **kwargs):
            state["published"] += 1

    monkeypatch.setattr(health.mqtt, "Client", FakeClient)
    result = health.check_mqtt("127.0.0.1", 1883, timeout=0.1)
    assert result.passed
    assert "no publish" in result.detail
    assert state == {"published": 0, "disconnected": True}


def test_mqtt_check_reports_connect_timeout(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            pass

        def loop_start(self):
            return 0

        def disconnect(self):
            pass

        def loop_stop(self):
            pass

    monkeypatch.setattr(health.mqtt, "Client", FakeClient)
    result = health.check_mqtt("127.0.0.1", 1883, timeout=0.001)
    assert not result.passed
    assert "CONNACK" in result.detail


def test_dashboard_check_accepts_success_and_reports_unavailable(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    monkeypatch.setattr(health, "urlopen", lambda *_args, **_kwargs: Response())
    assert health.check_dashboard("http://127.0.0.1:1880").passed

    def unavailable(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(health, "urlopen", unavailable)
    result = health.check_dashboard("http://127.0.0.1:1880")
    assert not result.passed
    assert "connection refused" in result.detail


def test_sqlite_check_is_read_only_and_checks_integrity_and_tables(tmp_path):
    path = tmp_path / "ready.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE readings (event_id TEXT PRIMARY KEY);"
        "CREATE TABLE predictions (event_id TEXT PRIMARY KEY);"
        "INSERT INTO readings VALUES ('r1');"
        "INSERT INTO predictions VALUES ('p1');"
    )
    connection.commit()
    connection.close()

    result = health.check_sqlite(path)
    assert result.passed
    assert "readings=1, predictions=1" in result.detail
    assert "foreign_key_check ok" in result.detail
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 1
    connection.close()


def test_sqlite_check_rejects_missing_schema(tmp_path):
    path = tmp_path / "empty.sqlite3"
    sqlite3.connect(path).close()
    result = health.check_sqlite(path)
    assert not result.passed
    assert "tables are missing" in result.detail


def test_environment_can_configure_dashboard_url(monkeypatch):
    monkeypatch.setenv("NODE_RED_DASHBOARD_URL", "http://127.0.0.1:2880/dashboard")
    args = health.parse_args([])
    assert args.dashboard_url == "http://127.0.0.1:2880/dashboard"
