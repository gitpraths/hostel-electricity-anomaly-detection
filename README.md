# Hostel Electricity Anomaly Detection

A modular two-computer system for learning normal electricity use and flagging
unusual readings with occupancy and time context. This is the Phase 1 foundation:
architecture and operating documentation only. There is no running model, MQTT
client, database, backend, or dashboard yet.

## Project status

- ETH Zurich's ECO Electricity Consumption & Occupancy dataset is the intended
  source. Selected exports are being arranged; no data is bundled or presumed
  available locally.
- Any future synthetic fixture will be clearly labelled and kept distinct from
  real ECO observations.
- Raw data, local configuration, secrets, databases, and generated model files
  are excluded from Git.

## Planned system

**Computer 1 (IoT/MQTT Mac):** Mosquitto broker, later a reading
publisher/simulator, prediction receiver, operational storage, and dashboard.

**Computer 2 (ML laptop):** selected ECO export preprocessing and training,
then a live MQTT reading subscriber and prediction publisher.

Both computers connect over a reachable network. Computer 2 uses Computer 1's
configured LAN hostname/IP to reach Mosquitto, never `localhost`. `localhost` is
appropriate only between services on the same computer.

See [architecture](docs/architecture.md), [MQTT specification](docs/mqtt-spec.md),
[Computer 1 setup](docs/setup-computer-1.md), [Computer 2 setup](docs/setup-computer-2.md),
and the [roadmap](docs/roadmap.md).

For the ECO Household 1 data workflow, see the [inspection report](docs/dataset-inspection.md),
[preprocessing instructions](docs/preprocessing.md), and [processed data dictionary](docs/data-dictionary.md).

## Configuration and dependencies

Install Python 3.11 or newer and use a virtual environment. The selected Python
stack is listed in `requirements.txt`; install Mosquitto separately on Computer
1. Copy `.env.example` to `.env` on each machine and configure `MQTT_HOST` as
Computer 1's reachable address. Never commit real credentials.

This phase does not install or execute these packages; application entry points
will be added in later phases.

## Dataset handling

Place only authorized selected ECO exports under `data/raw/eco/` when received.
Keep originals unchanged and out of Git. Record each export's household, date
range, signals, provenance, and transformations. Preprocessing will follow the
actual export format; no full archive or particular file layout is assumed.

## Running the complete system

End-to-end commands will be documented when services are implemented. For now,
use the per-computer setup documents to prepare the environments and network
configuration.

## GitHub preparation

This workspace is not initialized as a Git repository yet. Suggested first
commit commands are included in the Phase 1 handoff. Review `.gitignore` and
check staged files before committing.
