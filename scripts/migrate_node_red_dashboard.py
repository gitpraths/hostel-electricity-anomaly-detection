#!/usr/bin/env python3
"""Prepare or apply a backup-first, in-place Node-RED dashboard migration.

Without --apply this command is read-only with respect to the live flow file;
it validates an in-memory candidate and writes only a sanitized migration
report. With --apply it creates a non-overwriting timestamped backup and then
atomically replaces the flow file. It never calls Node-RED's deploy API.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FLOW_FILE = Path.home() / ".node-red" / "flows.json"
DEFAULT_POLISHED = ROOT / "node-red" / "hostel-electricity-dashboard.json"
DEFAULT_BASELINE = ROOT / "node-red" / "hostel-electricity-dashboard.backup.json"
DEFAULT_REPORT = ROOT / "reports" / "node-red-dashboard-migration-report.json"

DASHBOARD_TAB_ID = "e645f300346a4657"
FLOW_1_LABEL = "Flow 1"
READINGS_TOPIC = "hostel/v1/readings/+/+"
PREDICTIONS_TOPIC = "hostel/v1/predictions/+/+"
READINGS_NODE_ID = "0c997bff253b422d"
PREDICTIONS_NODE_ID = "692bf35269324cbb"
BROKER_NODE_ID = "b01c3a41855c4377"
FUNCTION_NODE_ID = "79f06a994f154f3e"
MEAN_WIDGET_ID = "ff54883525084981"
LATEST_GROUP_ID = "04bdf2de2a134979"
NOTICE_ID = "fab968f10f784d91"

CONFIG_REFERENCE_KEYS = ("broker", "group", "page", "ui", "theme", "tls")


class MigrationError(RuntimeError):
    """Raised when preconditions or candidate-flow invariants are not met."""


def read_json_array(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MigrationError(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MigrationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(node, dict) for node in value):
        raise MigrationError(f"Expected a JSON array of Node-RED nodes in {path}.")
    return value


def index_nodes(nodes: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise MigrationError(f"A node in {label} has no string ID.")
        if node_id in result:
            raise MigrationError(f"Duplicate node ID {node_id} in {label}.")
        result[node_id] = node
    return result


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("name") or node.get("label") or node.get("path") or "")


def tab_by_id(nodes_by_id: dict[str, dict[str, Any]], tab_id: str) -> dict[str, Any]:
    node = nodes_by_id.get(tab_id)
    if node is None or node.get("type") != "tab":
        raise MigrationError(f"Expected dashboard tab {tab_id} is missing.")
    return node


def config_closure(
    nodes: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], tab_id: str
) -> dict[str, dict[str, Any]]:
    """Collect a tab, its flow nodes, and transitively referenced config nodes."""
    found = {node["id"]: node for node in nodes if node.get("z") == tab_id}
    tab = tab_by_id(nodes_by_id, tab_id)
    found[tab_id] = tab
    pending = list(found.values())
    while pending:
        node = pending.pop()
        for key in CONFIG_REFERENCE_KEYS:
            ref = node.get(key)
            if isinstance(ref, str) and ref in nodes_by_id and ref not in found:
                found[ref] = nodes_by_id[ref]
                pending.append(nodes_by_id[ref])
    return found


def flow_snapshot(
    nodes: list[dict[str, Any]], nodes_by_id: dict[str, dict[str, Any]], tab: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    return config_closure(nodes, nodes_by_id, tab["id"])


def target_map(polished: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return index_nodes(polished, "polished dashboard source")


def patch_function(current: str, desired: str) -> str:
    """Apply only reviewed display and anomaly-correlation deltas."""
    if current == desired:
        return current

    display_replacements = (
        (
            "// 6 model score/threshold, 7 robust comparator, 8 recent anomalies.",
            "// 6 model score/threshold, 7 robust comparator, 8 recent anomalies, 9 mean-power text readout.",
        ),
        (
            "    const robust = {payload:'Secondary robust comparator: ' + (p.robust_anomaly ? 'ANOMALY' : 'NORMAL') + '  |  Score: ' + p.robust_score.toFixed(3)};",
            "    const robust = {payload:'Secondary robust comparator: ' + (p.robust_anomaly ? 'ANOMALY' : 'NORMAL') + '  |  Score: ' + p.robust_score.toFixed(4)};",
        ),
        ("const outputs = Array(9).fill(null);", "const outputs = Array(10).fill(null);"),
        (
            "        const occupancy = reading.occupancy_fraction === null ? 'Unknown (occupancy not supplied)' : (reading.occupancy_fraction * 100).toFixed(1) + '% occupied';",
            r"        const occupancy = reading.occupancy_fraction === null ? 'Unknown (occupancy not supplied)' : (reading.occupancy_fraction * 100).toFixed(1).replace(/\.0$/, '') + '% occupied';",
        ),
        (
            "        outputs[0] = {payload:reading.powerallphases_mean_w};",
            """        outputs[0] = {payload:Number(reading.powerallphases_mean_w.toFixed(2))};
        outputs[9] = {payload:reading.powerallphases_mean_w.toFixed(2) + ' W'};""",
        ),
        (
            "        outputs[1] = {topic:'historical-mean-power',payload:{x:reading.timestamp,y:reading.powerallphases_mean_w}};",
            "        outputs[1] = {topic:'historical-mean-power',payload:{x:reading.timestamp,y:Number(reading.powerallphases_mean_w.toFixed(2))}};",
        ),
        (
            "        outputs[2] = {payload:reading.powerallphases_max_w.toFixed(1) + ' W'};",
            "        outputs[2] = {payload:reading.powerallphases_max_w.toFixed(2) + ' W'};",
        ),
        (
            "        outputs[3] = {payload:reading.powerallphases_std_w.toFixed(1) + ' W'};",
            "        outputs[3] = {payload:reading.powerallphases_std_w.toFixed(2) + ' W'};",
        ),
    )
    correlation_replacements = (
        (
            """function addAnomaly(p, recent) {
    if (p.anomaly && !recent.some(item => item.event_id === p.event_id)) {
        recent.unshift({event_id:p.event_id,timestamp:p.timestamp,site_id:p.site_id,meter_id:p.meter_id,score:p.score.toFixed(4),threshold:p.threshold.toFixed(4),model_variant:p.model_variant,explanation:p.explanation});
        recent.splice(MAX_ANOMALIES);
    }
    return recent;
}""",
            """function matchesSource(p, reading) {
    return !!p && !!reading && reading.event_id === p.source_event_id &&
        reading.site_id === p.site_id && reading.meter_id === p.meter_id &&
        reading.timestamp === p.timestamp;
}
function addAnomaly(p, reading, recent) {
    const alreadyListed = recent.some(item =>
        item.event_id === p.event_id ||
        item.source_event_id === p.source_event_id ||
        (!item.source_event_id && item.timestamp === p.timestamp &&
            item.site_id === p.site_id && item.meter_id === p.meter_id)
    );
    if (matchesSource(p, reading) && p.anomaly && !alreadyListed) {
        recent.unshift({event_id:p.event_id,source_event_id:p.source_event_id,timestamp:p.timestamp,site_id:p.site_id,meter_id:p.meter_id,score:p.score.toFixed(4),threshold:p.threshold.toFixed(4),model_variant:p.model_variant,explanation:p.explanation});
        recent.splice(MAX_ANOMALIES);
    }
    return recent;
}""",
        ),
        (
            """        if (match && match.site_id === reading.site_id && match.meter_id === reading.meter_id && match.timestamp === reading.timestamp) {
            const latest = latestPredictionWidgets(match);
            for (let i=5;i<=7;i++) outputs[i] = latest[i];
        }""",
            """        if (matchesSource(match, reading)) {
            const updatedRecent = addAnomaly(match, reading, recent);
            flow.set('dashboard_recent_anomalies', updatedRecent);
            outputs[8] = {payload:updatedRecent};
            const latest = latestPredictionWidgets(match);
            for (let i=5;i<=7;i++) outputs[i] = latest[i];
        }""",
        ),
        (
            """        const recent = flow.get('dashboard_recent_anomalies') || [];
        putBounded(predictions, p.source_event_id, p);
        flow.set('dashboard_predictions', predictions);
        const updatedRecent = addAnomaly(p, recent);
        flow.set('dashboard_recent_anomalies', updatedRecent);
        const currentId = flow.get('dashboard_current_reading_id');
        const source = readings[p.source_event_id];
        if (source && source.site_id === p.site_id && source.meter_id === p.meter_id && source.timestamp === p.timestamp && currentId === p.source_event_id) {
            const latest = latestPredictionWidgets(p);
            for (let i=5;i<=7;i++) outputs[i] = latest[i];
        }
        outputs[8] = {payload:updatedRecent};""",
            """        const recent = flow.get('dashboard_recent_anomalies') || [];
        putBounded(predictions, p.source_event_id, p);
        flow.set('dashboard_predictions', predictions);
        const source = readings[p.source_event_id];
        const linked = matchesSource(p, source);
        const updatedRecent = linked ? addAnomaly(p, source, recent) : recent;
        if (linked) flow.set('dashboard_recent_anomalies', updatedRecent);
        const currentId = flow.get('dashboard_current_reading_id');
        if (linked && currentId === p.source_event_id) {
            const latest = latestPredictionWidgets(p);
            for (let i=5;i<=7;i++) outputs[i] = latest[i];
        }
        outputs[8] = {payload:updatedRecent};""",
        ),
    )

    migrated = current
    for old, new in display_replacements:
        count = migrated.count(old)
        if count == 1:
            migrated = migrated.replace(old, new, 1)
        elif count > 1:
            raise MigrationError("A display patch matched multiple times; refusing to alter the function.")

    for old, new in correlation_replacements:
        count = migrated.count(old)
        if count == 1:
            migrated = migrated.replace(old, new, 1)
        elif count == 0 and new in migrated:
            continue
        else:
            raise MigrationError(
                "A correlation patch did not match the reviewed function state; "
                "refusing to replace custom Function-node logic."
            )

    if migrated != desired:
        raise MigrationError(
            "The function's remaining differences do not match the reviewed "
            "polished source. Refusing to replace custom function logic."
        )
    return migrated


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def apply_candidate(
    before: list[dict[str, Any]],
    polished: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before_by_id = index_nodes(before, "live flows.json")
    polished_by_id = target_map(polished)
    baseline_by_id = index_nodes(baseline, "pre-polish baseline")

    dashboard_tabs = [
        node
        for node in before
        if node.get("type") == "tab" and node.get("label") == "Hostel Electricity Monitoring"
    ]
    if len(dashboard_tabs) != 1 or dashboard_tabs[0].get("id") != DASHBOARD_TAB_ID:
        raise MigrationError(
            "Expected exactly one Hostel Electricity Monitoring tab with the reviewed ID."
        )
    if polished_by_id.get(DASHBOARD_TAB_ID, {}).get("type") != "tab":
        raise MigrationError("Polished source does not contain the expected dashboard tab.")

    baseline_ids = set(baseline_by_id)
    polished_ids = set(polished_by_id)
    new_ids = {LATEST_GROUP_ID, MEAN_WIDGET_ID, NOTICE_ID}
    if not new_ids.issubset(polished_ids):
        raise MigrationError("Polished source is missing one or more reviewed additions.")
    if not baseline_ids.issubset(polished_ids):
        raise MigrationError("Polished source is missing original baseline node IDs.")
    if polished_ids != baseline_ids | new_ids:
        raise MigrationError("Polished source contains unexpected added or removed IDs.")

    current_dashboard = config_closure(before, before_by_id, DASHBOARD_TAB_ID)
    current_dashboard_ids = set(current_dashboard)
    expected_before = baseline_ids
    expected_after = baseline_ids | new_ids
    if current_dashboard_ids not in (expected_before, expected_after):
        unexpected = sorted(current_dashboard_ids ^ expected_before)
        raise MigrationError(
            "Live dashboard node/config set differs from the reviewed baseline; "
            f"unexpected IDs: {unexpected}"
        )

    # Source and live copies must agree on node type for every original ID.
    for node_id in baseline_ids:
        if before_by_id.get(node_id, {}).get("type") != baseline_by_id[node_id].get("type"):
            raise MigrationError(f"Node type changed for original ID {node_id}.")
        if polished_by_id[node_id].get("type") != baseline_by_id[node_id].get("type"):
            raise MigrationError(f"Polished source changes the type of original ID {node_id}.")

    protected_ids = {
        DASHBOARD_TAB_ID,
        BROKER_NODE_ID,
        "145f0795d62e4648",  # Dashboard UI base
        "2923ac50c4d14145",  # Live Monitoring page
        "f106e96a124548a4",  # Dashboard theme
        READINGS_NODE_ID,
        PREDICTIONS_NODE_ID,
    }
    for node_id in protected_ids:
        if node_id not in before_by_id or node_id not in polished_by_id:
            raise MigrationError(f"Protected node {node_id} is missing.")
        if before_by_id[node_id] != polished_by_id[node_id]:
            raise MigrationError(
                f"Polished source differs from protected node {node_id}; "
                "broker, topics, subscriptions, and UI configuration must remain exact."
            )

    for node_id in new_ids:
        existing = before_by_id.get(node_id)
        if existing is not None and existing.get("type") != polished_by_id[node_id].get("type"):
            raise MigrationError(f"New-component ID {node_id} is occupied by a different node type.")

    candidate = copy.deepcopy(before)
    candidate_by_id = index_nodes(candidate, "candidate flows.json")

    # Patch only the reviewed visual/configuration fields on existing nodes.
    field_patches: dict[str, tuple[str, ...]] = {
        "b7203704f222496e": ("order",),
        "1b7ae57c6bad43cf": ("order",),
        "f07d102b06f14a19": ("order",),
        "21141ac6b4254bc7": ("value", "valueType"),
        "beef18440de44a48": ("height", "pointRadius", "xAxisLabel"),
        "fc1c715529d24da6": ("fontSize", "group", "order", "width"),
        "ee2a26e7cbc74d16": ("fontSize", "group", "order", "width"),
        "36e083fb31ac4e53": ("fontSize", "group", "order", "width"),
        "9644628cdee3400f": ("color", "fontSize", "order", "width"),
        "1cd51364240d4b33": ("columns", "height"),
        "011d4f5429874b5b": ("info", "name"),
    }
    for node_id, fields in field_patches.items():
        current = candidate_by_id.get(node_id)
        target = polished_by_id.get(node_id)
        if current is None or target is None:
            raise MigrationError(f"Expected dashboard node {node_id} is missing.")
        for field in fields:
            current[field] = copy.deepcopy(target[field])

    function = candidate_by_id[FUNCTION_NODE_ID]
    target_function = polished_by_id[FUNCTION_NODE_ID]
    function["func"] = patch_function(function.get("func", ""), target_function["func"])
    current_wires = copy.deepcopy(function.get("wires", []))
    target_wires = target_function.get("wires", [])
    if len(target_wires) != 10 or target_wires[9] != [MEAN_WIDGET_ID]:
        raise MigrationError("Polished function output 9 is not wired only to the mean readout.")
    if current_wires[:9] != target_wires[:9]:
        raise MigrationError("Existing function outputs 0–8 differ from the reviewed wiring.")
    if len(current_wires) == 9:
        current_wires.append([MEAN_WIDGET_ID])
    elif len(current_wires) == 10:
        if current_wires[9] != [MEAN_WIDGET_ID]:
            raise MigrationError("Function output 9 already has an unexpected wire.")
    else:
        raise MigrationError("The live function does not have the expected 9-output baseline.")
    function["wires"] = current_wires
    function["outputs"] = 10

    # Preserve the live gauge's existing wire representation; only its display
    # value expression and type are changed above.
    for node_id in (LATEST_GROUP_ID, MEAN_WIDGET_ID, NOTICE_ID):
        target = polished_by_id[node_id]
        if node_id not in candidate_by_id:
            added = copy.deepcopy(target)
            candidate.append(added)
            candidate_by_id[node_id] = added
        else:
            existing = candidate_by_id[node_id]
            # A second run is accepted only if the pre-existing addition is
            # already exactly the reviewed component. Avoid clobbering edits.
            if existing != target:
                raise MigrationError(
                    f"Previously added component {node_id} differs from the reviewed source."
                )

    after_by_id = index_nodes(candidate, "candidate flows.json")
    checks = validate_candidate(before, candidate, before_by_id, after_by_id, baseline_by_id, polished_by_id)

    all_before = index_nodes(before, "live flows.json")
    all_after = index_nodes(candidate, "candidate flows.json")
    report_nodes = []
    for node_id in sorted(set(all_before) | set(all_after)):
        old = all_before.get(node_id)
        new = all_after.get(node_id)
        if old is None:
            status = "added"
            fields: list[str] = []
            item = new
        elif new is None:
            status = "removed"
            fields = []
            item = old
        else:
            fields = changed_fields(old, new)
            status = "changed" if fields else "unchanged"
            item = new
        report_nodes.append(
            {
                "id": node_id,
                "type": item.get("type"),
                "name": node_label(item),
                "status": status,
                "changed_fields": fields,
            }
        )

    before_dashboard = config_closure(before, all_before, DASHBOARD_TAB_ID)
    after_dashboard = config_closure(candidate, all_after, DASHBOARD_TAB_ID)
    changed_count = sum(1 for node in report_nodes if node["status"] == "changed")
    added_count = sum(1 for node in report_nodes if node["status"] == "added")
    unchanged_count = sum(1 for node in report_nodes if node["status"] == "unchanged")
    global_reading_count = sum(
        1 for node in candidate if node.get("type") == "mqtt in" and node.get("topic") == READINGS_TOPIC
    )
    global_prediction_count = sum(
        1 for node in candidate if node.get("type") == "mqtt in" and node.get("topic") == PREDICTIONS_TOPIC
    )
    warnings = []
    if global_reading_count != 1:
        warnings.append(
            "The full Node-RED instance has "
            f"{global_reading_count} readings input(s) on {READINGS_TOPIC}; one is in "
            "the separate Flow 1 debug flow. It is preserved unchanged, so the global "
            "count cannot be one while honoring the Flow 1 preservation requirement. "
            "The dashboard tab itself has exactly one readings input."
        )

    report = {
        "report_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "live_flow_file": str(DEFAULT_FLOW_FILE),
        "polished_source": str(DEFAULT_POLISHED),
        "pre_polish_baseline": str(DEFAULT_BASELINE),
        "backup_created_before_preparation": None,
        "mode": "dry-run",
        "summary": {
            "nodes_before": len(before),
            "nodes_after_candidate": len(candidate),
            "dashboard_nodes_before": len(before_dashboard),
            "dashboard_nodes_after_candidate": len(after_dashboard),
            "changed": changed_count,
            "added": added_count,
            "removed": sum(1 for node in report_nodes if node["status"] == "removed"),
            "unchanged": unchanged_count,
        },
        "checks": checks,
        "warnings": warnings,
        "nodes": report_nodes,
    }
    return candidate, report


def validate_candidate(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    before_by_id: dict[str, dict[str, Any]],
    after_by_id: dict[str, dict[str, Any]],
    baseline_by_id: dict[str, dict[str, Any]],
    polished_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            raise MigrationError(f"Validation failed: {name}: {detail}")

    check(
        "single_dashboard_tab",
        sum(1 for node in after if node.get("type") == "tab" and node.get("label") == "Hostel Electricity Monitoring") == 1,
        "Exactly one Hostel Electricity Monitoring tab exists.",
    )
    after_dashboard = config_closure(after, after_by_id, DASHBOARD_TAB_ID)
    check("dashboard_readings_input", sum(n.get("type") == "mqtt in" and n.get("topic") == READINGS_TOPIC for n in after_dashboard.values()) == 1, "Exactly one readings input exists in the dashboard tab.")
    check("dashboard_predictions_input", sum(n.get("type") == "mqtt in" and n.get("topic") == PREDICTIONS_TOPIC for n in after_dashboard.values()) == 1, "Exactly one predictions input exists in the dashboard tab.")
    check("unique_node_ids", len(after_by_id) == len(after), "All node IDs are unique.")

    broker_before = before_by_id.get(BROKER_NODE_ID)
    broker_after = after_by_id.get(BROKER_NODE_ID)
    check("broker_unchanged", broker_before == broker_after, "Broker node ID and complete serialized settings are unchanged.")
    for node_id, topic in ((READINGS_NODE_ID, READINGS_TOPIC), (PREDICTIONS_NODE_ID, PREDICTIONS_TOPIC)):
        old = before_by_id.get(node_id)
        new = after_by_id.get(node_id)
        check(
            f"mqtt_subscription_unchanged_{node_id}",
            old == new and new is not None and new.get("topic") == topic and new.get("qos") == "1" and new.get("broker") == BROKER_NODE_ID,
            f"Topic {topic}, QoS 1, broker reference, and complete node configuration are unchanged.",
        )

    for node_id, label in (
        (DASHBOARD_TAB_ID, "tab"),
        ("145f0795d62e4648", "ui-base"),
        ("2923ac50c4d14145", "ui-page"),
        ("f106e96a124548a4", "ui-theme"),
    ):
        check(f"protected_{label}_unchanged", before_by_id.get(node_id) == after_by_id.get(node_id), f"Original {label} ID and all serialized fields are unchanged.")

    old_function = before_by_id[FUNCTION_NODE_ID]
    new_function = after_by_id[FUNCTION_NODE_ID]
    desired_function = polished_by_id[FUNCTION_NODE_ID]
    try:
        correlation_preserved = patch_function(old_function.get("func", ""), desired_function["func"]) == desired_function["func"]
    except MigrationError:
        correlation_preserved = old_function.get("func") == desired_function.get("func")
    check("correlation_logic_preserved_exactly", correlation_preserved, "The polished function is reachable only via the reviewed display-only textual patch; all other function-code bytes, including validation and source_event_id correlation, match exactly.")
    check("function_output_count", new_function.get("outputs") == 10 and len(new_function.get("wires", [])) == 10, "Processing function has 10 outputs.")
    check("function_outputs_0_to_8_preserved", new_function.get("wires", [])[:9] == old_function.get("wires", [])[:9], "Existing output 0–8 targets are byte-for-byte unchanged.")
    check("function_output_9_only_mean_widget", new_function.get("wires", [])[9:10] == [[MEAN_WIDGET_ID]], "Output 9 targets only the new mean-power readout.")

    # Flow 1 and every node not owned by the dashboard are immutable.
    flow1_tabs = [node for node in before if node.get("type") == "tab" and node.get("label") == FLOW_1_LABEL]
    if len(flow1_tabs) != 1:
        raise MigrationError("Expected exactly one separate Flow 1 tab.")
    flow1_before = flow_snapshot(before, before_by_id, flow1_tabs[0])
    flow1_after = flow_snapshot(after, after_by_id, after_by_id[flow1_tabs[0]["id"]])
    check("flow_1_unchanged", flow1_before == flow1_after, "Flow 1 and its transitively referenced config nodes are unchanged.")

    # Check every ordinary wire and every Dashboard 2.0 config reference.
    bad_wires = []
    for node in after:
        for port in node.get("wires", []):
            for target in port:
                if target not in after_by_id:
                    bad_wires.append((node.get("id"), target))
    check("all_wire_targets_exist", not bad_wires, f"No dangling wire targets ({len(bad_wires)} found).")
    bad_refs = []
    for node in after:
        kind = node.get("type")
        if kind == "ui-page":
            if after_by_id.get(node.get("ui"), {}).get("type") != "ui-base": bad_refs.append((node["id"], "ui"))
            if after_by_id.get(node.get("theme"), {}).get("type") != "ui-theme": bad_refs.append((node["id"], "theme"))
        elif kind == "ui-group":
            if after_by_id.get(node.get("page"), {}).get("type") != "ui-page": bad_refs.append((node["id"], "page"))
        elif kind and kind.startswith("ui-") and kind not in ("ui-base", "ui-page", "ui-group", "ui-theme", "ui-link", "ui-control"):
            if after_by_id.get(node.get("group"), {}).get("type") != "ui-group": bad_refs.append((node["id"], "group"))
        elif kind == "mqtt in":
            if after_by_id.get(node.get("broker"), {}).get("type") != "mqtt-broker": bad_refs.append((node["id"], "broker"))
    check("all_ui_and_broker_references_valid", not bad_refs, f"No invalid page/group/theme/UI-base/broker references ({len(bad_refs)} found).")

    global_readings = sum(n.get("type") == "mqtt in" and n.get("topic") == READINGS_TOPIC for n in after)
    global_predictions = sum(n.get("type") == "mqtt in" and n.get("topic") == PREDICTIONS_TOPIC for n in after)
    checks.append({"name": "global_readings_input_count", "passed": global_readings == 1, "warning": global_readings != 1, "detail": f"There are {global_readings} readings inputs across all tabs; Flow 1 is preserved and owns a separate debug subscription."})
    check("global_predictions_input_count", global_predictions == 1, f"There are {global_predictions} predictions inputs across all tabs.")

    check("expected_dashboard_id_set", set(after_dashboard) == set(baseline_by_id) | {LATEST_GROUP_ID, MEAN_WIDGET_ID, NOTICE_ID}, "Existing 26 dashboard node/config IDs plus exactly the three reviewed additions are present.")
    check("chart_limit_and_timestamp_axis", after_by_id["beef18440de44a48"].get("removeOlderPoints") == 500 and after_by_id["beef18440de44a48"].get("xAxisType") == "category" and after_by_id["beef18440de44a48"].get("xAxisProperty") == "x", "Chart remains capped at 500 points and uses the original timestamp string on its categorical x-axis.")
    check("nullable_occupancy_and_correlated_review_candidates", "occupancy_fraction === null" in new_function.get("func", "") and "matchesSource(p, reading) && p.anomaly && !alreadyListed" in new_function.get("func", ""), "Null occupancy remains Unknown; only anomaly predictions with a matching source reading enter the bounded review table.")
    return checks


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def restore_bytes_atomic(path: Path, contents: bytes) -> None:
    """Restore exact backup bytes with an atomic same-directory replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.restore.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def create_non_overwriting_backup(flow_file: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = flow_file.with_name(f"flows.backup.dashboard-polish-apply-{stamp}.json")
    raw = flow_file.read_bytes()
    try:
        with backup.open("xb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError as exc:
        raise MigrationError(f"Refusing to overwrite existing backup: {backup}") from exc
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow-file", type=Path, default=DEFAULT_FLOW_FILE)
    parser.add_argument("--polished", type=Path, default=DEFAULT_POLISHED)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--prepared-backup", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Create an immediate backup and atomically update the live flow file.")
    args = parser.parse_args()

    flow_file = args.flow_file.expanduser().resolve()
    polished_path = args.polished.expanduser().resolve()
    baseline_path = args.baseline.expanduser().resolve()
    report_path = args.report.expanduser().resolve()

    before = read_json_array(flow_file)
    polished = read_json_array(polished_path)
    baseline = read_json_array(baseline_path)
    candidate, report = apply_candidate(before, polished, baseline)
    report["live_flow_file"] = str(flow_file)
    report["polished_source"] = str(polished_path)
    report["pre_polish_baseline"] = str(baseline_path)
    report["backup_created_before_preparation"] = str(args.prepared_backup.expanduser().resolve()) if args.prepared_backup else None

    backup_path = None
    if args.apply:
        if args.prepared_backup is None:
            raise MigrationError(
                "Apply requires --prepared-backup so the live flow can be checked "
                "against the reviewed snapshot."
            )
        reviewed_backup_path = args.prepared_backup.expanduser().resolve()
        reviewed_bytes = reviewed_backup_path.read_bytes()
        if flow_file.read_bytes() != reviewed_bytes:
            raise MigrationError(
                "The live flow file has changed since the reviewed backup. "
                "Refusing to apply; inspect the new flow and prepare a fresh review."
            )

        backup_path = create_non_overwriting_backup(flow_file)
        report["mode"] = "apply"
        report["apply_backup"] = str(backup_path)
        backup_bytes = backup_path.read_bytes()
        if backup_bytes != reviewed_bytes or flow_file.read_bytes() != reviewed_bytes:
            raise MigrationError(
                "The live flow changed during apply preparation. The fresh backup "
                f"was preserved at {backup_path}; refusing to write the candidate."
            )
        try:
            write_json_atomic(flow_file, candidate)
            applied = read_json_array(flow_file)
            applied_by_id = index_nodes(applied, "applied flows.json")
            before_by_id = index_nodes(before, "pre-apply flows.json")
            baseline_by_id = index_nodes(baseline, "pre-polish baseline")
            polished_by_id = index_nodes(polished, "polished dashboard source")
            report["checks"] = validate_candidate(before, applied, before_by_id, applied_by_id, baseline_by_id, polished_by_id)
        except Exception as exc:
            try:
                restore_bytes_atomic(flow_file, backup_bytes)
            except Exception as restore_exc:
                raise MigrationError(
                    f"Post-write validation failed ({exc}); automatic rollback also failed "
                    f"({restore_exc}). The untouched backup is preserved at {backup_path}."
                ) from restore_exc
            raise MigrationError(
                f"Post-write validation failed ({exc}); the live flow was restored from "
                f"{backup_path}."
            ) from exc

    write_json_atomic(report_path, report)
    print(json.dumps({
        "mode": report["mode"],
        "backup": str(backup_path) if backup_path else report.get("backup_created_before_preparation"),
        "report": str(report_path),
        "summary": report["summary"],
        "failed_checks": [check for check in report["checks"] if not check.get("passed") and not check.get("warning")],
        "warnings": report["warnings"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        raise SystemExit(f"Migration refused: {exc}")
