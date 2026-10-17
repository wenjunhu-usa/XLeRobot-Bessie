"""Validate bounded arm-only gamepad steps without touching hardware."""
import math

ARM_JOINTS = {
    f"{side}_arm_{joint}"
    for side in ("left", "right")
    for joint in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
}


def plan_steps(steps, targets, limits, mode="arms"):
    if not isinstance(steps, dict) or len(steps) > 4:
        raise ValueError("Expected up to four arm joint steps")
    allowed = ARM_JOINTS if mode == "arms" else {"head_motor_1", "head_motor_2"} if mode == "head" else set()
    result = {}
    for name, amount in steps.items():
        if name not in allowed or isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError("Invalid arm joint or step")
        maximum = 2.0
        if not math.isfinite(amount) or abs(amount) > maximum:
            raise ValueError(f"Step must be finite and at most {maximum:g}")
        lo, hi = limits[name]
        result[name] = max(lo, min(hi, targets[name] + amount))
    return result


def wheel_speeds(forward, turn, raised):
    if raised is not True:
        raise ValueError("Confirm wheels are raised first")
    for value in (forward, turn):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1:
            raise ValueError("Invalid wheel input")
    # Same motor signs and speed ceiling as the existing web wheel buttons.
    return (round(max(-100, min(100, -100 * forward + 100 * turn))),
            round(max(-100, min(100, 100 * forward + 100 * turn))))
