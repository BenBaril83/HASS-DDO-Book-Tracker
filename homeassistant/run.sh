#!/usr/bin/env bash
# Wrapper invoked by the Home Assistant command_line sensor.
#
# It must print ONLY the tracker's JSON to stdout (HA parses stdout as JSON),
# so keep any diagnostics on stderr. Adjust the two paths below to your setup.
set -euo pipefail

# Where you installed this project (contains the ddo_tracker package):
PROJECT_DIR="/config/ddo/HASS-DDO-Book-Tracker"

# Your credentials file (keep it out of any git repo!). See config.example.yaml.
export DDO_CONFIG="/config/ddo/config.yaml"

# Use the venv Python if you made one, otherwise the system python3.
PYTHON="${PROJECT_DIR}/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

cd "$PROJECT_DIR"
# Forward any arguments (e.g. `run.sh calendar -o ...`, `run.sh digest --send`).
# With no arguments, default to `json` so the command_line sensor works.
if [ "$#" -eq 0 ]; then
  exec "$PYTHON" -m ddo_tracker json
fi
exec "$PYTHON" -m ddo_tracker "$@"
