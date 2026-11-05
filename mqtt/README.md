# MQTT ML inference service

`mqtt.inference_service` subscribes to reading events, validates each message
against reading schema `2.0`, maps its raw model inputs into a one-row DataFrame,
calls the existing `AnomalyDetector.predict()` interface, and publishes the
result on the matching prediction topic. It loads the saved model and metadata
through `AnomalyDetector.load()`; it does not train or alter the model.

## Run locally on the Mac

Install project dependencies, ensure the trained model and matching JSON
metadata sidecar exist under `models/`, and run the broker locally. The service
uses loopback by default:

```bash
python -m mqtt.inference_service
```

Or configure explicitly:

```bash
python -m mqtt.inference_service \
  --model models/eco_household_1_iforest.joblib \
  --broker-host 127.0.0.1 --broker-port 1883 \
  --readings-topic 'hostel/v1/readings/+/+' \
  --client-id hostel-ml-inference
```

The service subscribes at QoS 1 to `hostel/v1/readings/+/+` and publishes
non-retained QoS 1 results at
`hostel/v1/predictions/{site_id}/{meter_id}`. Invalid readings are logged and
skipped. Prediction publish failures are logged and counted. Ctrl+C disconnects
cleanly.

## Configure Computer 2

Set `ML_MQTT_HOST` to Computer 1's reachable LAN hostname/IP on the teammate's
laptop. Do not use `127.0.0.1` or `localhost` there: the model service runs on
Computer 2 while the broker runs on Computer 1. Set `ML_MODEL_PATH` to the
transferred model artifact and keep its matching `.metadata.json` sidecar next
to it. `ML_MQTT_PORT`, `ML_READINGS_TOPIC`, and `ML_MQTT_CLIENT_ID` can also be
set in `.env`; credentials are read from `MQTT_USERNAME` and `MQTT_PASSWORD`.

During this phase, the service is exercised locally on one Mac with both broker
and service using loopback. This is a development test; it does not change the
intended two-computer boundary.

## Contract and reliability

See `docs/mqtt-spec.md` for reading/prediction schemas, timestamp semantics,
nullable occupancy behavior, score direction, event IDs, and QoS. Predictions
carry the source reading event ID and a model version derived from the model
artifact hash. Prediction IDs are stable for QoS redelivery of a reading under
the same model. The service rejects unsupported reading schema versions and
topic/payload identifier mismatches. It does not persist messages or predictions;
a durable queue is outside this phase.

## Tests

```bash
python -m pytest -q
```

The service tests use a fake detector and mocked MQTT client; they require
neither a running broker nor the ECO Parquet file.
