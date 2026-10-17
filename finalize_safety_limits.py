#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path

CAL = json.loads(Path("calibration/xlerobot_040.json").read_text())
DRAFT = json.loads(Path("calibration/safety_limits_draft.json").read_text())
OUT = Path("calibration/safety_limits.json")
JOINTS = [
    "left_arm_shoulder_pan", "left_arm_shoulder_lift", "left_arm_elbow_flex",
    "left_arm_wrist_flex", "left_arm_wrist_roll", "left_arm_gripper",
    "head_motor_1", "head_motor_2",
    "right_arm_shoulder_pan", "right_arm_shoulder_lift", "right_arm_elbow_flex",
    "right_arm_wrist_flex", "right_arm_wrist_roll", "right_arm_gripper",
]

missing = [name for name in JOINTS if name not in DRAFT["joints"]]
if missing:
    raise SystemExit(f"Missing recorded joints: {missing}")

result = {
    "format": "xlerobot_safety_limits_v1",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "method": "user-selected endpoints intersected with calibrated motor range, then inset",
    "joints": {},
}
for name in JOINTS:
    recorded = DRAFT["joints"][name]
    values = sorted([float(recorded["endpoint_a"]["value"]), float(recorded["endpoint_b"]["value"])])
    if name.endswith("gripper"):
        hard_min, hard_max, margin, unit = 0.0, 100.0, 0.5, "%"
    else:
        half_span = (CAL[name]["range_max"] - CAL[name]["range_min"]) * 180.0 / 4095.0
        hard_min, hard_max, margin, unit = -half_span, half_span, 0.5, "deg"
    intersect_min = max(values[0], hard_min)
    intersect_max = min(values[1], hard_max)
    safe_min = intersect_min + margin
    safe_max = intersect_max - margin
    if safe_min >= safe_max:
        raise RuntimeError(f"No usable range for {name}: recorded={values}, hardware={[hard_min, hard_max]}")
    result["joints"][name] = {
        "min": round(safe_min, 4), "max": round(safe_max, 4), "unit": unit,
        "recorded_min": round(values[0], 4), "recorded_max": round(values[1], 4),
        "hardware_min": round(hard_min, 4), "hardware_max": round(hard_max, 4),
        "inset": margin,
    }

tmp = OUT.with_suffix(".tmp")
tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
os.replace(tmp, OUT)
for name, limits in result["joints"].items():
    print(f"{name}: {limits['min']:.2f} .. {limits['max']:.2f} {limits['unit']}")
