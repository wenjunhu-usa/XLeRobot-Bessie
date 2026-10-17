#!/usr/bin/env python3
from local_config import get_port
import fcntl
import json
import time
import urllib.request

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

CAL = json.load(open("calibration/xlerobot_040.json"))
LEFT = [
    "left_arm_shoulder_pan", "left_arm_shoulder_lift", "left_arm_elbow_flex",
    "left_arm_wrist_flex", "left_arm_wrist_roll", "left_arm_gripper",
    "head_motor_1", "head_motor_2",
]
RIGHT = [
    "right_arm_shoulder_pan", "right_arm_shoulder_lift", "right_arm_elbow_flex",
    "right_arm_wrist_flex", "right_arm_wrist_roll", "right_arm_gripper",
]
WHEELS = ["base_left_wheel", "base_right_wheel"]
LEFT_PORT = get_port("XLEROBOT_LEFT_HEAD_PORT")
RIGHT_PORT = get_port("XLEROBOT_RIGHT_WHEELS_PORT")


def motor(name):
    if name.endswith("gripper"):
        mode = MotorNormMode.RANGE_0_100
    elif name in WHEELS:
        mode = MotorNormMode.RANGE_M100_100
    else:
        mode = MotorNormMode.DEGREES
    return Motor(CAL[name]["id"], "sts3215", mode)


try:
    req = urllib.request.Request("http://127.0.0.1:8765/api/shutdown", method="POST")
    urllib.request.urlopen(req, timeout=3).read()
    time.sleep(2)
except Exception:
    pass

lock_file = open("/tmp/xlerobot-controller.lock", "w")
fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
bus1 = FeetechMotorsBus(
    port=LEFT_PORT,
    motors={n: motor(n) for n in LEFT},
    calibration={n: MotorCalibration(**CAL[n]) for n in LEFT},
)
bus2 = FeetechMotorsBus(
    port=RIGHT_PORT,
    motors={n: motor(n) for n in RIGHT + WHEELS},
    calibration={n: MotorCalibration(**CAL[n]) for n in RIGHT + WHEELS},
)
bus1.connect(); bus2.connect()
try:
    bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
    bus1.disable_torque()
    bus2.disable_torque()
    time.sleep(2)
    wheel_velocity = bus2.sync_read("Present_Velocity", WHEELS, normalize=False)
    torque1 = bus1.sync_read("Torque_Enable", LEFT, normalize=False)
    torque2 = bus2.sync_read("Torque_Enable", RIGHT + WHEELS, normalize=False)
    if any(torque1.values()) or any(torque2.values()):
        raise RuntimeError(f"Torque-off verification failed: left={torque1}, right={torque2}")
    if any(abs(v) > 5 for v in wheel_velocity.values()):
        raise RuntimeError(f"Wheel stop verification failed: {wheel_velocity}")
    print("Wheels stopped:", wheel_velocity)
    print("All 16 motor torques verified OFF.")
    print("Manual calibration mode is ready.")
finally:
    bus1.disconnect(disable_torque=False)
    bus2.disconnect(disable_torque=False)
