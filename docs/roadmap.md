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

## Phase 4A–4F — MQTT, local storage, and live dashboard (local implementation complete)

Phases 4A–4B established the broker and local communication; Phase 4C adds the
historical ECO replay publisher; Phase 4D adds the ML inference subscriber and
prediction publisher; Phase 4E adds the Computer 1 MQTT receiver and SQLite
storage. The receiver stores QoS 1 messages transactionally, deduplicates by
event ID, and resolves out-of-order prediction-to-reading links. Broker and
services remain local-loopback only. Phase 4F adds an importable Node-RED Dashboard 2.0
flow for local live monitoring; the two-computer deployment still needs validation
when Computer 2 is available. Streamlit is not included.

## Phase 5 — Operational deployment and hardening

Validate the two-computer broker/service boundary when Computer 2 is available.
Decide on broker authentication/TLS, listener binding, firewall policy, Node-RED
access security, SQLite backup/retention, migration, and recovery. Keep transport
and storage separate from the model and UI; reassess PostgreSQL only if operating
needs justify it. The local Node-RED flow has no durable dashboard state or
historical database API.

## Phase 6 — Optional dashboard extensions and alerts

Assess whether persistent historical views or Streamlit add value beyond the
Node-RED live dashboard. Agree on notification channels and alert deduplication
before enabling external notifications.

## Phase 7 — Reproducible deployment and handoff

Document complete start/stop commands, network/firewall configuration, secrets,
model artifact handoff, and recovery. Validate a clean setup on macOS and the
teammate's OS with authorized data and only explicitly labelled synthetic
interface fixtures when needed.
