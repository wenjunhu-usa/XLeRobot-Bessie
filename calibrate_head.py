#!/usr/bin/env python3
from pathlib import Path

from lerobot.robots.xlerobot.sub_robots.xlerobot_mount import (
    XLeRobotMount,
    XLeRobotMountConfig,
)


PROJECT_DIR = Path(__file__).resolve().parent
PORTS = {}
for line in (PROJECT_DIR / "robot_ports.env").read_text().splitlines():
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        PORTS[key] = value


config = XLeRobotMountConfig(
    id="xlerobot_head",
    port=PORTS["XLEROBOT_LEFT_HEAD_PORT"],
    calibration_dir=PROJECT_DIR / "calibration",
    pan_motor_id=7,
    tilt_motor_id=8,
)
head = XLeRobotMount(config)

try:
    head.bus.connect()
    head.calibrate()
finally:
    if head.bus.is_connected:
        head.bus.disable_torque()
        head.bus.disconnect(disable_torque=True)

