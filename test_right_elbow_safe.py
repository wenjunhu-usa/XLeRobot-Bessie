#!/usr/bin/env python3
from local_config import get_port
import json
import time

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode


port = get_port("XLEROBOT_RIGHT_WHEELS_PORT")
saved = json.load(open("calibration/xlerobot_right_arm.json"))["elbow_flex"]
bus = FeetechMotorsBus(
    port=port,
    motors={"elbow_flex": Motor(3, "sts3215", MotorNormMode.DEGREES)},
    calibration={"elbow_flex": MotorCalibration(**saved)},
)

bus.connect()
try:
    bus.disable_torque("elbow_flex")
    bus.write("Operating_Mode", "elbow_flex", OperatingMode.POSITION.value)
    bus.write("Acceleration", "elbow_flex", 10)
    bus.write("Goal_Velocity", "elbow_flex", 80, normalize=False)
    start = bus.read("Present_Position", "elbow_flex")
    bus.write("Goal_Position", "elbow_flex", start)
    bus.enable_torque("elbow_flex")
    time.sleep(0.5)

    target = start + 3.0
    print(f"start={start:.2f} deg, target={target:.2f} deg", flush=True)
    bus.write("Goal_Position", "elbow_flex", target)
    time.sleep(1.0)
    outward = bus.read("Present_Position", "elbow_flex")
    print(f"outward={outward:.2f} deg", flush=True)

    bus.write("Goal_Position", "elbow_flex", start)
    time.sleep(1.0)
    returned = bus.read("Present_Position", "elbow_flex")
    print(f"returned={returned:.2f} deg", flush=True)
finally:
    bus.disable_torque("elbow_flex")
    bus.disconnect(disable_torque=False)
