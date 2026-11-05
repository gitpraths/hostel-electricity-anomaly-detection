# Node-RED live electricity dashboard

This phase provides an importable Node-RED Dashboard 2.0 flow for monitoring the MQTT reading and prediction streams. It is a separate flow tab and uses its own local Mosquitto broker configuration; it does not replace or edit the existing manually created MQTT-to-Debug flow.

## Import and open

For a first-time installation, start the local broker and Node-RED editor, import `node-red/hostel-electricity-dashboard.json` as a new flow, review the preview, and deploy. This is not the update procedure for an already-installed dashboard.

For an already-installed dashboard, do not import the polished JSON or an update-only copy through the editor. An import can add a duplicate set of nodes; matching IDs do not safely replace the live nodes. The polished flow is already present in this repository. For a future approved file migration, stop Node-RED gracefully, create a fresh snapshot of `~/.node-red/flows.json`, and prepare/inspect the candidate with the migration script:

```bash
python scripts/migrate_node_red_dashboard.py --prepared-backup "$HOME/.node-red/flows.backup.dashboard-polish-prep-YYYYMMDDTHHMMSSZ.json"
```

After explicit approval, apply against that same snapshot:

```bash
python scripts/migrate_node_red_dashboard.py --apply --prepared-backup "$HOME/.node-red/flows.backup.dashboard-polish-prep-YYYYMMDDTHHMMSSZ.json"
```

Apply mode creates a fresh backup, refuses if the live file differs from the reviewed snapshot, writes atomically, validates, and restores the backup if post-write validation fails. It does not restart or deploy Node-RED. Restart Node-RED after a successful update so it loads the configured flow file. See [`docs/node-red-dashboard.md`](../docs/node-red-dashboard.md) for details.

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
