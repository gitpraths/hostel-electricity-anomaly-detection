# Computer 1 setup — IoT, MQTT, and monitoring host

Computer 1 is the Mac. It will host Mosquitto and later the reading
publisher/simulator, prediction receiver, storage, and dashboard.

1. Install Python 3.11 or newer and Git.
2. Install Eclipse Mosquitto on macOS using its official installation method.
3. Clone the repository after it is created on GitHub.
4. Create/activate a Python virtual environment and install `requirements.txt`.
5. Copy `.env.example` to `.env`. Set `MQTT_HOST` to this Mac's reachable LAN
   hostname/address. Set credentials when broker authentication is configured.
   Keep `.env` private and untracked.
6. Configure the firewall to permit broker connections from the trusted network
   or Computer 2 only. Add TLS before connecting across untrusted networks.

## Network address

Find the current reachable hostname/address in macOS network settings or the
router. Configure it in each machine's `.env`, not in source. A stable DHCP
reservation or LAN DNS name is preferable because addresses can change.

## Phase 1 status

This phase adds documentation/configuration examples only. There is no
publisher, broker configuration, database, backend, or dashboard command to run.
See `roadmap.md` for implementation order.
