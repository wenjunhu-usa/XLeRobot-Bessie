#!/usr/bin/env python3
from local_config import get_port
import select
import sys
import time

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus


PORT = get_port("XLEROBOT_RIGHT_WHEELS_PORT")
bus = FeetechMotorsBus(
    port=PORT,
    motors={"right_elbow": Motor(3, "sts3215", MotorNormMode.DEGREES)},
)

bus.connect(handshake=False)
minimum = 4096
maximum = -1
last_print = 0.0
print("Recording right elbow ID 3. Press ENTER to stop.", flush=True)
try:
    while True:
        position = bus.read("Present_Position", "right_elbow", normalize=False)
        minimum = min(minimum, position)
        maximum = max(maximum, position)
        now = time.monotonic()
        if now - last_print >= 0.5:
            print(f"min={minimum:4d} current={position:4d} max={maximum:4d}", flush=True)
            last_print = now
        if select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
            break
        time.sleep(0.02)
finally:
    print(f"FINAL min={minimum} max={maximum} span={maximum - minimum}", flush=True)
    bus.disconnect(disable_torque=False)
