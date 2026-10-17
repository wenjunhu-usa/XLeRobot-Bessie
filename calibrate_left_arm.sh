#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$project_dir/robot_ports.env"
mkdir -p "$project_dir/calibration"

exec "$project_dir/.venv/bin/lerobot-calibrate" \
  --robot.type=so101_follower \
  --robot.id=xlerobot_left_arm \
  --robot.port="$XLEROBOT_LEFT_HEAD_PORT" \
  --robot.calibration_dir="$project_dir/calibration"

