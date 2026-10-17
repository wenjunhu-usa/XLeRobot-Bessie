#!/usr/bin/env python3
from local_config import get_port
import json

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode


saved = json.load(open("calibration/xlerobot_right_arm.json"))["gripper"]
bus = FeetechMotorsBus(
    port=get_port("XLEROBOT_RIGHT_WHEELS_PORT"),
    motors={"gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100)},
    calibration={"gripper": MotorCalibration(**saved)},
)

bus.connect()
try:
    bus.disable_torque("gripper")
    bus.write("Operating_Mode", "gripper", OperatingMode.POSITION.value)
    bus.write("Acceleration", "gripper", 5)
    bus.write("Goal_Velocity", "gripper", 50, normalize=False)
    target = bus.read("Present_Position", "gripper")
    bus.write("Goal_Position", "gripper", target)
    bus.enable_torque("gripper")
    print(f"Right gripper holding at {target:.2f}%")
    print("Enter '+' or '-' then ENTER for a 1% step; 'q' then ENTER to quit and keep holding.")
    while True:
        command = input("gripper> ").strip()
        if command.lower() == "q":
            break
        if command not in {"+", "-"}:
            print("Use only +, -, or q.")
            continue
        target += 1.0 if command == "+" else -1.0
        target = max(0.0, min(100.0, target))
        bus.write("Goal_Position", "gripper", target)
        print(f"Target: {target:.2f}%")
finally:
    bus.disconnect(disable_torque=False)
