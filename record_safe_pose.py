#!/usr/bin/env python3
from local_config import get_port
import json
import time
from datetime import datetime

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

cal = json.load(open("calibration/xlerobot_040.json"))
safety = json.load(open("calibration/safety_limits.json"))["joints"]
left_names = [n for n in cal if n.startswith("left_arm_") or n.startswith("head_")]
right_names = [n for n in cal if n.startswith("right_arm_")]

def make_motor(name):
    mode = MotorNormMode.RANGE_0_100 if name.endswith("gripper") else MotorNormMode.DEGREES
    return Motor(cal[name]["id"], "sts3215", mode)

left = FeetechMotorsBus(
    port=get_port("XLEROBOT_LEFT_HEAD_PORT"),
    motors={n: make_motor(n) for n in left_names},
    calibration={n: MotorCalibration(**cal[n]) for n in left_names},
)
right = FeetechMotorsBus(
    port=get_port("XLEROBOT_RIGHT_WHEELS_PORT"),
    motors={n: make_motor(n) for n in right_names},
    calibration={n: MotorCalibration(**cal[n]) for n in right_names},
)

left.connect(); right.connect()
try:
    left_torque = left.sync_read("Torque_Enable", left_names, normalize=False)
    right_torque = right.sync_read("Torque_Enable", right_names, normalize=False)
    if any(left_torque.values()) or any(right_torque.values()):
        raise RuntimeError(f"Refusing to record while torque is on: left={left_torque}, right={right_torque}")
    samples = []
    for _ in range(5):
        samples.append({**left.sync_read("Present_Position"), **right.sync_read("Present_Position")})
        time.sleep(0.1)
    positions = {name: sum(s[name] for s in samples) / len(samples) for name in samples[0]}
    spread = {name: max(s[name] for s in samples) - min(s[name] for s in samples) for name in samples[0]}
    unstable = {name: value for name, value in spread.items() if value > 1.0}
    def limits(name):
        return safety[name]["min"], safety[name]["max"]
    outside = {name: value for name, value in positions.items() if not (limits(name)[0] <= value <= limits(name)[1])}
    if unstable:
        raise RuntimeError(f"Pose moved during recording: {unstable}")
    if outside:
        raise RuntimeError(f"Pose is outside software safety limits: {outside}")
    document = {
        "name": "safe_shutdown_pose_v1",
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "units": "degrees; grippers use percent",
        "positions": positions,
        "sample_spread": spread,
    }
    with open("calibration/safe_shutdown_pose.json", "w") as f:
        json.dump(document, f, indent=2)
        f.write("\n")
    print(json.dumps(document, indent=2))
finally:
    left.disconnect(disable_torque=False)
    right.disconnect(disable_torque=False)
