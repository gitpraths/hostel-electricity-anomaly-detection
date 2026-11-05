"""Integration checks for the Node-RED dashboard function in the exported flow.

The tests run the actual Function-node source under Node.js with an isolated
in-memory flow context. They do not connect to or modify a Node-RED runtime.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FLOW_PATH = REPOSITORY_ROOT / "node-red" / "hostel-electricity-dashboard.json"
FUNCTION_ID = "79f06a994f154f3e"
READING_TOPIC = "hostel/v1/readings/hostel-a/meter-1"
PREDICTION_TOPIC = "hostel/v1/predictions/hostel-a/meter-1"

NODE_HARNESS = r"""
const fs = require('fs');
const nodes = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const functionNode = nodes.find(node => node.id === '79f06a994f154f3e');
if (!functionNode) throw new Error('Dashboard Function node not found');
const invoke = new Function('msg', 'flow', 'node', 'Buffer', functionNode.func);
const state = new Map();
const flow = {get:key => state.get(key), set:(key,value) => state.set(key,value)};
const warnings = [];
const node = {warn:message => warnings.push(message)};
const messages = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = messages.map(message => invoke(message, flow, node, Buffer));
process.stdout.write(JSON.stringify({
  outputs,
  recent:state.get('dashboard_recent_anomalies') || [],
  currentReadingId:state.get('dashboard_current_reading_id') || null,
  warnings
}));
"""


@pytest.fixture(scope="module")
def node_binary() -> str:
    binary = shutil.which("node")
    if binary is None:
        pytest.skip("Node.js is required to exercise the Node-RED Function node.")
    return binary


def event_id(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def reading(number: int, start: datetime | None = None) -> dict:
    start = start or datetime(2012, 7, 15)
    timestamp = start + timedelta(minutes=15 * (number - 1))
    second = timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second
    return {
        "schema_version": "2.0",
        "event_id": event_id(number),
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "date": timestamp.date().isoformat(),
        "time_of_day": timestamp.time().isoformat(timespec="seconds"),
        "interval_start_second": second,
        "hour": timestamp.hour,
        "site_id": "hostel-a",
        "meter_id": "meter-1",
        "interval_seconds": 900,
        "powerallphases_mean_w": 123.456,
        "powerallphases_max_w": 140.0,
        "powerallphases_std_w": 3.2,
        "occupancy_fraction": None,
        "source": "eco_household_1_historical_replay",
    }


def prediction(number: int, source_number: int, *, anomaly: bool = True, **overrides) -> dict:
    source = reading(source_number)
    return {
        "schema_version": "1.0",
        "event_id": event_id(1000 + number),
        "source_event_id": source["event_id"],
        "timestamp": source["timestamp"],
        "site_id": source["site_id"],
        "meter_id": source["meter_id"],
        "model_version": "test-model",
        "feature_schema_version": "1.0.0",
        "model_variant": "with_occupancy",
        "anomaly": anomaly,
        "score": 0.912345,
        "threshold": 0.700001,
        "robust_anomaly": False,
        "robust_score": 0.123456,
        "explanation": f"review candidate {number}",
        **overrides,
    }


def as_message(topic: str, payload: dict) -> dict:
    return {"topic": topic, "payload": payload}


def run_function(node_binary: str, messages: list[dict]) -> dict:
    completed = subprocess.run(
        [node_binary, "-e", NODE_HARNESS, str(FLOW_PATH)],
        input=json.dumps(messages),
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    return json.loads(completed.stdout)


def test_normal_prediction_does_not_enter_anomaly_table(node_binary: str) -> None:
    result = run_function(
        node_binary,
        [
            as_message(READING_TOPIC, reading(1)),
            as_message(
                PREDICTION_TOPIC,
                prediction(1, 1, anomaly=False, robust_anomaly=True),
            ),
        ],
    )
    assert result["outputs"][1][8]["payload"] == []
    assert result["recent"] == []


def test_linked_anomaly_row_has_correlated_source_and_display_fields(node_binary: str) -> None:
    pred = prediction(1, 1)
    result = run_function(
        node_binary,
        [as_message(READING_TOPIC, reading(1)), as_message(PREDICTION_TOPIC, pred)],
    )
    assert len(result["recent"]) == 1
    row = result["recent"][0]
    assert row == {
        "event_id": pred["event_id"],
        "source_event_id": pred["source_event_id"],
        "timestamp": pred["timestamp"],
        "site_id": pred["site_id"],
        "meter_id": pred["meter_id"],
        "score": "0.9123",
        "threshold": "0.7000",
        "model_variant": "with_occupancy",
        "explanation": "review candidate 1",
    }


def test_unmatched_or_timestamp_mismatched_anomalies_are_not_listed(node_binary: str) -> None:
    unmatched = prediction(1, 1)
    mismatch = prediction(2, 2, timestamp="2012-07-15T12:00:00")
    result = run_function(
        node_binary,
        [
            as_message(PREDICTION_TOPIC, unmatched),
            as_message(READING_TOPIC, reading(2)),
            as_message(PREDICTION_TOPIC, mismatch),
        ],
    )
    assert all(output[8]["payload"] == [] for output in result["outputs"])
    assert result["recent"] == []


def test_duplicate_prediction_deliveries_do_not_duplicate_an_event(node_binary: str) -> None:
    pred = prediction(1, 1)
    regenerated = prediction(2, 1)
    result = run_function(
        node_binary,
        [
            as_message(READING_TOPIC, reading(1)),
            as_message(PREDICTION_TOPIC, pred),
            as_message(PREDICTION_TOPIC, pred),
            as_message(PREDICTION_TOPIC, regenerated),
        ],
    )
    assert len(result["recent"]) == 1
    assert result["recent"][0]["source_event_id"] == reading(1)["event_id"]


def test_out_of_order_anomaly_waits_for_its_reading_to_correlate(node_binary: str) -> None:
    pred = prediction(1, 1)
    result = run_function(
        node_binary,
        [as_message(PREDICTION_TOPIC, pred), as_message(READING_TOPIC, reading(1))],
    )
    assert result["outputs"][0][8]["payload"] == []
    assert len(result["outputs"][1][8]["payload"]) == 1
    assert result["recent"][0]["source_event_id"] == reading(1)["event_id"]


def test_anomaly_table_keeps_only_latest_twenty_correlated_events(node_binary: str) -> None:
    messages = []
    for number in range(1, 22):
        messages.append(as_message(READING_TOPIC, reading(number)))
        messages.append(as_message(PREDICTION_TOPIC, prediction(number, number)))
    result = run_function(node_binary, messages)
    assert len(result["recent"]) == 20
    assert result["recent"][0]["source_event_id"] == reading(21)["event_id"]
    assert result["recent"][-1]["source_event_id"] == reading(2)["event_id"]


def test_new_linked_anomaly_updates_the_table_in_newest_first_order(node_binary: str) -> None:
    messages = []
    for number in (1, 2):
        messages.extend(
            [
                as_message(READING_TOPIC, reading(number)),
                as_message(PREDICTION_TOPIC, prediction(number, number)),
            ]
        )
    result = run_function(node_binary, messages)
    assert [row["source_event_id"] for row in result["recent"]] == [
        reading(2)["event_id"],
        reading(1)["event_id"],
    ]
    assert len(result["outputs"][-1][8]["payload"]) == 2


def test_ten_interval_chronological_replay_leaves_final_reading_and_prediction_visible(
    node_binary: str,
) -> None:
    """Regression for the observed 00:00 first-row sticking in the live dashboard."""
    means = [63.693534, 83.670772, 63.018952, 71.191698, 142.448114,
             103.964622, 146.616123, 99.956022, 55.819847, 78.396089]
    maxima = [125.868, 84.858, 83.783, 961.223, 145.694,
              140.045, 249.007, 190.778, 84.008, 146.700]
    deviations = [15.554639, 0.386995, 14.239270, 47.484068, 2.085156,
                  9.598319, 48.356621, 31.511109, 8.606968, 24.830705]
    scores = [0.419896, 0.427559, 0.420361, 0.483783, 0.421366,
              0.402161, 0.438237, 0.416938, 0.424777, 0.404265]
    messages = []
    for number in range(1, 11):
        item = reading(number)
        item.update(
            powerallphases_mean_w=means[number - 1],
            powerallphases_max_w=maxima[number - 1],
            powerallphases_std_w=deviations[number - 1],
        )
        result = prediction(
            number,
            number,
            anomaly=False,
            score=scores[number - 1],
            threshold=0.589912,
        )
        messages.extend(
            [
                as_message(READING_TOPIC, item),
                as_message(PREDICTION_TOPIC, result),
            ]
        )

    result = run_function(node_binary, messages)
    final_reading = reading(10)
    reading_outputs = result["outputs"][::2]
    assert len(reading_outputs) == 10
    assert reading_outputs[0][0]["payload"] == 63.69
    assert reading_outputs[-1][0]["payload"] == 78.40
    assert reading_outputs[-1][9]["payload"] == "78.40 W"
    assert reading_outputs[-1][1]["payload"] == {
        "x": "2012-07-15T02:15:00",
        "y": 78.40,
    }
    assert reading_outputs[-1][2]["payload"] == "146.70 W"
    assert reading_outputs[-1][3]["payload"] == "24.83 W"
    assert result["currentReadingId"] == final_reading["event_id"]
    assert result["outputs"][-1][5]["payload"] == "NORMAL"
    assert "0.4043" in result["outputs"][-1][6]["payload"]
    assert result["recent"] == []
    assert result["warnings"] == []
