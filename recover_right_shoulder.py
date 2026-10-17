#!/usr/bin/env python3
from local_config import get_port
import fcntl
import json
import time
import urllib.request

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

NAME = "right_arm_shoulder_lift"
WHEELS = ["base_left_wheel", "base_right_wheel"]
PORT = get_port("XLEROBOT_RIGHT_WHEELS_PORT")
CAL = json.load(open("calibration/xlerobot_040.json"))


def motor(name):
    mode = MotorNormMode.RANGE_M100_100 if name in WHEELS else MotorNormMode.DEGREES
    return Motor(CAL[name]["id"], "sts3215", mode)


try:
    req = urllib.request.Request("http://127.0.0.1:8765/api/shutdown", method="POST")
    urllib.request.urlopen(req, timeout=3).read()
    time.sleep(2)
except Exception:
    pass

controller_lock = open("/tmp/xlerobot-controller.lock", "w")
fcntl.flock(controller_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
bus = FeetechMotorsBus(
    port=PORT,
    motors={n: motor(n) for n in [NAME] + WHEELS},
    calibration={n: MotorCalibration(**CAL[n]) for n in [NAME] + WHEELS},
)
bus.connect()
try:
    bus.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
    bus.write("Torque_Enable", NAME, 0, normalize=False)
    bus.write("Operating_Mode", NAME, OperatingMode.POSITION.value)
    bus.write("Acceleration", NAME, 3, normalize=False)
    bus.write("Goal_Velocity", NAME, 30, normalize=False)
    start = bus.read("Present_Position", NAME)
    target = start + 5.0
    bus.write("Goal_Position", NAME, target)
    bus.write("Torque_Enable", NAME, 1, normalize=False)
    time.sleep(2)
    actual = bus.read("Present_Position", NAME)
    print(f"{NAME}: start={start:.2f}, target={target:.2f}, actual={actual:.2f}")
finally:
    bus.disconnect(disable_torque=False)
