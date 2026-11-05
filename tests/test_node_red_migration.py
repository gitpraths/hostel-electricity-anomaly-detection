"""Offline regression tests for the backup-first Node-RED flow migration."""

from __future__ import annotations

from pathlib import Path

from scripts.migrate_node_red_dashboard import apply_candidate, read_json_array


ROOT = Path(__file__).resolve().parents[1]
POLISHED = ROOT / "node-red" / "hostel-electricity-dashboard.json"
BASELINE = ROOT / "node-red" / "hostel-electricity-dashboard.backup.json"
FUNCTION_ID = "79f06a994f154f3e"


def test_migration_transforms_reviewed_baseline_function_to_polished_function() -> None:
    baseline = read_json_array(BASELINE)
    polished = read_json_array(POLISHED)
    old_function = next(node["func"] for node in baseline if node.get("id") == FUNCTION_ID)
    desired_function = next(node["func"] for node in polished if node.get("id") == FUNCTION_ID)

    from scripts.migrate_node_red_dashboard import patch_function

    assert patch_function(old_function, desired_function) == desired_function


def test_migration_is_idempotent_and_adds_only_reviewed_nodes() -> None:
    baseline = read_json_array(BASELINE)
    polished = read_json_array(POLISHED)
    before = baseline + [{"id": "flow-1-test-tab", "type": "tab", "label": "Flow 1"}]

    first, first_report = apply_candidate(before, polished, baseline)
    second, second_report = apply_candidate(first, polished, baseline)

    assert second == first
    assert first_report["summary"]["added"] == 3
    assert first_report["summary"]["removed"] == 0
    assert second_report["summary"]["added"] == 0
    assert second_report["summary"]["changed"] == 0
    assert second_report["summary"]["removed"] == 0
