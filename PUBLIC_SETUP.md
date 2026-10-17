# Public checkout setup

This repository contains Bessie-specific additions only. Install the base
[XLeRobot](https://github.com/Vector-Wangel/XLeRobot) software and its compatible
LeRobot environment separately; their source is not vendored here.

## Environment

Use Python 3.12 and the LeRobot version required by XLeRobot, then install the
small set of extra dependencies:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Private device configuration

```bash
cp robot_ports.env.example robot_ports.env
ls -l /dev/serial/by-id/
v4l2-ctl --list-devices
```

Replace the example values with paths from your machine. `robot_ports.env` is
ignored by Git so controller serial numbers and camera paths remain private.

## Bessie calibration

The tracked files in `calibration/` are Bessie's measured motor calibration,
software limits, and safe shutdown pose. They are useful for Bessie and unsafe
to reuse on another physical robot. Recalibrate and remeasure every limit after
changing motors, horns, linkages, or controller assignments.

## Pre-upload check

```bash
git status --short
git diff --cached
git grep -n -E 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|gh[pousr]_|github_pat_|hf_|sk-'
```
