# Development roadmap

## Phase 1 — Project foundation (complete)

Document stack, two-computer architecture, MQTT contract, setup, Git hygiene,
and roadmap. No runtime services are implemented.

## Phase 2 — ECO export inspection and preprocessing

**Phase 2A and 2B complete for the supplied Household 1 export.** The actual
CSV layout is documented in `dataset-inspection.md`; reusable validation and
15-minute aggregation live in `data/preprocess_eco.py`. The generated
`dataset-validation-report.md` records the actual run. The initial processed
dataset uses 79 clean matched days and excludes six matching days containing
the `-1` sentinel. No model has been trained. New household/export formats need
their own inspection before ingestion changes.

## Phase 3 — Model baseline and evaluation (next; requires approval)

Train an Isolation Forest baseline on normal training-period behavior, compare
appropriate baselines, define score semantics and thresholds, and evaluate with
temporal splits and suitable metrics. Save model metadata and reproducible
training configuration.

## Phase 4 — MQTT broker and message clients

Configure Mosquitto on Computer 1 with access control. Implement its reading
publisher/simulator and Computer 2 prediction subscriber/publisher against the
documented schema, QoS, reconnect behavior, and duplicate handling.

## Phase 5 — Persistence and service boundary

Add a data-access layer and SQLite storage on Computer 1 for readings,
predictions, and alert state. Keep transport and storage logic separate from the
model and UI. Reassess PostgreSQL only if operating needs justify it.

## Phase 6 — Dashboard and alerts

Build the Streamlit dashboard for readings, occupancy context, predictions, and
anomaly history. Agree on notification channels and alert deduplication before
enabling external notifications.

## Phase 7 — Reproducible deployment and handoff

Document complete start/stop commands, network/firewall configuration, secrets,
model artifact handoff, and recovery. Validate a clean setup on macOS and the
teammate's OS with authorized data and only explicitly labelled synthetic
interface fixtures when needed.
