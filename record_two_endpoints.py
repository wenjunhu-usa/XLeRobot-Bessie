#!/usr/bin/env python3
from local_config import get_port
import argparse
import fcntl
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

CAL = json.loads(Path("calibration/xlerobot_040.json").read_text())
OUT = Path("calibration/safety_limits_draft.json")
LEFT_PORT = get_port("XLEROBOT_LEFT_HEAD_PORT")
RIGHT_PORT = get_port("XLEROBOT_RIGHT_WHEELS_PORT")

parser = argparse.ArgumentParser()
parser.add_argument("joint")
parser.add_argument("--timeout", type=float, default=180.0)
args = parser.parse_args()
name = args.joint
if name not in CAL or name.startswith("base_"):
    raise SystemExit(f"Unknown position joint: {name}")

lock_file = open("/tmp/xlerobot-controller.lock", "w")
fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
mode = MotorNormMode.RANGE_0_100 if name.endswith("gripper") else MotorNormMode.DEGREES
bus = FeetechMotorsBus(
    port=LEFT_PORT if name.startswith("left_arm_") or name.startswith("head_") else RIGHT_PORT,
    motors={name: Motor(CAL[name]["id"], "sts3215", mode)},
    calibration={name: MotorCalibration(**CAL[name])},
)


def save(points):
    unit = "%" if name.endswith("gripper") else "deg"
    ordered = sorted(points, key=lambda p: p["value"])
    doc = json.loads(OUT.read_text()) if OUT.exists() else {
        "format": "xlerobot_user_safety_limits_v1", "status": "draft", "joints": {}
    }
    doc["joints"][name] = {
        "endpoint_a": {**ordered[0], "unit": unit},
        "endpoint_b": {**ordered[1], "unit": unit},
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)


bus.connect()
try:
    if bus.read("Torque_Enable", name, normalize=False) != 0:
        raise RuntimeError(f"Refusing to record while {name} torque is ON")
    initial = bus.read("Present_Position", name, normalize=False)
    print(f"RECORDING {name}; initial raw={initial}. Move to endpoint 1 and hold 2 seconds.", flush=True)
    points = []
    anchor = initial
    moved = False
    window = []
    deadline = time.monotonic() + args.timeout
    while len(points) < 2:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Timed out after recording {len(points)} endpoint(s)")
        raw = bus.read("Present_Position", name, normalize=False)
        value = float(bus.read("Present_Position", name))
        now = time.monotonic()
        if abs(raw - anchor) >= 12:
            moved = True
        window.append((now, raw, value))
        window = [x for x in window if now - x[0] <= 1.6]
        if moved and len(window) >= 10 and now - window[0][0] >= 1.4:
            raws = [x[1] for x in window]
            if max(raws) - min(raws) <= 5:
                point = {
                    "raw": int(round(statistics.median(raws))),
                    "value": round(statistics.median(x[2] for x in window), 4),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
                points.append(point)
                print(f"ENDPOINT {len(points)} RECORDED: {point}", flush=True)
                if len(points) == 1:
                    print("Move to endpoint 2 and hold 2 seconds.", flush=True)
                    anchor = point["raw"]
                    moved = False
                    window = []
                    time.sleep(0.5)
        time.sleep(0.1)
    save(points)
    print("COMPLETE", json.dumps({"joint": name, "endpoints": points}, ensure_ascii=False), flush=True)
finally:
    bus.disconnect(disable_torque=False)
