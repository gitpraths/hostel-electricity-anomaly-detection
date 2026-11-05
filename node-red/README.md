# Node-RED live electricity dashboard

This phase provides an importable Node-RED Dashboard 2.0 flow for monitoring the MQTT reading and prediction streams. It is a separate flow tab and uses its own local Mosquitto broker configuration; it does not replace or edit the existing manually created MQTT-to-Debug flow.

## Import and open

For a first-time installation, start the local broker and Node-RED editor, import `node-red/hostel-electricity-dashboard.json` as a new flow, review the preview, and deploy.

For an update to the already-deployed flow, **do not import the full file as a new flow**. First export the current deployed tab as an additional recovery copy. Then generate an update file without the tab node, keeping existing IDs and `z` references:

```bash
python - <<'PY'
import json
from pathlib import Path
source = Path("node-red/hostel-electricity-dashboard.json")
nodes = json.loads(source.read_text())
update = [node for node in nodes if node.get("type") != "tab"]
Path("/tmp/hostel-electricity-dashboard-update.json").write_text(json.dumps(update, indent=2))
PY
```

In Node-RED choose **Menu → Import → select a file**, select `/tmp/hostel-electricity-dashboard-update.json`, and import into the current flow. If Node-RED reports ID conflicts, choose **View nodes**; replace the conflicting existing nodes/config nodes with the imported versions and keep the new nodes selected for import. Do not choose **Import copy**. The update file contains no tab node, so the deployed dashboard tab is preserved and no second tab is created. Review the canvas, verify there is still one **Hostel Electricity Monitoring** tab, then Deploy. Refresh the dashboard URL. The repository backup at `node-red/hostel-electricity-dashboard.backup.json` is the pre-edit flow; export the live editor first too if you have made local changes since deploying it.

Dashboard URL: [http://127.0.0.1:1880/dashboard/hostel-electricity](http://127.0.0.1:1880/dashboard/hostel-electricity).

The flow's MQTT broker node is `127.0.0.1:1883`, MQTT 3.1.1, no authentication, and no TLS, matching current local testing. Do not expose this broker to a network as configured.

## What it shows

- Current mean total power in W, using a 0–6,000 W gauge range based on ECO Household 1's observed mean-power range (50.7–5,608.2 W), plus an adjacent zero-padded two-decimal readout.
- A mean-power line chart with the source `timestamp` string as its categorical x-axis. It retains at most 500 chart points and does not substitute the current time.
- Latest interval peak and within-interval standard deviation, both shown to two decimal places in W; occupancy is shown to at most one decimal place.
- Occupancy fraction as a percentage, or **Unknown** for JSON `null`.
- Isolation Forest status as **PENDING PREDICTION** until a prediction matching the reading's `event_id` arrives; then NORMAL or ANOMALY. It also shows score, threshold, model variant, and the documented score direction (higher means more unusual).
- The robust statistical comparator, explicitly styled as secondary and shown to four decimal places, plus a bounded recent anomaly review table containing at most 20 entries. Scores and thresholds are shown to four decimal places. A note explains that flags are review candidates, not confirmed faults.
- MQTT connection status for the two Node-RED subscriptions. Broker connectivity alone does not indicate ML service health.

The latest interval indicators share a four-tile responsive group. The anomaly section separates primary status, score context, and the secondary comparator. The table columns are aligned for scanning and the timestamp/explanation columns receive more width.

The function node validates reading schema `2.0` and prediction schema `1.0`, validates topic/payload site and meter IDs, rejects malformed or incompatible messages, and correlates via prediction `source_event_id` and reading `event_id`. It handles predictions arriving before readings with bounded in-memory caches (500 recent readings and 500 predictions). Recent anomaly events are bounded to 20 and duplicate prediction IDs are ignored in the table.

## Local replay walkthrough

From the repository root, run these services in separate terminals after ensuring the trained model artifact and processed Parquet are available:

```bash
python -m mqtt.storage_service
python -m mqtt.inference_service
python -m iot.publisher --replay-delay 0.25
```

For a faster smoke replay, use `--replay-delay 0.01 --max-records 10`. The publisher replays historical ECO data, not live meter readings. A reading updates the power widgets and sets prediction status to pending. When inference publishes the corresponding `source_event_id`, the model widgets update; an anomalous prediction also appears in the recent events table. The SQLite receiver persists events independently; the dashboard does not read the database.

## Future Computer 2 / LAN configuration

The imported broker node is intentionally set to loopback. For a later two-computer deployment, edit this broker config in Node-RED to Computer 1's reachable hostname/IP and configure broker authentication and TLS as appropriate. Set `ML_MQTT_HOST` on Computer 2 to that reachable address; do not use localhost there. Review firewall/broker binding separately. This phase does not expose or reconfigure Mosquitto.

## Limitations

- Widget/cache history is in memory and resets when Node-RED restarts or redeploys this flow. The database remains separate and no historical SQLite/API view is implemented.
- The chart is a bounded most-recent-500 point view, not a full historical archive.
- The source ECO timestamp is timezone-naive; the chart displays the original timestamp label without adding an offset.
- The table is a review aid. Model flags are not verified faults, and the robust comparator is not the primary model.
- The editor and dashboard are unauthenticated in current localhost development settings; keep them local unless separately secured.
