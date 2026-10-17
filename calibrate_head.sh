#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$project_dir/calibration"
exec "$project_dir/.venv/bin/python" "$project_dir/calibrate_head.py"
