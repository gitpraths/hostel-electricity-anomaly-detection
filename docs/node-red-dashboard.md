# Phase 4F — Node-RED live dashboard

The importable flow is [`node-red/hostel-electricity-dashboard.json`](../node-red/hostel-electricity-dashboard.json). It creates a separate Node-RED tab named **Hostel Electricity Monitoring**, a Dashboard 2.0 page named **Live Monitoring**, and a dedicated local MQTT broker configuration. It leaves the existing manual flow untouched.

## Requirements and import

The flow was authored against Node-RED 5.0.9 and `@flowfuse/node-red-dashboard` 1.35.0 (the installed package at implementation time). For first-time setup only, in the editor at `http://127.0.0.1:1880`, use **Menu → Import → select a file**, choose the JSON flow, import it as a new flow, inspect the preview, and deploy. The editor's existing tab and MQTT-to-Debug nodes are not part of the exported file.

For an already-installed dashboard, do not import the polished JSON or an update-only copy through the editor. Import can create a second set of nodes; matching IDs are not a safe replacement mechanism. The checked-in flow is already polished. For a future file-based update, first stop Node-RED gracefully, save a fresh copy of `~/.node-red/flows.json`, run the migration script's dry-run and inspect its report, then apply only after approval:

```bash
python scripts/migrate_node_red_dashboard.py --prepared-backup "$HOME/.node-red/flows.backup.dashboard-polish-prep-YYYYMMDDTHHMMSSZ.json"
python scripts/migrate_node_red_dashboard.py --apply --prepared-backup "$HOME/.node-red/flows.backup.dashboard-polish-prep-YYYYMMDDTHHMMSSZ.json"
```

The `--prepared-backup` path must be the exact reviewed snapshot; apply mode refuses if `flows.json` has changed since that snapshot. Apply mode creates another non-overwriting backup, atomically replaces the flow file, validates the result, and restores the backup on validation failure. It does not restart Node-RED or deploy. After a successful apply, start Node-RED again; it loads the configured flow file automatically. See [`scripts/migrate_node_red_dashboard.py`](../scripts/migrate_node_red_dashboard.py) for safeguards and report details.

Dashboard URL: [http://127.0.0.1:1880/dashboard/hostel-electricity](http://127.0.0.1:1880/dashboard/hostel-electricity).

The broker config uses `127.0.0.1:1883`, MQTT 3.1.1, no credentials and no TLS for local testing. The two `mqtt in` nodes subscribe at QoS 1 to `hostel/v1/readings/+/+` and `hostel/v1/predictions/+/+`.

## Widget behavior

| Area | Behavior |
| --- | --- |
| Live readings | Gauge and adjacent exact readout for mean total power (W; 0–6,000 range based on the supplied ECO EDA), chart with source timestamp labels, latest peak power, within-interval standard deviation, and occupancy percentage or Unknown. Mean/peak/std are displayed to two decimals; occupancy uses at most one. The chart retains at most 500 points. |
| Anomaly Detection | Shows amber PENDING PREDICTION until a linked prediction arrives, then green NORMAL or red ANOMALY. Isolation Forest score and threshold use four decimals and include the model variant and score direction. Robust score uses four decimals and is visually muted as a secondary comparator. A visible note says flags are candidates for review, not confirmed faults. |
| Recent Anomaly Events | Readable, aligned table of at most 20 primary-model anomaly review candidates with timestamp, site, meter, score, threshold, model variant, and explanation. Numeric table values use four decimals; repeated prediction event IDs do not duplicate rows. |
| MQTT Connection | Reports connection status for the Node-RED MQTT subscriptions. This is broker/subscription connectivity and does not prove that the independent ML service is connected or publishing. |

## Validation, correlation, and memory

The common function node parses JSON/object input and validates the actual reading schema `2.0` and prediction schema `1.0`, required fields, numeric/boolean values, timezone-naive timestamp formatting, UUIDs, and topic/payload identifiers. Invalid messages are logged through Node-RED `node.warn` and ignored. Occupancy JSON `null` remains unknown and displays as Unknown.

The latest power/peak/variability indicators use two decimal places; occupancy displays up to one decimal place and strips trailing `.0`. The gauge receives a rounded numeric value and an adjacent text readout preserves two decimal places (including trailing zeroes). Chart values are rounded to two decimals for display, but the source timestamp remains unchanged.

Reading and prediction topics are independent. The function correlates on prediction `source_event_id` matching reading `event_id`, with site, meter and timestamp agreement. Predictions received first are held in a 500-entry bounded cache; an anomaly is added to the review table only after its matching reading is available and all correlation fields agree. Delayed predictions for older readings can update the anomaly table but do not overwrite the latest-reading model status. The chart retains no more than 500 recent points, and recent anomaly rows are limited to 20. Duplicate prediction deliveries are deduplicated by prediction event ID and source reading ID.

The source ECO timestamps have no verified timezone. They are shown as the original timestamp strings on a categorical chart axis, avoiding an implied UTC conversion or replacement with current time. The dashboard state is in memory and is not an archival interface. SQLite is not exposed to widgets; no API or backend was added. Chart points, correlation caches, and anomaly rows reset when Node-RED restarts or redeploys; SQLite remains persistent. On startup Node-RED loads its configured flow file automatically, so an editor Deploy is not required just to load saved flows. For the complete Phase 6 local startup/shutdown order, see [Computer 1 setup](setup-computer-1.md).

## Local test

Start the broker, then in separate repository-root terminals:

```bash
python -m mqtt.storage_service
python -m mqtt.inference_service
python -m iot.publisher --replay-delay 0.25
```

For a short fast demonstration use `python -m iot.publisher --replay-delay 0.01 --max-records 10`. The publisher emits historical ECO replay messages. It is not a live electricity meter. If model artifacts or the processed Parquet are not present locally, the corresponding publisher/inference command cannot run until those existing project artifacts are supplied.

Example walkthrough: a schema 2.0 reading at `2012-12-24T17:45:00` with `powerallphases_mean_w: 322.6`, `powerallphases_max_w: 402.7`, `powerallphases_std_w: 25.3`, and `occupancy_fraction: null` updates the gauge, chart, peak, variability, and occupancy widgets; occupancy reads **Unknown** and model status reads **PENDING PREDICTION**. A schema 1.0 prediction is correlated only when its `source_event_id` equals the reading's `event_id` and its timestamp, site and meter also agree. A linked prediction updates model status, score/threshold/variant, and robust comparator. Only a linked prediction with `anomaly: true` adds its timestamp/site/meter/score/threshold/model variant/explanation to the bounded table. This is a message-flow example; the prediction value is not fabricated as a project result.

## Future LAN deployment and limitations

The flow does not change the broker listener or firewall and is configured only for localhost. When Computer 2 becomes available, update the imported MQTT broker config to Computer 1's reachable hostname/IP, configure `ML_MQTT_HOST` on Computer 2 to that address, and separately configure authentication/TLS, listener binding, firewall policy, and secured Node-RED access. Never configure Computer 2 with localhost for a broker running on Computer 1.

Known limitations: Node-RED flow caches and widgets reset on restart/redeploy; no SQLite history/API, alert delivery, or durable dashboard cache is included; the recent-event list is only a review aid, because anomaly flags have no verified ground truth. Dashboard/editor security is not configured by this phase, so keep them bound to localhost unless separately secured.
