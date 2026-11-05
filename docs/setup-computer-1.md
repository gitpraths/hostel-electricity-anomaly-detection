# Computer 1 setup — complete single-Mac workflow

Computer 1 hosts the local-only Mosquitto broker, Node-RED Dashboard 2.0, the
MQTT-to-SQLite receiver, ML inference, and the ECO historical replay publisher.
All commands below run on the same Mac. Do not change the Mosquitto listener or
firewall for this phase.

## One-time setup

1. Install Python 3.11+, Git, Homebrew Mosquitto, Node.js, Node-RED, and the
   `@flowfuse/node-red-dashboard` palette package using their official install
   instructions.
2. Clone this repository and enter its root directory:

   ```bash
   git clone https://github.com/gitpraths/hostel-electricity-anomaly-detection.git
   cd hostel-electricity-anomaly-detection
   ```
3. Create a virtual environment and install Python dependencies:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install -r requirements.txt
   ```

4. Ensure the existing processed Parquet, trained model, and model metadata
   sidecar are present at the paths configured in `.env.example`. This runbook
   does not download ECO data or retrain the model.
5. Optionally copy `.env.example` to `.env` and edit local paths/settings. Never
   commit `.env` or credentials. Python does not load `.env` automatically; each
   service terminal must source it as shown below.
6. Ensure the Node-RED user directory contains the deployed flow and Dashboard
   2.0 package. For first-time setup, follow
   [the Node-RED dashboard guide](node-red-dashboard.md).

## Start the local pipeline

Use a separate terminal for each long-running process. Start in this order and
wait for the readiness indication before moving to the next terminal.

**Terminal 1 — Mosquitto broker** (skip if the existing local broker is already
running; never start a second process on port 1883):

```bash
cd ~/hostel-electricity-anomaly-detection
mosquitto -c "$(brew --prefix)/etc/mosquitto/mosquitto.conf" -v
```

Confirm its configuration binds only `127.0.0.1:1883`. Do not replace it with a
default/network listener.

**Terminal 2 — Node-RED** (skip if it is already running):

```bash
node-red --userDir "$HOME/.node-red" --settings "$HOME/.node-red/settings.js" -D uiHost=127.0.0.1
```

This uses the existing user directory and configured `flows.json`; the command
line override binds the editor/dashboard to loopback. Do not start a second
copy if port 1880 is occupied. On startup Node-RED loads its saved flow file
automatically; an editor Deploy is not required to load that file. The
dashboard URL is [http://127.0.0.1:1880/dashboard/hostel-electricity](http://127.0.0.1:1880/dashboard/hostel-electricity).

In each remaining service terminal, first run:

```bash
cd ~/hostel-electricity-anomaly-detection
if [ -f .env ]; then set -a; source .env; set +a; fi
```

**Terminal 3 — SQLite receiver:**

```bash
.venv/bin/python -m mqtt.storage_service
```

Wait for `Storage service ready`. SQLite is created if needed; keep the same
`DATABASE_PATH` across restarts.

**Terminal 4 — ML inference:**

```bash
.venv/bin/python -m mqtt.inference_service
```

Wait for `Inference service ready`. It loads the model and metadata before
subscribing.

**Terminal 5 — readiness check, then publisher:**

```bash
.venv/bin/python -m scripts.check_local_pipeline
```

All checks should say PASS. The check validates the Parquet, model and sidecar;
performs MQTT CONNECT/CONNACK without publishing; requests the dashboard page;
and checks SQLite integrity, foreign keys, and expected tables through a
read-only connection. It cannot prove the subscribers are active, so also
require both `... service ready` log lines above.

For a 10-reading demonstration:

```bash
.venv/bin/python -m iot.publisher --replay-delay 0.01 --max-records 10
```

For the full 7,584-interval replay at a 0.25-second delay:

```bash
.venv/bin/python -m iot.publisher --replay-delay 0.25
```

The full replay takes about 32 minutes. This is historical ECO data replay, not
a live meter, and it must start last after all consumers are ready. Configure
the rate with `ECO_REPLAY_INTERVAL_SECONDS` or `--replay-delay`.

## Shutdown and persistence

Let the publisher finish or press Ctrl-C first. Then Ctrl-C the inference and
storage terminals, stop Node-RED gracefully in its terminal, and stop Mosquitto
last. Avoid force-killing processes so SQLite closes cleanly and MQTT clients
disconnect normally.

SQLite readings and predictions persist in its database file across service
and Node-RED restarts. SQLite uses WAL mode; keep its `-wal` and `-shm` files
beside the database while it is open, and do not copy the database mid-write.
Dashboard chart points, correlation caches, and the 20-row anomaly view live in
memory and reset when Node-RED restarts. Node-RED reloads its configured flow
file at startup, so no editor Deploy is needed just to load saved flows. UI
history reset is expected and does not delete SQLite history.

## Troubleshooting

- `Address already in use`: the broker or Node-RED is probably already running;
  do not launch a second instance.
- MQTT check fails: confirm the broker is listening on `127.0.0.1:1883` and
  service-specific host/port variables point there.
- Storage/inference readiness times out: inspect that terminal's error and
  verify its model/database path and MQTT connection.
- Dashboard check fails: open the URL in a browser and inspect the Node-RED
  terminal. Process presence alone does not prove dashboard readiness.
- Missing dataset or model: obtain authorized local artifacts separately; this
  runbook never downloads or fabricates them.

See [database setup](../database/README.md), [MQTT services](../mqtt/README.md),
and [dashboard details](node-red-dashboard.md) for component contracts.
