#!/usr/bin/env python3
from local_config import get_port
import json
import tkinter as tk
from tkinter import messagebox

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode


class GripperWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("XLeRobot Right Gripper — ID 6")
        self.root.geometry("440x220")
        self.root.resizable(False, False)

        saved = json.load(open("calibration/xlerobot_right_arm.json"))["gripper"]
        self.bus = FeetechMotorsBus(
            port=get_port("XLEROBOT_RIGHT_WHEELS_PORT"),
            motors={"gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100)},
            calibration={"gripper": MotorCalibration(**saved)},
        )
        self.bus.connect()
        self.bus.disable_torque("gripper")
        self.bus.write("Operating_Mode", "gripper", OperatingMode.POSITION.value)
        self.bus.write("Acceleration", "gripper", 5)
        self.bus.write("Goal_Velocity", "gripper", 50, normalize=False)
        self.target = self.bus.read("Present_Position", "gripper")
        self.bus.write("Goal_Position", "gripper", self.target)
        self.bus.enable_torque("gripper")

        tk.Label(root, text="Right gripper ID 6", font=("Sans", 18, "bold")).pack(pady=(18, 6))
        self.status = tk.StringVar()
        tk.Label(root, textvariable=self.status, font=("Sans", 14)).pack(pady=5)
        controls = tk.Frame(root)
        controls.pack(pady=16)
        tk.Button(controls, text="− 1%", width=12, height=2, command=lambda: self.step(-1)).pack(side="left", padx=10)
        tk.Button(controls, text="+ 1%", width=12, height=2, command=lambda: self.step(1)).pack(side="left", padx=10)
        tk.Label(root, text="Keep fingers and objects out of the gripper during the first test.").pack()
        self.update_status()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def update_status(self) -> None:
        actual = self.bus.read("Present_Position", "gripper")
        self.status.set(f"Target {self.target:.1f}%   |   Actual {actual:.1f}%")

    def step(self, amount: float) -> None:
        try:
            self.target = max(0.0, min(100.0, self.target + amount))
            self.bus.write("Goal_Position", "gripper", self.target)
            self.root.after(250, self.update_status)
        except Exception as exc:
            messagebox.showerror("Gripper error", str(exc))

    def close(self) -> None:
        self.bus.disconnect(disable_torque=False)
        self.root.destroy()


root = tk.Tk()
try:
    GripperWindow(root)
    root.mainloop()
except Exception as exc:
    messagebox.showerror("XLeRobot gripper", str(exc))
    root.destroy()
