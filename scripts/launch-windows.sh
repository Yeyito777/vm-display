#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VMROOT="/home/yeyito/Workspace/virtual-machines/windows"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export DWM_AI_TAG="${DWM_AI_TAG:-1}"
export DWM_AI_TOKEN="${DWM_AI_TOKEN:-vm:windows}"
export DWM_AI_LABEL="${DWM_AI_LABEL:-vm: windows}"
export DWM_AI_POLICY="${DWM_AI_POLICY:-autodelete-pristine}"
export SPICE_ADDR="${SPICE_ADDR:-127.0.0.1}"
export SPICE_PORT="${SPICE_PORT:-5930}"
URI="${1:-spice://$SPICE_ADDR:$SPICE_PORT}"

if ! pgrep -f 'qemu-system-x86_64.*process=exo-windows' >/dev/null 2>&1; then
  "$VMROOT/launch-vm-headless.sh"
fi

python3 - <<'PY'
import os, socket, sys, time
host = os.environ.get('SPICE_ADDR', '127.0.0.1')
port = int(os.environ.get('SPICE_PORT', '5930'))
deadline = time.time() + 20
while time.time() < deadline:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect((host, port))
    except OSError:
        time.sleep(0.2)
    else:
        s.close()
        sys.exit(0)
    finally:
        try:
            s.close()
        except Exception:
            pass
sys.exit('timed out waiting for spice listener')
PY

python3 -m vm_display --uri "$URI" --title "exo-windows" &
child=$!

if command -v xdotool >/dev/null 2>&1; then
  for _ in $(seq 1 100); do
    wid="$(xdotool search --name '^exo-windows$' 2>/dev/null | tail -n 1 || true)"
    if [ -n "$wid" ]; then
      xdotool windowmove "$wid" 0 19 >/dev/null 2>&1 || true
      break
    fi
    sleep 0.1
  done
fi

wait "$child"
