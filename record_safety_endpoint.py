#!/usr/bin/env python3
from local_config import get_port
import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

CAL_PATH = Path("calibration/xlerobot_040.json")
OUT_PATH = Path("calibration/safety_limits_draft.json")
LEFT_PORT = get_port("XLEROBOT_LEFT_HEAD_PORT")
RIGHT_PORT = get_port("XLEROBOT_RIGHT_WHEELS_PORT")
CAL = json.loads(CAL_PATH.read_text())

parser = argparse.ArgumentParser()
parser.add_argument("joint")
parser.add_argument("endpoint")
args = parser.parse_args()
name = args.joint
if name not in CAL or name.startswith("base_"):
    raise SystemExit(f"Unknown position joint: {name}")
if args.endpoint not in {"endpoint_a", "endpoint_b"}:
    raise SystemExit("endpoint must be endpoint_a or endpoint_b")

mode = MotorNormMode.RANGE_0_100 if name.endswith("gripper") else MotorNormMode.DEGREES
motor = Motor(CAL[name]["id"], "sts3215", mode)
port = LEFT_PORT if name.startswith("left_arm_") or name.startswith("head_") else RIGHT_PORT
bus = FeetechMotorsBus(
    port=port,
    motors={name: motor},
    calibration={name: MotorCalibration(**CAL[name])},
)
bus.connect()
try:
    torque = bus.read("Torque_Enable", name, normalize=False)
    if torque != 0:
        raise RuntimeError(f"Refusing to record while {name} torque is ON")
    raw_samples = []
    value_samples = []
    for _ in range(7):
        raw_samples.append(bus.read("Present_Position", name, normalize=False))
        value_samples.append(bus.read("Present_Position", name))
        time.sleep(0.08)
finally:
    bus.disconnect(disable_torque=False)

if max(raw_samples) - min(raw_samples) > 8:
    raise RuntimeError(f"Joint moved during sampling: raw={raw_samples}")

entry = {
    "raw": int(round(statistics.median(raw_samples))),
    "value": round(float(statistics.median(value_samples)), 4),
    "unit": "%" if name.endswith("gripper") else "deg",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
}
doc = json.loads(OUT_PATH.read_text()) if OUT_PATH.exists() else {
    "format": "xlerobot_user_safety_limits_v1",
    "status": "draft",
    "joints": {},
}
doc["joints"].setdefault(name, {})[args.endpoint] = entry
tmp = OUT_PATH.with_suffix(".tmp")
tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
os.replace(tmp, OUT_PATH)
print(json.dumps({"joint": name, "endpoint": args.endpoint, **entry}, ensure_ascii=False))
