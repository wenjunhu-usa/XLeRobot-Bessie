"""Bounded SO-101 end-effector planning for the XLeRobot web controller.

The bundled SO101 model is planar: it maps reach/height to shoulder_lift and
elbow_flex. Shoulder pan, wrist pitch/roll, and the gripper are controlled as
small coordinated increments around that planar solution.
"""

import math

from so101_kinematics import SO101Kinematics


SIDES = ("left", "right")
DELTA_LIMITS = {
    "reach": 0.003,   # metres per request
    "height": 0.003,  # metres per request
    "pitch": 1.0,     # degrees per request
    "pan": 1.0,
    "roll": 1.0,
    "gripper": 2.0,   # percent per request
}
MAX_JOINT_STEP_DEG = 3.0
# URDF: Wrist_Roll origin is 60.1 mm from wrist pitch and Fixed_Jaw_tip is
# another 97 mm along the tool. The old two-link controller stopped at the
# wrist joint and therefore did not control the physical gripper tip.
TOOL_LENGTH = 0.0601 + 0.097


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def arm_pose(side, targets, kinematics=None):
    """Return the planar tool pose implied by a joint target dictionary."""
    if side not in SIDES:
        raise ValueError("arm must be left or right")
    kinematics = kinematics or SO101Kinematics()
    prefix = f"{side}_arm_"
    shoulder = targets[prefix + "shoulder_lift"]
    elbow = targets[prefix + "elbow_flex"]
    wrist_reach, wrist_height = kinematics.forward_kinematics(shoulder, elbow)
    pitch = targets[prefix + "wrist_flex"] + shoulder + elbow
    pitch_rad = math.radians(pitch)
    return {
        "reach": wrist_reach + TOOL_LENGTH * math.cos(pitch_rad),
        "height": wrist_height + TOOL_LENGTH * math.sin(pitch_rad),
        "wrist_reach": wrist_reach,
        "wrist_height": wrist_height,
        "pitch": pitch,
        "pan": targets[prefix + "shoulder_pan"],
        "roll": targets[prefix + "wrist_roll"],
        "gripper": targets[prefix + "gripper"],
    }


def _inverse_candidates(reach, height, kinematics):
    """Return both analytic branches that invert SO101Kinematics.forward_kinematics."""
    l1, l2 = kinematics.l1, kinematics.l2
    cosine = (reach * reach + height * height - l1 * l1 - l2 * l2) / (2 * l1 * l2)
    cosine = max(-1.0, min(1.0, cosine))
    offset1 = math.atan2(0.028, 0.11257)
    offset2 = math.atan2(0.0052, 0.1349) + offset1
    solutions = []
    for relative_elbow in (math.acos(cosine), -math.acos(cosine)):
        shoulder_axis = math.atan2(height, reach) - math.atan2(
            l2 * math.sin(relative_elbow), l1 + l2 * math.cos(relative_elbow)
        )
        model_elbow = relative_elbow + math.pi
        shoulder = 90 - math.degrees(shoulder_axis + offset1)
        elbow = math.degrees(model_elbow + offset2) - 90
        solutions.append((shoulder, elbow))
    return solutions


def plan_cartesian(commands, targets, limits, kinematics=None):
    """Plan one bounded Cartesian increment for one or both arms.

    ``commands`` maps ``left`` and/or ``right`` to delta fields from
    ``DELTA_LIMITS``. All resulting joints must remain inside the measured
    software limits; otherwise no plan is returned.
    """
    if not isinstance(commands, dict) or not commands or len(commands) > 2:
        raise ValueError("Expected Cartesian commands for one or two arms")
    kinematics = kinematics or SO101Kinematics()
    planned = {}
    for side, command in commands.items():
        if side not in SIDES or not isinstance(command, dict):
            raise ValueError("Invalid arm command")
        unknown = set(command) - set(DELTA_LIMITS)
        if unknown:
            raise ValueError(f"Unknown Cartesian fields: {', '.join(sorted(unknown))}")
        delta = {name: _number(command.get(name, 0), name) for name in DELTA_LIMITS}
        for name, value in delta.items():
            if abs(value) > DELTA_LIMITS[name]:
                raise ValueError(f"{name} increment exceeds {DELTA_LIMITS[name]}")

        pose = arm_pose(side, targets, kinematics)
        prefix = f"{side}_arm_"
        rejected = []
        candidates = []
        # A 3 mm Cartesian step can require fractionally more than the 3° hard
        # joint-step ceiling at some poses. Back off translation only while
        # retaining the requested tool pitch/pan/roll/gripper increment.
        for translation_scale in (1.0, 0.75, 0.5, 0.25):
            tip_reach = pose["reach"] + delta["reach"] * translation_scale
            tip_height = pose["height"] + delta["height"] * translation_scale
            pitch = pose["pitch"] + delta["pitch"]
            pitch_rad = math.radians(pitch)
            reach = tip_reach - TOOL_LENGTH * math.cos(pitch_rad)
            height = tip_height - TOOL_LENGTH * math.sin(pitch_rad)
            radius = math.hypot(reach, height)
            minimum = abs(kinematics.l1 - kinematics.l2) + 0.005
            maximum = kinematics.l1 + kinematics.l2 - 0.005
            if not minimum <= radius <= maximum:
                rejected.append(f"workspace {minimum:.3f}…{maximum:.3f} m")
                continue
            for shoulder, elbow in _inverse_candidates(reach, height, kinematics):
                candidate = {
                    prefix + "shoulder_pan": pose["pan"] + delta["pan"],
                    prefix + "shoulder_lift": shoulder,
                    prefix + "elbow_flex": elbow,
                    prefix + "wrist_flex": pitch - shoulder - elbow,
                    prefix + "wrist_roll": pose["roll"] + delta["roll"],
                    prefix + "gripper": pose["gripper"] + delta["gripper"],
                }
                outside = [name for name, value in candidate.items() if value < limits[name][0] or value > limits[name][1]]
                if outside:
                    rejected.extend(outside)
                    continue
                jumped = [
                    name for name, value in candidate.items()
                    if not name.endswith("gripper") and abs(value - targets[name]) > MAX_JOINT_STEP_DEG
                ]
                if jumped:
                    rejected.extend(f"{name} jump>{MAX_JOINT_STEP_DEG:g}°" for name in jumped)
                    continue
                distance = (shoulder - targets[prefix + "shoulder_lift"]) ** 2 + (elbow - targets[prefix + "elbow_flex"]) ** 2
                candidates.append((distance, candidate))
            if candidates:
                break
        if not candidates:
            names = ", ".join(sorted(set(rejected))) or "no continuous IK solution"
            raise ValueError("Cartesian target exceeds safe joint range: " + names)
        planned.update(min(candidates, key=lambda item: item[0])[1])
    return planned
