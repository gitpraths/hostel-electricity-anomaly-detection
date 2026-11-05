# Hostel Electricity Anomaly Detection

A modular two-computer system for learning normal electricity use and flagging
unusual readings with occupancy and time context. ECO preprocessing and an
initial unsupervised anomaly detection baseline are implemented. The ECO
historical replay publisher is available under `iot/`, and `mqtt/` contains the
ML inference subscriber, prediction publisher, and MQTT-to-SQLite receiver.
A Node-RED Dashboard 2.0 flow is implemented for local live monitoring; Streamlit remains out of scope.

## Project status

- The supplied ETH Zurich ECO Household 1 export has been inspected and
  preprocessed. Raw files and the processed Parquet remain local and are ignored
  by Git; they must be obtained separately to reproduce analysis.
- Any future synthetic fixture will be clearly labelled and kept distinct from
  real ECO observations.
- Raw data, local configuration, secrets, databases, and generated model files
  are excluded from Git.

## Planned system

**Computer 1 (IoT/MQTT Mac):** Mosquitto broker, ECO historical replay
publisher, MQTT-to-SQLite receiver, and Node-RED Dashboard 2.0.

**Computer 2 (ML laptop):** selected ECO export preprocessing and training,
then a live MQTT reading subscriber and prediction publisher.

Both computers connect over a reachable network. Computer 2 uses Computer 1's
configured LAN hostname/IP to reach Mosquitto, never `localhost`. `localhost` is
appropriate only between services on the same computer.

See [architecture](docs/architecture.md), [MQTT specification](docs/mqtt-spec.md),
[Computer 1 setup](docs/setup-computer-1.md), [Computer 2 setup](docs/setup-computer-2.md),
the [roadmap](docs/roadmap.md), and [Node-RED dashboard instructions](docs/node-red-dashboard.md).

For the ECO Household 1 data workflow, see the [inspection report](docs/dataset-inspection.md),
[preprocessing instructions](docs/preprocessing.md), and [processed data dictionary](docs/data-dictionary.md).
The [Phase 3A EDA report](docs/eda-report.md) documents exploratory findings and feature recommendations.
Phase 3B model setup and design are in [ML setup](docs/setup-ml.md) and
[baseline details](docs/ml-baseline.md), with actual evaluation results in
[model evaluation](docs/model-evaluation.md).
For local ECO replay, see [the publisher instructions](iot/README.md) and the
[MQTT payload contract](docs/mqtt-spec.md).
For the inference service, see [MQTT service setup](mqtt/README.md). Local
validation uses loopback. Remote Computer 2 connectivity will require a later
network configuration phase; no LAN listener is enabled now.
Computer 1's SQLite receiver and schema are documented in [database setup](database/README.md);
the database file remains local and Git-ignored.
ML artifacts use validated feature schema `1.0.0`; keep the model and its JSON
metadata sidecar together. See the ML setup guide for branch-specific threshold
overrides and compatibility behavior.

## Configuration and dependencies

Install Python 3.11 or newer and use a virtual environment. The selected Python
stack is listed in `requirements.txt`; install Mosquitto separately on Computer
1. Copy `.env.example` to `.env` on each machine and configure `MQTT_HOST` as
Computer 1's reachable address. Never commit real credentials.

Install dependencies with `python -m pip install -r requirements.txt` inside
your virtual environment. Mosquitto is installed separately on Computer 1.

## Dataset handling

Keep authorized ECO originals in their existing raw-data locations, unchanged
and out of Git. The current Phase 2 workflow uses the supplied Household 1
export; additional household/export formats require inspection before ingestion
changes.

## Running the complete system

For local monitoring, start Mosquitto and run `python -m mqtt.storage_service`,
`python -m mqtt.inference_service`, and `python -m iot.publisher` in separate
terminals. Import the flow in `node-red/hostel-electricity-dashboard.json` and
open `http://127.0.0.1:1880/dashboard/hostel-electricity`. See
[Node-RED dashboard instructions](docs/node-red-dashboard.md). The broker and
services remain loopback-only; LAN setup is a separate deployment task.

## GitHub preparation

This workspace is a Git repository with the GitHub remote configured. Before
committing, review `git status` and `.gitignore`; raw/processed datasets, model
artifacts, local databases, environment files, and credentials must stay untracked.
