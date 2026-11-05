# Computer 2 setup — ML and dataset workstation

Computer 2 is the teammate's laptop. It will prepare selected ECO exports, train
and evaluate models, then subscribe to live readings and publish predictions.

1. Install Python 3.11 or newer and Git.
2. Clone the repository after it is created on GitHub.
3. Create/activate a Python virtual environment and install `requirements.txt`.
4. Copy `.env.example` to `.env`. Set `MQTT_HOST` to Computer 1's reachable LAN
   hostname/address. Never use `localhost` on Computer 2. Configure credentials
   after broker authentication is enabled.
5. Keep only selected, authorized ECO exports in the configured local data
   directory when received; never commit raw data.

## Data and model workflow

The full ECO archive is neither required nor assumed downloaded. Before
preprocessing, inspect the actual export's schema, timezone, sampling interval,
household/meter identifiers, occupancy labels, and provenance. Training steps
will be defined once the selected exports are available.

Transfer model artifacts outside Git with metadata describing model version,
feature schema, preprocessing version, training data selection, and threshold.

## Network and phase status

Computer 2 must be able to route to Computer 1's broker host and port. Confirm
those values with the Computer 1 owner. Never put credentials in shell history,
shared documents, or committed files.

The ML MQTT inference service is started with `python -m mqtt.inference_service`
from the repository root. It loads `ML_MODEL_PATH` and the matching metadata
sidecar, subscribes to the configured readings topic, and publishes predictions.
Set `ML_MQTT_HOST` to Computer 1's reachable LAN address on this computer; do
not use localhost here. See `mqtt/README.md` and `docs/mqtt-spec.md` for the
service contract. No database or dashboard is included in this phase.
