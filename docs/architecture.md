# Preliminary architecture

## Roles and data flow

```text
Computer 1 (Mac)
  ECO replay publisher ──┐
  Node-RED dashboard ────┼── MQTT broker (127.0.0.1:1883 in local phase)
  SQLite receiver ───────┘           │
                                     ├── readings ──> Computer 2 ML service
                                     └── predictions <── Computer 2 ML service

Node-RED subscribes to readings and predictions directly. SQLite stores both
streams independently; the dashboard does not access the database.
```

Mosquitto runs on Computer 1. For the current local phases it remains on
loopback (`127.0.0.1:1883`); no LAN listener or firewall opening is added. The
two-computer network configuration remains future deployment work. Before that
work, plan authenticated broker accounts and TLS for untrusted networks; never
expose an unauthenticated broker to the public internet.

## Selected stack

| Concern | Choice | Reason |
| --- | --- | --- |
| Data processing | Python and pandas | Cross-platform tabular workflow; can ingest selected CSV exports without assuming their schema in advance. |
| Broker | Eclipse Mosquitto | Small, widely available broker with macOS, Linux, and Windows installation options. |
| Python MQTT client | Paho MQTT | Established Python publish/subscribe client. |
| Initial anomaly baseline | scikit-learn Isolation Forest | Unsupervised baseline while features and labels are assessed; validate features and threshold on real ECO exports before operational use. |
| Operational store | SQLite pilot | No separate server and included with Python; suitable for a single-host pilot. Consider PostgreSQL only if concurrency, scale, or remote operations require it. |
| Dashboard | Node-RED Dashboard 2.0 | Uses the existing Node-RED install and consumes MQTT directly; keeps the live UI separate from SQLite and the ML service. |
| Configuration | Environment variables and local `.env` for development | Keeps machine-specific addresses and credentials out of source; `.env` is ignored. |

The Python stack is listed in `requirements.txt`. Mosquitto is installed as an
operating-system service, and SQLite needs no external database server. Node-RED
and Dashboard 2.0 are installed separately from Python dependencies.

## Service boundaries

- **Computer 1:** broker, Phase 4C historical ECO replay simulator, Phase 4E
  SQLite storage receiver, and Phase 4F Node-RED Dashboard 2.0 subscriber.
- **Computer 2:** ECO preprocessing, model training/evaluation, model loading,
  reading subscriber and prediction publisher (`mqtt.inference_service`).
- **Local Phase 4D validation:** broker, reading publisher, and inference
  service can run on the developer Mac via loopback. This is for testing only;
  the ML service remains portable to Computer 2 and must then use Computer 1's
  reachable LAN address rather than localhost.
- MQTT schemas in `mqtt-spec.md` define the machine-to-machine boundary. The
  live dashboard subscribes directly to both topics; it does not query SQLite.
- Computer 2 sends predictions only over MQTT; it does not open or receive
  credentials for Computer 1's SQLite file.
- Model files are deployment artifacts transferred separately, not committed.
  Include model version, feature schema, preprocessing version, data selection,
  and threshold metadata.

## Dataset principles

No raw ECO data is included or presumed downloaded. Implement ingestion after
inspecting selected authorized exports. Preserve source files locally, exclude
them from Git, and document provenance in processed outputs. Any synthetic
interface fixture must be named and described as synthetic, never as ECO data.

## Reliability and security

- Use MQTT QoS 1 for reading and prediction events; the storage receiver uses
  manual acknowledgements after SQLite commit and deduplicates by `event_id`.
- Do not retain readings or predictions. Retained status messages are allowed.
- Keep credentials in local environment configuration or a secret manager.
- Restrict broker access with firewall rules; add broker authentication and TLS
  before use on an untrusted network.
- Include model/schema versions so incompatible deployments can be detected.
