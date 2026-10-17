#!/usr/bin/env python3
from local_config import get_port
import fcntl
import json
import time
import urllib.request

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

CAL = json.load(open("calibration/xlerobot_040.json"))
RIGHT = [
    "right_arm_shoulder_pan",
    "right_arm_shoulder_lift",
    "right_arm_elbow_flex",
    "right_arm_wrist_flex",
    "right_arm_wrist_roll",
    "right_arm_gripper",
]
WHEELS = ["base_left_wheel", "base_right_wheel"]
PORT = get_port("XLEROBOT_RIGHT_WHEELS_PORT")


def motor(name):
    mode = MotorNormMode.RANGE_0_100 if name.endswith("gripper") else MotorNormMode.DEGREES
    if name in WHEELS:
        mode = MotorNormMode.RANGE_M100_100
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
    motors={n: motor(n) for n in RIGHT + WHEELS},
    calibration={n: MotorCalibration(**CAL[n]) for n in RIGHT + WHEELS},
)
bus.connect()
try:
    bus.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
    time.sleep(1)
    wheel_velocity = bus.sync_read("Present_Velocity", WHEELS, normalize=False)
    positions = bus.sync_read("Present_Position", RIGHT)
    bus.sync_write("Torque_Enable", dict.fromkeys(RIGHT, 0), normalize=False)
    torque = bus.sync_read("Torque_Enable", RIGHT, normalize=False)
    if any(torque.values()):
        raise RuntimeError(f"Right-arm torque-off verification failed: {torque}")
    print("Wheel stop command sent; velocities:", wheel_velocity)
    print("Right-arm positions before release:", positions)
    print("Right-arm torque verified OFF:", torque)
    print("You may now support and manually position the right arm.")
finally:
    bus.disconnect(disable_torque=False)
