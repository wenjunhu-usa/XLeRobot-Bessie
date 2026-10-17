#!/usr/bin/env python3
import json
from pathlib import Path

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus


PROJECT_DIR = Path(__file__).resolve().parent
PORTS = {}
for line in (PROJECT_DIR / "robot_ports.env").read_text().splitlines():
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        PORTS[key] = value

port = PORTS["XLEROBOT_RIGHT_WHEELS_PORT"]
motors = {
    "base_left_wheel": Motor(9, "sts3215", MotorNormMode.RANGE_M100_100),
    "base_right_wheel": Motor(10, "sts3215", MotorNormMode.RANGE_M100_100),
}
calibration = {
    name: MotorCalibration(
        id=motor.id,
        drive_mode=0,
        homing_offset=0,
        range_min=0,
        range_max=4095,
    )
    for name, motor in motors.items()
}

bus = FeetechMotorsBus(port=port, motors=motors)
try:
    bus.connect()
    bus.disable_torque()
    bus.write_calibration(calibration)

    output_dir = PROJECT_DIR / "calibration"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "xlerobot_wheels.json"
    output_path.write_text(
        json.dumps(
            {
                name: {
                    "id": cal.id,
                    "drive_mode": cal.drive_mode,
                    "homing_offset": cal.homing_offset,
                    "range_min": cal.range_min,
                    "range_max": cal.range_max,
                }
                for name, cal in calibration.items()
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Wheel calibration saved to {output_path}")
finally:
    if bus.is_connected:
        bus.disable_torque()
        bus.disconnect(disable_torque=True)

