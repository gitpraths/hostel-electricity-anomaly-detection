# SQLite storage on Computer 1

`database.store.SQLiteStore` owns schema initialization, transactions, and
parameterized inserts. `mqtt.storage_service` handles MQTT connections and
payload validation, then calls the store. The ML service has no database
connection or credentials; predictions reach SQLite through MQTT on Computer 1.

## Run

From the repository root, install `requirements.txt`, ensure Mosquitto is
running locally, and start:

```bash
python -m mqtt.storage_service
```

By default it subscribes to readings and predictions on `127.0.0.1:1883` and
creates `database/hostel_electricity.sqlite3`. Override with environment
variables or CLI options:

```bash
python -m mqtt.storage_service \
  --database-path database/hostel_electricity.sqlite3 \
  --broker-host 127.0.0.1 --broker-port 1883
```

The database path can also be set with `DATABASE_PATH`; broker settings are
`STORAGE_MQTT_HOST`, `STORAGE_MQTT_PORT`, and `STORAGE_MQTT_CLIENT_ID`. The file
is ignored by Git. Do not copy it to Computer 2; the ML laptop needs only its
model artifact and broker connection settings.

## Tables and relationships

- `readings` stores the reading schema 2.0 fields without renaming, with
  `event_id` as its primary key and nullable `occupancy_fraction`.
- `predictions` stores prediction schema 1.0 fields, including `source_event_id`
  unchanged. `source_reading_event_id` is a nullable foreign key to
  `readings.event_id` and an index supports relationship lookup.
- If a prediction arrives first, it is stored with a null resolved foreign key.
  When its reading arrives, the same reading transaction links it if event,
  site, and meter identifiers agree. `source_event_id` remains preserved even
  while unresolved.
- Both tables have indexes for site/meter time queries and received time;
  prediction anomaly and source-event lookups are indexed.

The column sets are:

```text
readings(event_id, schema_version, timestamp, date, time_of_day,
  interval_start_second, hour, site_id, meter_id, interval_seconds,
  powerallphases_mean_w, powerallphases_max_w, powerallphases_std_w,
  occupancy_fraction, source, received_at)

predictions(event_id, schema_version, source_event_id,
  source_reading_event_id, timestamp, site_id, meter_id, model_version,
  feature_schema_version, anomaly, score, threshold, model_variant,
  robust_anomaly, robust_score, explanation, received_at)
```

## Delivery behavior

SQLite uses explicit `BEGIN IMMEDIATE` transactions and rolls back on failure.
Unique event IDs plus `ON CONFLICT(event_id) DO NOTHING` make QoS 1 redelivery
idempotent without overwriting prior data. The receiver uses Paho manual
acknowledgements with a persistent client session: valid messages and
duplicates are acknowledged only after the transaction succeeds. Malformed
messages are logged and acknowledged to avoid poison-message loops. A database
failure is logged and left unacknowledged for broker redelivery. This provides
at-least-once delivery within broker/session limits; SQLite and MQTT are not a
single distributed transaction, and there is no separate dead-letter queue.

The default broker address is loopback. Network exposure and Computer 2 access
are intentionally not configured in this phase.
