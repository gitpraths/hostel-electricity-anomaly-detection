# Project scripts

`check_local_pipeline.py` runs read-only readiness checks for the local Mac
demo. From the repository root, after the broker, Node-RED, SQLite receiver,
and inference service are ready, run:

```bash
.venv/bin/python -m scripts.check_local_pipeline
```

It checks the processed Parquet, model and metadata sidecar; performs an MQTT
CONNECT/CONNACK handshake without publishing; requests the dashboard page; and
checks SQLite integrity, foreign keys, and expected tables using a read-only
connection. It does not publish test messages or prove subscriber readiness.
Check the `Storage service ready` and `Inference service ready` logs separately.

Overrides are available with `--dataset`, `--model`, `--database`,
`--broker-host`, `--broker-port`, `--dashboard-url`, and `--timeout`. Defaults
also come from documented environment variables.
