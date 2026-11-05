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
the `-1` sentinel. New household/export formats need their own inspection before
ingestion changes.

## Phase 3A — Exploratory data analysis (complete)

See `eda-report.md` and reproducible figures under `reports/figures/` for
verified distributions, context analysis, and the chronological split proposal.

## Phase 3B — Unsupervised baseline (implemented; review required)

`ml/` provides date-grouped training-only Isolation Forest variants,
training-derived cutoffs, a contextual robust baseline, inference, and
unlabelled chronological evaluation. See `model-evaluation.md`. No confirmed
anomaly labels are available; flags remain review signals rather than confirmed
faults.

## Phase 4 — MQTT broker and message clients (local implementation complete)

Phases 4A–4B established the broker and local communication; Phase 4C adds the
historical ECO replay publisher; Phase 4D adds the ML inference subscriber and
prediction publisher. A local Mac end-to-end smoke test passed. The two-computer
deployment still needs validation when Computer 2 is available. No durable
queue, prediction receiver, database, or dashboard is included.

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
