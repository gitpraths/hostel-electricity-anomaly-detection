# MQTT topic and message specification

Mosquitto runs on Computer 1. Set `MQTT_HOST` on both computers to Computer 1's
reachable hostname/IP; do not use `localhost` on Computer 2. Development port:
`1883` (plaintext on a trusted network only). Use TLS for untrusted networks.

## Topics

| Topic | Publisher | Subscriber | Purpose |
| --- | --- | --- | --- |
| `hostel/v1/readings/{site_id}/{meter_id}` | Computer 1 publisher/gateway | Computer 2 inference service; Computer 1 persistence (future) | Electricity observation stream. |
| `hostel/v1/predictions/{site_id}/{meter_id}` | Computer 2 inference service | Computer 1 prediction receiver/dashboard service (future) | Model score and anomaly decision for a reading. |
| `hostel/v1/status/{service_id}` | Each service | Monitoring clients | Health state; retained message is allowed. |

Identifiers are URL-safe and are not secrets. Do not publish occupant names or
other direct personal identifiers.

## Reading payload

UTF-8 JSON, one processed interval per message, published at **QoS 1** with
`retain=false`. The Phase 4C publisher replays historical ECO Household 1 data;
it is a simulator and does not represent a live physical meter. The delay
between messages controls replay pacing only; it does not change the timestamp
or sampling interval in the source record.

```json
{
  "schema_version": "2.0",
  "event_id": "31c59f53-8cc0-44d2-a44f-d8610adfe65f",
  "timestamp": "2012-12-24T17:45:00",
  "date": "2012-12-24",
  "time_of_day": "17:45:00",
  "interval_start_second": 63900,
  "hour": 17,
  "site_id": "hostel-a",
  "meter_id": "eco-household-01",
  "interval_seconds": 900,
  "powerallphases_mean_w": 322.63967,
  "powerallphases_max_w": 402.654,
  "powerallphases_std_w": 25.34958,
  "occupancy_fraction": 1.0,
  "source": "eco_household_1_historical_replay"
}
```

| Field | Type | Meaning / units |
| --- | --- | --- |
| `schema_version` | string | Reading message contract version, currently `2.0`. |
| `event_id` | string (UUID) | New unique identifier for each publish attempt/event. QoS 1 consumers should deduplicate by this value. Replaying the dataset again generates new IDs. |
| `timestamp` | string | Original interval start as timezone-naive `YYYY-MM-DDTHH:MM:SS`, assembled from source `date` and `time_of_day`; no UTC offset is claimed. |
| `date` | string | Source calendar date (`YYYY-MM-DD`), directly usable by ML inference. |
| `time_of_day` | string | Source wall-clock-style time (`HH:MM:SS`), directly usable for explanation and ML input validation. |
| `interval_start_second` | integer, seconds | Seconds since the source date began; the ML feature builder derives cyclic time sine/cosine from this value. |
| `hour` | integer, hour of day | Hour 0–23 from the original interval position; required by inference and the robust comparison. |
| `site_id`, `meter_id` | string | Topic identifiers repeated in the payload. |
| `interval_seconds` | integer, seconds | Source aggregation duration; normally `900` for 15 minutes. |
| `powerallphases_mean_w` | number, watts | Mean total real power across the interval. |
| `powerallphases_max_w` | number, watts | Maximum one-second total real power in the interval. |
| `powerallphases_std_w` | number, watts | Sample standard deviation (`ddof=1`) of one-second total power. |
| `occupancy_fraction` | number 0–1 or `null` | Fraction of source occupancy labels equal to occupied. `null` means unknown and must not be replaced by zero. |
| `source` | string | `eco_household_1_historical_replay`, identifying these as historical simulator messages. |

`timestamp` preserves the processed dataset's date plus time-of-day semantics.
The source has no verified timezone or offset, so payload timestamps omit `Z`
and offsets. The publisher does not attach the machine's local timezone.

### ML input mapping

The payload includes every raw column currently required by
`AnomalyDetector.predict`: `date`, `time_of_day`, `interval_start_second`,
`hour`, `powerallphases_mean_w`, `powerallphases_max_w`,
`powerallphases_std_w`, and `occupancy_fraction`. Map these fields to a one-row
DataFrame, keeping JSON `null` as a missing/NaN occupancy value. Pass that frame
to the existing feature builder. `ml.features.make_features` derives
`time_of_day_sin` and `time_of_day_cos` from `interval_start_second`; those
derived values are not transmitted or fabricated by the publisher. If
occupancy is null, the detector's no-occupancy branch is selected.

### Topic and delivery

Readings publish to `hostel/v1/readings/{site_id}/{meter_id}` at QoS 1, without
retention. Site and meter identifiers use letters, digits, underscores, or
hyphens. QoS 1 may redeliver a message, so consumers should deduplicate on
`event_id`. IDs are unique per generated event, not stable across separate
replay runs.

## Prediction payload

The Phase 4D service publishes one prediction for each valid reading it scores.
It sends predictions at QoS 1 with `retain=false`.

```json
{
  "schema_version": "1.0",
  "event_id": "44dddb77-602d-5396-9e31-4bded2383661",
  "source_event_id": "31c59f53-8cc0-44d2-a44f-d8610adfe65f",
  "timestamp": "2012-12-24T17:45:00",
  "site_id": "hostel-a",
  "meter_id": "eco-household-01",
  "model_version": "iforest-1.0.0-0123456789abcdef",
  "feature_schema_version": "1.0.0",
  "anomaly": false,
  "score": 0.4488,
  "threshold": 0.5899,
  "model_variant": "with_occupancy",
  "robust_anomaly": false,
  "robust_score": 0.01,
  "explanation": "mean 322.6 W; 15-min peak 402.7 W; within-interval std 25.3 W; occupancy fraction 1.00; time 17:45:00. The score indicates unusualness, not its cause."
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | Prediction message contract, currently `1.0`. |
| `event_id` | string (UUID) | UUIDv5 derived from source reading event ID and model version, making QoS 1 redeliveries idempotently identifiable. |
| `source_event_id` | string (UUID) | Reading event that produced this result. |
| `timestamp` | string | Original timezone-naive interval timestamp copied from the reading; it is not prediction-processing time. |
| `site_id`, `meter_id` | string | Identifiers copied from the reading; determine the prediction topic. |
| `model_version` | string | `iforest-{feature_schema_version}-{first 16 hex chars of the model artifact SHA-256}`. |
| `feature_schema_version` | string | Validated model input schema, currently `1.0.0`. |
| `anomaly` | boolean | Isolation Forest flag. It is an unlabelled review signal, not a confirmed fault. |
| `score`, `threshold` | number | Isolation Forest score and selected branch threshold; higher scores mean more unusual. |
| `model_variant` | string | `with_occupancy` or `without_occupancy`, indicating which estimator scored the reading. |
| `robust_anomaly`, `robust_score` | boolean, number | Interpretable robust-baseline flag and modified-z score. |
| `explanation` | string | Observed power, peak, variability, occupancy context, and time; it does not establish cause. |

`source_event_id` links the result to its input. Prediction event IDs are stable
for redeliveries of the same source event under the same model version. Replaying
readings with new source event IDs produces new prediction IDs. No prediction
timestamp timezone is inferred from the ECO source.

## Delivery behavior

- QoS 1 for reading and prediction topics. Consumers deduplicate by `event_id`
  because QoS 1 can deliver duplicates.
- Do not retain readings or predictions. A bounded local queue/store can be
  designed for disconnect recovery in the implementation phase.
- Retained status messages should include schema version, status, and timestamp;
  Last Will and Testament can report unexpected disconnection.
- The current inference service scores one 15-minute (900-second) interval per
  reading; it validates the required fields, schema version, timestamp semantics,
  interval duration, topic IDs, and nullable occupancy before scoring.
