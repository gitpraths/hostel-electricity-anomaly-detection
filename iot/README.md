# ECO historical MQTT publisher

`iot.publisher` replays processed Household 1 ECO interval records to the
readings topic. It is a historical-data simulator, not a live physical meter.
It publishes QoS 1, non-retained messages in chronological order and stops on a
delivery failure instead of silently skipping a record.

## Install and configure

From the repository root, install the existing dependencies and activate the
virtual environment. Configure with CLI options or environment variables shown
in `.env.example`. To use that example locally in a POSIX shell:

```bash
set -a
source .env
set +a
```

The default broker is local loopback `127.0.0.1:1883`; the publisher does not
open a listener or expose the broker. Do not set credentials in source control.
If broker authentication is enabled, `MQTT_USERNAME` and `MQTT_PASSWORD` are
read from the environment.

## Run

Default replay pacing is 0.25 seconds between messages:

```bash
python -m iot.publisher
```

Replay a small sample quickly for a local demonstration:

```bash
python -m iot.publisher --max-records 10 --replay-delay 0.01
```

Choose a dataset, broker, topic identifiers, and interval explicitly:

```bash
python -m iot.publisher \
  --dataset data/processed/eco_household_1_15min.parquet \
  --broker-host 127.0.0.1 --broker-port 1883 \
  --site-id hostel-a --meter-id eco-household-01 \
  --replay-delay 0.25 --max-records 100
```

CLI options override environment values. Available settings are `ECO_DATASET_PATH`,
`ECO_MQTT_HOST`, `ECO_MQTT_PORT`, `ECO_SITE_ID`, `ECO_METER_ID`,
`ECO_REPLAY_INTERVAL_SECONDS`, `ECO_MAX_RECORDS`, and `ECO_MQTT_CLIENT_ID`.
Generic `MQTT_HOST` and `MQTT_PORT` are fallback broker settings.

The topic is `hostel/v1/readings/{site_id}/{meter_id}`. See
`docs/mqtt-spec.md` for the complete version 2.0 JSON contract and mapping to
the current model's raw input fields. The publisher includes unknown occupancy
as JSON `null`; the future subscriber must preserve it as missing.

## Failure and shutdown behavior

Connection failures and QoS 1 publish/acknowledgement failures are logged and
cause a non-zero exit. The publisher stops at the failed event; it does not
claim later records were sent. Ctrl+C stops replay and disconnects the client
cleanly. Logs report progress every 100 messages and at completion.

## Tests

```bash
python -m pytest -q
```

Publisher tests use mocked MQTT clients and small synthetic interface fixtures;
they do not require a running broker or the local ECO dataset.
