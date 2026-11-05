# Node-RED live electricity dashboard

This phase provides an importable Node-RED Dashboard 2.0 flow for monitoring the MQTT reading and prediction streams. It is a separate flow tab and uses its own local Mosquitto broker configuration; it does not replace or edit the existing manually created MQTT-to-Debug flow.

## Import and open

1. Start the local broker and Node-RED editor.
2. In Node-RED, choose **Menu → Import → select a file**, then select `node-red/hostel-electricity-dashboard.json` (or paste its JSON through **Import → Clipboard**).
3. Import as a new flow/tab. Review the preview and choose **Import**.
4. Deploy the imported tab.
5. Open [http://127.0.0.1:1880/dashboard/hostel-electricity](http://127.0.0.1:1880/dashboard/hostel-electricity).

The flow's MQTT broker node is `127.0.0.1:1883`, MQTT 3.1.1, no authentication, and no TLS, matching current local testing. Do not expose this broker to a network as configured.

## What it shows

- Current mean total power in W, using a 0–6,000 W gauge range based on ECO Household 1's observed mean-power range (50.7–5,608.2 W).
- A mean-power line chart with the source `timestamp` string as its categorical x-axis. It retains at most 500 chart points and does not substitute the current time.
- Latest interval peak and within-interval standard deviation, both in W.
- Occupancy fraction as a percentage, or **Unknown** for JSON `null`.
- Isolation Forest status as **PENDING PREDICTION** until a prediction matching the reading's `event_id` arrives; then NORMAL or ANOMALY. It also shows score, threshold, model variant, and the documented score direction (higher means more unusual).
- The robust statistical comparator, explicitly shown as secondary, plus a bounded recent anomaly review table containing at most 20 entries.
- MQTT connection status for the two Node-RED subscriptions. Broker connectivity alone does not indicate ML service health.

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
