# Phase 4F — Node-RED live dashboard

The importable flow is [`node-red/hostel-electricity-dashboard.json`](../node-red/hostel-electricity-dashboard.json). It creates a separate Node-RED tab named **Hostel Electricity Monitoring**, a Dashboard 2.0 page named **Live Monitoring**, and a dedicated local MQTT broker configuration. It leaves the existing manual flow untouched.

## Requirements and import

The flow was authored against Node-RED 5.0.9 and `@flowfuse/node-red-dashboard` 1.35.0 (the installed package at implementation time). In the editor at `http://127.0.0.1:1880`, use **Menu → Import → select a file**, choose the JSON flow, import it as a new flow, inspect the preview, and click **Import**. Deploy the new tab after import. The editor's existing tab and MQTT-to-Debug nodes are not part of the exported file.

Dashboard URL: [http://127.0.0.1:1880/dashboard/hostel-electricity](http://127.0.0.1:1880/dashboard/hostel-electricity).

The broker config uses `127.0.0.1:1883`, MQTT 3.1.1, no credentials and no TLS for local testing. The two `mqtt in` nodes subscribe at QoS 1 to `hostel/v1/readings/+/+` and `hostel/v1/predictions/+/+`.

## Widget behavior

| Area | Behavior |
| --- | --- |
| Live readings | Gauge for mean total power (W; 0–6,000 range based on the supplied ECO EDA), chart with source timestamp labels, latest peak power, within-interval standard deviation, and occupancy percentage or Unknown. The chart retains at most 500 points. |
| Anomaly Detection | Shows PENDING PREDICTION on each new reading until its linked prediction arrives. Then displays Isolation Forest NORMAL/ANOMALY, score, threshold, selected model variant, and the higher-score-means-more-unusual interpretation. Shows robust baseline output as a secondary comparator. |
| Recent Anomaly Events | Table of at most 20 primary-model anomaly review candidates with timestamp, site, meter, score, threshold, model variant, and explanation. Repeated prediction event IDs do not duplicate table entries. |
| MQTT Connection | Reports connection status for the Node-RED MQTT subscriptions. This is broker/subscription connectivity and does not prove that the independent ML service is connected or publishing. |

## Validation, correlation, and memory

The common function node parses JSON/object input and validates the actual reading schema `2.0` and prediction schema `1.0`, required fields, numeric/boolean values, timezone-naive timestamp formatting, UUIDs, and topic/payload identifiers. Invalid messages are logged through Node-RED `node.warn` and ignored. Occupancy JSON `null` remains unknown and displays as Unknown.

Reading and prediction topics are independent. The function correlates on prediction `source_event_id` matching reading `event_id`, with site, meter and timestamp agreement. Predictions received first are held in a 500-entry bounded cache; recent readings are also bounded to 500. Delayed predictions for older readings can update the anomaly table but do not overwrite the latest-reading model status. The chart retains no more than 500 recent points, and recent anomaly rows are limited to 20.

The source ECO timestamps have no verified timezone. They are shown as the original timestamp strings on a categorical chart axis, avoiding an implied UTC conversion or replacement with current time. The dashboard state is in memory and is not an archival interface. SQLite is not exposed to widgets; no API or backend was added.

## Local test

Start the broker, then in separate repository-root terminals:

```bash
python -m mqtt.storage_service
python -m mqtt.inference_service
python -m iot.publisher --replay-delay 0.25
```

For a short fast demonstration use `python -m iot.publisher --replay-delay 0.01 --max-records 10`. The publisher emits historical ECO replay messages. It is not a live electricity meter. If model artifacts or the processed Parquet are not present locally, the corresponding publisher/inference command cannot run until those existing project artifacts are supplied.

Example walkthrough: a schema 2.0 reading at `2012-12-24T17:45:00` with `powerallphases_mean_w: 322.6`, `powerallphases_max_w: 402.7`, `powerallphases_std_w: 25.3`, and `occupancy_fraction: null` updates the gauge, chart, peak, variability, and occupancy widgets; occupancy reads **Unknown** and model status reads **PENDING PREDICTION**. A later schema 1.0 prediction whose `source_event_id` equals that reading's `event_id` updates model status, score/threshold/variant, and robust comparator. If `anomaly` is true, it adds the prediction's timestamp/site/meter/score/threshold/model variant/explanation to the bounded table. This is a message-flow example; the prediction value is not fabricated as a project result.

## Future LAN deployment and limitations

The flow does not change the broker listener or firewall and is configured only for localhost. When Computer 2 becomes available, update the imported MQTT broker config to Computer 1's reachable hostname/IP, configure `ML_MQTT_HOST` on Computer 2 to that address, and separately configure authentication/TLS, listener binding, firewall policy, and secured Node-RED access. Never configure Computer 2 with localhost for a broker running on Computer 1.

Known limitations: Node-RED flow caches and widgets reset on restart/redeploy; no SQLite history/API, alert delivery, or durable dashboard cache is included; the recent-event list is only a review aid, because anomaly flags have no verified ground truth. Dashboard/editor security is not configured by this phase, so keep them bound to localhost unless separately secured.
