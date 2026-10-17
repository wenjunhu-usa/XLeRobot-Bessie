#!/usr/bin/env python3
from local_config import get_port
import json

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode


names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
saved = json.load(open("calibration/xlerobot_right_arm.json"))
bus = FeetechMotorsBus(
    port=get_port("XLEROBOT_RIGHT_WHEELS_PORT"),
    motors={
        name: Motor(index + 1, "sts3215", MotorNormMode.RANGE_0_100 if name == "gripper" else MotorNormMode.DEGREES)
        for index, name in enumerate(names)
    },
    calibration={name: MotorCalibration(**saved[name]) for name in names},
)

bus.connect()
bus.disable_torque(names)
for name in names:
    bus.write("Operating_Mode", name, OperatingMode.POSITION.value)
    bus.write("Acceleration", name, 10)
    bus.write("Goal_Velocity", name, 80, normalize=False)
current = bus.sync_read("Present_Position", names)
bus.sync_write("Goal_Position", current)
bus.enable_torque(names)
print("Right arm holding current position:")
for name, position in current.items():
    print(f"  {name}: {position:.2f}")
bus.disconnect(disable_torque=False)
