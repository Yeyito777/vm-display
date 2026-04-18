#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export DWM_AI_TAG="${DWM_AI_TAG:-1}"
export DWM_AI_TOKEN="${DWM_AI_TOKEN:-vm:windows}"
export DWM_AI_LABEL="${DWM_AI_LABEL:-vm: windows}"
export DWM_AI_POLICY="${DWM_AI_POLICY:-autodelete-pristine}"
exec python3 -m vm_display --uri "${1:-spice://127.0.0.1:5930}" --title "exo-windows"
