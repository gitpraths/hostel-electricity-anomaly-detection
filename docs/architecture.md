# Preliminary architecture

## Roles and data flow

```text
Selected ECO exports -> Computer 2 preprocessing/training -> local model artifact
                                                               |
Computer 1 publisher -> MQTT readings -> Computer 2 detector  |
Computer 1 broker     <- MQTT predictions <- Computer 2 detector
        |
        +-> later: persistence (SQLite pilot) -> dashboard/backend
```

Mosquitto runs on Computer 1. Both computers connect using a configured,
network-reachable hostname/IP and port. The broker host must be reachable from
Computer 2 and its firewall must permit MQTT traffic. Use TLS and authenticated
broker accounts beyond a trusted local network; do not expose an unauthenticated
broker to the public internet.

## Selected stack

| Concern | Choice | Reason |
| --- | --- | --- |
| Data processing | Python and pandas | Cross-platform tabular workflow; can ingest selected CSV exports without assuming their schema in advance. |
| Broker | Eclipse Mosquitto | Small, widely available broker with macOS, Linux, and Windows installation options. |
| Python MQTT client | Paho MQTT | Established Python publish/subscribe client. |
| Initial anomaly baseline | scikit-learn Isolation Forest | Unsupervised baseline while features and labels are assessed; validate features and threshold on real ECO exports before operational use. |
| Operational store | SQLite pilot | No separate server and included with Python; suitable for a single-host pilot. Consider PostgreSQL only if concurrency, scale, or remote operations require it. |
| Dashboard | Streamlit | Lightweight Python monitoring UI with few added dependencies; keep data access separate so the UI can change later. |
| Configuration | Environment variables and local `.env` for development | Keeps machine-specific addresses and credentials out of source; `.env` is ignored. |

The initial Python stack is listed in `requirements.txt`. Mosquitto is installed
as an operating-system service, and SQLite needs no external database server.
Add dependencies only when an implementation phase needs them.

## Service boundaries

- **Computer 1:** broker, reading source (simulator or meter gateway),
  prediction receiver, operational database, dashboard.
- **Computer 2:** ECO preprocessing, model training/evaluation, model loading,
  live prediction subscriber, prediction publisher.
- MQTT schemas in `mqtt-spec.md` define the machine-to-machine boundary.
- Model files are deployment artifacts transferred separately, not committed.
  Include model version, feature schema, preprocessing version, data selection,
  and threshold metadata.

## Dataset principles

No raw ECO data is included or presumed downloaded. Implement ingestion after
inspecting selected authorized exports. Preserve source files locally, exclude
them from Git, and document provenance in processed outputs. Any synthetic
interface fixture must be named and described as synthetic, never as ECO data.

## Reliability and security

- Use MQTT QoS 1 for reading and prediction events; deduplicate by `event_id`.
- Do not retain readings or predictions. Retained status messages are allowed.
- Keep credentials in local environment configuration or a secret manager.
- Restrict broker access with firewall rules; add broker authentication and TLS
  before use on an untrusted network.
- Include model/schema versions so incompatible deployments can be detected.
