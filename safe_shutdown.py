#!/usr/bin/env python3
from local_config import get_port
import argparse
import json
import math
import statistics
import time
import urllib.request

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

CAL = json.load(open("calibration/xlerobot_040.json"))
SAFETY = json.load(open("calibration/safety_limits.json"))["joints"]
POSE = json.load(open("calibration/safe_shutdown_pose.json"))["positions"]
LEFT = [n for n in POSE if n.startswith("left_arm_") or n.startswith("head_")]
RIGHT = [n for n in POSE if n.startswith("right_arm_")]
WHEELS = ["base_left_wheel", "base_right_wheel"]

def safe_limits(name):
    return SAFETY[name]["min"], SAFETY[name]["max"]

invalid_pose = {n:v for n,v in POSE.items() if not (safe_limits(n)[0] <= v <= safe_limits(n)[1])}
if invalid_pose:
    raise SystemExit(f"DO NOT run automatic return: recorded safe pose exceeds calibrated limits: {invalid_pose}. Re-record the safe pose.")

parser = argparse.ArgumentParser()
parser.add_argument("--validate-only", action="store_true", help="validate files without connecting to the robot")
args = parser.parse_args()
if args.validate_only:
    print("PASS: safety limits and saved shutdown pose are valid; no robot connection was opened.")
    raise SystemExit(0)

def motor(name):
    mode = MotorNormMode.RANGE_0_100 if name.endswith("gripper") else MotorNormMode.DEGREES
    if name in WHEELS: mode = MotorNormMode.RANGE_M100_100
    return Motor(CAL[name]["id"], "sts3215", mode)

print("XLeRobot automatic safe shutdown")
try:
    request = urllib.request.Request("http://127.0.0.1:8765/api/shutdown", method="POST")
    urllib.request.urlopen(request, timeout=3).read()
    print("Web controller stopped safely.")
    time.sleep(2)
except Exception:
    print("Web controller is not running; using direct motor control.")

bus1 = FeetechMotorsBus(
    port=get_port("XLEROBOT_LEFT_HEAD_PORT"),
    motors={n: motor(n) for n in LEFT},
    calibration={n: MotorCalibration(**CAL[n]) for n in LEFT},
)
bus2 = FeetechMotorsBus(
    port=get_port("XLEROBOT_RIGHT_WHEELS_PORT"),
    motors={n: motor(n) for n in RIGHT + WHEELS},
    calibration={n: MotorCalibration(**CAL[n]) for n in RIGHT + WHEELS},
)

bus1.connect(); bus2.connect()
all_torques_off = False
try:
    bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
    current = {**bus1.sync_read("Present_Position", LEFT), **bus2.sync_read("Present_Position", RIGHT)}
    outside_at_start = [n for n, v in current.items() if v < safe_limits(n)[0] or v > safe_limits(n)[1]]
    if outside_at_start:
        raise RuntimeError(f"DO NOT MOVE: current pose is outside safety limits: {outside_at_start}")

    for name in LEFT + RIGHT:
        bus = bus1 if name in LEFT else bus2
        bus.write("Torque_Enable", name, 0, normalize=False)
        bus.write("Operating_Mode", name, OperatingMode.POSITION.value)
        bus.write("Acceleration", name, 5)
        bus.write("Goal_Velocity", name, 80, normalize=False)
        bus.write("Goal_Position", name, current[name])
        bus.write("Torque_Enable", name, 1, normalize=False)
    for name in WHEELS:
        bus2.write("Torque_Enable", name, 0, normalize=False)
        bus2.write("Operating_Mode", name, OperatingMode.VELOCITY.value)
        bus2.write("Goal_Velocity", name, 0, normalize=False)
        bus2.write("Torque_Enable", name, 1, normalize=False)

    max_distance = max(abs(POSE[n] - current[n]) for n in POSE)
    steps = max(1, math.ceil(max_distance / 0.5))
    print(f"Moving to saved safe pose in {steps} slow steps...")
    for index in range(1, steps + 1):
        fraction = index / steps
        goal = {n: current[n] + (POSE[n] - current[n]) * fraction for n in POSE}
        bus1.sync_write("Goal_Position", {n: goal[n] for n in LEFT})
        bus2.sync_write("Goal_Position", {n: goal[n] for n in RIGHT})
        time.sleep(0.12)
        actual = {**bus1.sync_read("Present_Position", LEFT), **bus2.sync_read("Present_Position", RIGHT)}
        outside = [n for n,v in actual.items() if v < safe_limits(n)[0] or v > safe_limits(n)[1]]
        lagging = [n for n in actual if abs(actual[n] - goal[n]) > 15]
        if outside or lagging:
            bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
            bus1.sync_write("Goal_Position", {n: actual[n] for n in LEFT})
            bus2.sync_write("Goal_Position", {n: actual[n] for n in RIGHT})
            raise RuntimeError(f"DO NOT disconnect 12V: automatic return stopped: outside={outside}, lagging={lagging}")

    time.sleep(0.5)
    final = {**bus1.sync_read("Present_Position", LEFT), **bus2.sync_read("Present_Position", RIGHT)}
    errors = {n: round(final[n] - POSE[n], 2) for n in POSE if abs(final[n] - POSE[n]) > 3}
    if errors:
        raise RuntimeError(f"DO NOT disconnect 12V: safe pose verification failed: {errors}")

    bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
    # STS3215 reports isolated +/-50 velocity samples while physically stopped.
    # Verify the commanded register and use a one-second median before removing
    # torque; one noisy sample must not turn a successful shutdown into a false
    # failure after every actuator is already released.
    wheel_goal = bus2.sync_read("Goal_Velocity", WHEELS, normalize=False)
    velocity_samples = []
    for _ in range(11):
        velocity_samples.append(bus2.sync_read("Present_Velocity", WHEELS, normalize=False))
        time.sleep(0.1)
    wheel_velocity = {
        name: statistics.median(sample[name] for sample in velocity_samples)
        for name in WHEELS
    }
    bad_wheel_goals = {name:value for name,value in wheel_goal.items() if value != 0}
    moving_wheels = {name:value for name,value in wheel_velocity.items() if abs(value) > 5}
    if bad_wheel_goals or moving_wheels:
        raise RuntimeError(
            f"DO NOT disconnect 12V: wheel stop verification failed: "
            f"goal={bad_wheel_goals}, median_velocity={moving_wheels}, samples={velocity_samples}"
        )

    bus1.disable_torque(); bus2.disable_torque()
    time.sleep(0.5)
    torque1 = bus1.sync_read("Torque_Enable", LEFT, normalize=False)
    torque2 = bus2.sync_read("Torque_Enable", RIGHT + WHEELS, normalize=False)
    if any(torque1.values()) or any(torque2.values()):
        raise RuntimeError("DO NOT disconnect 12V: torque-off verification failed")
    all_torques_off = True
    print("Safe pose reached and verified.")
    print(f"Wheel stop verified: goal={wheel_goal}, median velocity={wheel_velocity}")
    print("All 16 motor torques are off and verified.")
    print("12V POWER-OFF CHECK: PASS")
    print("Verification complete: it is now safe to disconnect the 12 V supply. Disconnecting 12 V is recommended.")
except Exception:
    try:
        if not all_torques_off:
            bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
            actual = {**bus1.sync_read("Present_Position", LEFT), **bus2.sync_read("Present_Position", RIGHT)}
            bus1.sync_write("Goal_Position", {n: actual[n] for n in LEFT})
            bus2.sync_write("Goal_Position", {n: actual[n] for n in RIGHT})
            print("FAIL-SAFE: wheels stopped; arms are holding their current positions. Keep 12V on.")
        else:
            print("FAIL-SAFE: all motor torques were already verified off.")
    except Exception as recovery_error:
        print(f"FAIL-SAFE recovery also failed: {recovery_error}. Use the physical 12V switch if motion is unsafe.")
    raise
finally:
    bus1.disconnect(disable_torque=False)
    bus2.disconnect(disable_torque=False)
