# MQTT topic and message specification (preliminary)

Mosquitto runs on Computer 1. Set `MQTT_HOST` on both computers to Computer 1's
reachable hostname/IP; do not use `localhost` on Computer 2. Development port:
`1883` (plaintext on a trusted network only). Use TLS for untrusted networks.

## Topics

| Topic | Publisher | Subscriber | Purpose |
| --- | --- | --- | --- |
| `hostel/v1/readings/{site_id}/{meter_id}` | Computer 1 publisher/gateway | Computer 2 detector; Computer 1 persistence | Electricity observation stream. |
| `hostel/v1/predictions/{site_id}/{meter_id}` | Computer 2 detector | Computer 1 prediction receiver/dashboard service | Model score and anomaly decision for a reading/window. |
| `hostel/v1/status/{service_id}` | Each service | Monitoring clients | Health state; retained message is allowed. |

Identifiers are URL-safe and are not secrets. Do not publish occupant names or
other direct personal identifiers.

## Reading payload

UTF-8 JSON, one observation per message. Electrical fields need confirmation
against the meter and selected ECO export schema.

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "timestamp": "2026-11-05T10:15:30Z",
  "site_id": "hostel-a",
  "meter_id": "meter-01",
  "interval_seconds": 1,
  "power_w": 842.3,
  "occupancy": null,
  "occupancy_source": null
}
```

`timestamp` is ISO 8601 with timezone. `power_w` is watts over the observation
interval. Occupancy is null when unknown; otherwise use documented categories
such as `occupied`/`unoccupied` and identify the source. Missing readings do not
imply an occupancy label.

## Prediction payload

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "source_event_id": "uuid-of-reading-or-window-end-event",
  "timestamp": "2026-11-05T10:15:31Z",
  "site_id": "hostel-a",
  "meter_id": "meter-01",
  "model_version": "model-version-string",
  "anomaly": false,
  "score": 0.12,
  "threshold": 0.65
}
```

Score direction and meaning are model-specific and must remain consistent for a
model version. `source_event_id` links to a reading or window. Document score
semantics and threshold with each trained artifact.

## Delivery behavior

- QoS 1 for reading and prediction topics. Consumers deduplicate by `event_id`
  because QoS 1 can deliver duplicates.
- Do not retain readings or predictions. A bounded local queue/store can be
  designed for disconnect recovery in the implementation phase.
- Retained status messages should include schema version, status, and timestamp;
  Last Will and Testament can report unexpected disconnection.
- Confirm fields, windowing, occupancy meaning, and units against real exports
  and meter capabilities before freezing the contract.
