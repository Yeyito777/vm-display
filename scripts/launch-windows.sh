#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export DWM_AI_TAG="${DWM_AI_TAG:-1}"
export DWM_AI_TOKEN="${DWM_AI_TOKEN:-vm:windows}"
export DWM_AI_LABEL="${DWM_AI_LABEL:-vm: windows}"
export DWM_AI_POLICY="${DWM_AI_POLICY:-autodelete-pristine}"
export SPICE_ADDR="${SPICE_ADDR:-127.0.0.1}"
export SPICE_PORT="${SPICE_PORT:-5930}"
URI="${1:-spice://$SPICE_ADDR:$SPICE_PORT}"
VM_NAME="${VM_NAME:-windows}"
VM_CMD="${VM_CMD:-vm}"
LOCKFILE="${XDG_RUNTIME_DIR:-/tmp}/vm-display-windows.lock"

client_pid() {
  ps -eo pid=,args= | awk '/python3( .*)?-m vm_display/ && /--title exo-windows/ && $0 !~ /awk/ {print $1; exit}'
}

vm_status_text() {
  "$VM_CMD" status "$VM_NAME" 2>/dev/null || true
}

vm_qemu_pid() {
  vm_status_text | awk -F': *' '/^[[:space:]]*QEMU:/{print $2; exit}'
}

vm_running() {
  vm_status_text | grep -Eq '^[[:space:]]*State:[[:space:]]*running'
}

spice_ready_for_pid() {
  local pid="${1:-}"
  [ -n "$pid" ] || return 1
  [ "$pid" != "down" ] || return 1
  ss -ltnp 2>/dev/null | grep -F ":$SPICE_PORT" | grep -F "pid=$pid" >/dev/null 2>&1
}

if ! command -v "$VM_CMD" >/dev/null 2>&1; then
  echo "[vm-display] $VM_CMD not found in PATH" >&2
  exit 1
fi

exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "[vm-display] windows wrapper already running" >&2
  exit 0
fi

if [ -n "$(client_pid)" ]; then
  echo "[vm-display] exo-windows client already running" >&2
  exit 0
fi

if ! vm_running; then
  "$VM_CMD" start "$VM_NAME" --headless >/dev/null
fi

QEMU_PID=""
DEADLINE=$((SECONDS + 30))
while (( SECONDS < DEADLINE )); do
  QEMU_PID="$(vm_qemu_pid)"
  if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
    if spice_ready_for_pid "$QEMU_PID"; then
      break
    fi
  fi
  sleep 0.2
done

if [ -z "$QEMU_PID" ] || ! kill -0 "$QEMU_PID" 2>/dev/null; then
  echo "[vm-display] $VM_NAME VM is not running" >&2
  exit 1
fi

if ! spice_ready_for_pid "$QEMU_PID"; then
  echo "[vm-display] timed out waiting for SPICE on $SPICE_ADDR:$SPICE_PORT for QEMU pid $QEMU_PID" >&2
  exit 1
fi

if [ -n "$(client_pid)" ]; then
  echo "[vm-display] exo-windows client already running" >&2
  exit 0
fi

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
