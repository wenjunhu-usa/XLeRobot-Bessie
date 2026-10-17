# XLeRobot-Bessie

This repository contains the control software and robot-specific parameters developed for Bessie: browser control for both arms, the head, and wheels; gamepad and keyboard input; software safety limits; safe shutdown; Cartesian arm control; and training-data collection.

## Relationship to XLeRobot

This project builds on [XLeRobot](https://github.com/Vector-Wangel/XLeRobot) and [LeRobot](https://github.com/huggingface/lerobot). The original XLeRobot source, mechanical designs, hardware models, simulations, and general documentation are not copied into this repository. Get them directly from the upstream projects. This repository contains only Bessie's additions and measured robot parameters.

Before using this project, assemble the robot and install a compatible LeRobot environment by following the upstream XLeRobot documentation. This code is released under Apache-2.0; the upstream projects remain the property of their respective authors.

## Contents

- `xlerobot_web.py`: Bessie's browser control service and runtime safety monitor.
- `arm_gamepad.*` and `gamepad_mapping.js`: gamepad control for the arms, head, and wheels.
- `cartesian_control.*` and `so101_kinematics.py`: planar Cartesian increments for both arms.
- `data_collection/`: camera, action, and state recording with LeRobot v2 export.
- `calibration/`: Bessie's motor calibration, safety limits, and safe shutdown pose.
- `calibrate_*.py`, `record_*.py`, and `finalize_safety_limits.py`: Bessie calibration and limit tools.
- `safe_shutdown.py`: speed-limited safe shutdown sequence.
- `tests/`: control planning, browser input, and recording tests.

## Installation

Python 3.12 is recommended. First install the XLeRobot-compatible LeRobot environment described by the upstream project, then install Bessie's additional dependencies:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

The head recalibration script also requires XLeRobot's `xlerobot_mount` module. That module belongs to upstream XLeRobot and is not copied here.

## Local device configuration

```bash
cp robot_ports.env.example robot_ports.env
ls -l /dev/serial/by-id/
v4l2-ctl --list-devices
```

Replace the serial and camera paths in `robot_ports.env` with paths detected on the current machine. Git ignores this file so hardware serial numbers are not published.

The tracked calibration and safety parameters apply to Bessie only. Recalibrate every motor and remeasure all software limits before using the code with another robot.

## Starting the controller

Connect both controller buses and cameras, and clear the area around both arms. Support the robot with its wheels off the ground during initial wheel testing:

```bash
./start_web_controller.sh
```

Open `http://127.0.0.1:8765/`. The controller reads the physical joint positions at startup and does not automatically return to zero. Begin operating only after the page displays `Safety monitor active — motion permitted`.

Runtime protections include:

- Every position command is checked against Bessie's measured software limits.
- If an actual or requested position exceeds its limit, the wheels stop, the arms and head hold position, and the emergency stop latches.
- Wheel commands expire after a short timeout, so the robot stops after a page or gamepad disconnect.
- Cartesian control limits translation, joint jumps, and target-following error.
- `/tmp/xlerobot-controller.lock` prevents two controllers from opening the serial buses simultaneously.

Software protection cannot replace the physical power switch. Keep the 12 V disconnect within immediate reach while testing.

## Tests

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Browser input tests are stored in `tests/*.html` and require a browser environment with Gamepad API support.
