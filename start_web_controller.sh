#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"
source robot_ports.env
python_bin="$project_dir/.venv/bin/python"
controller_lock="/tmp/xlerobot-controller.lock"

# Replace an existing XLeRobot web controller cleanly. The identity check
# prevents this script from shutting down an unrelated service on port 8765.
set +e
"$python_bin" -c '
import json, sys, urllib.request
base = "http://127.0.0.1:8765"
try:
    state = json.load(urllib.request.urlopen(base + "/api/state", timeout=1))
except Exception:
    sys.exit(1)
if not isinstance(state.get("positions"), dict) or not isinstance(state.get("targets"), dict):
    sys.exit(2)
request = urllib.request.Request(base + "/api/shutdown", data=b"", method="POST")
urllib.request.urlopen(request, timeout=2).read()
' >/dev/null 2>&1
existing_status=$?
set -e

if [[ "$existing_status" -eq 0 ]]; then
  echo "Existing XLeRobot controller found; requested safe replacement."
elif [[ "$existing_status" -eq 2 ]]; then
  echo "Port 8765 is occupied by a service that is not XLeRobot; refusing to stop it." >&2
  exit 1
elif "$python_bin" -c 'import socket; s=socket.create_connection(("127.0.0.1",8765),.5); s.close()' 2>/dev/null; then
  echo "Port 8765 is occupied but did not answer as XLeRobot; refusing to start another controller." >&2
  exit 1
fi

# Wait until the old process has completed its cleanup and released the
# hardware lock. Do not bypass the lock or kill an unknown process.
lock_ready=0
for _ in {1..100}; do
  if flock -n "$controller_lock" true 2>/dev/null; then
    lock_ready=1
    break
  fi
  sleep 0.1
done
if [[ "$lock_ready" -ne 1 ]]; then
  echo "Existing XLeRobot controller did not release $controller_lock within 10 seconds." >&2
  exit 1
fi

for port in "$XLEROBOT_LEFT_HEAD_PORT" "$XLEROBOT_RIGHT_WHEELS_PORT"; do
  [[ -r "$port" && -w "$port" ]] || { echo "Missing robot controller: $port" >&2; exit 1; }
done
"$python_bin" "$project_dir/xlerobot_web.py" &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM

ready=0
for _ in {1..100}; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "Web controller exited during startup." >&2
    wait "$server_pid"
    exit $?
  fi
  if "$python_bin" -c \
    'import socket; s=socket.create_connection(("127.0.0.1", 8765), 0.2); s.close()' \
    2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.1
done

if [[ "$ready" -ne 1 ]]; then
  echo "Web controller did not become ready at http://127.0.0.1:8765/" >&2
  exit 1
fi

url="http://127.0.0.1:8765/"
echo "Web controller ready: $url"
if command -v google-chrome >/dev/null 2>&1; then
  google-chrome "$url" >/tmp/xlerobot-chrome.log 2>&1 &
  disown
else
  echo "Chrome was not found; open this address manually: $url" >&2
fi
wait "$server_pid"
