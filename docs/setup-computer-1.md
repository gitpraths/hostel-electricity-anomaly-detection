# Computer 1 setup — IoT, MQTT, and monitoring host

Computer 1 is the Mac. It hosts Mosquitto, the ECO historical replay publisher,
the Phase 4E SQLite storage receiver, and the Phase 4F Node-RED Dashboard 2.0.

1. Install Python 3.11 or newer and Git.
2. Install Eclipse Mosquitto on macOS using its official installation method.
3. Clone the repository after it is created on GitHub.
4. Create/activate a Python virtual environment and install `requirements.txt`.
5. Copy `.env.example` to `.env`. Keep `.env` private and untracked. For local
   Phase 4E use `STORAGE_MQTT_HOST=127.0.0.1` and
   `DATABASE_PATH=database/hostel_electricity.sqlite3`.
6. Keep Mosquitto bound to loopback for this phase; do not open a LAN listener
   or firewall port. Remote Computer 2 connectivity is not configured yet.

## Local service commands

Start the database receiver from the repository root after Mosquitto is running:

```bash
python -m mqtt.storage_service
```

The receiver creates the configured SQLite file, subscribes to reading and
prediction topics, and stores them independently of the ML service. The database
is not shared with Computer 2. See `database/README.md` for schema and
transaction behavior, and `roadmap.md` for remaining work.

## Node-RED dashboard

Node-RED and Dashboard 2.0 must be installed separately. Import `node-red/hostel-electricity-dashboard.json` as a new flow from the editor, deploy that tab, and open `http://127.0.0.1:1880/dashboard/hostel-electricity`. Keep Node-RED and Mosquitto on localhost for this phase. See [dashboard guide](node-red-dashboard.md) for widget behavior and the three-terminal replay test.
