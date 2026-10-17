import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cartesian_control import DELTA_LIMITS, MAX_JOINT_STEP_DEG, TOOL_LENGTH, arm_pose, plan_cartesian


class CartesianControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = json.loads((ROOT / "calibration/safe_shutdown_pose.json").read_text())["positions"]
        raw = json.loads((ROOT / "calibration/safety_limits.json").read_text())["joints"]
        cls.limits = {name: (value["min"], value["max"]) for name, value in raw.items()}

    def test_zero_plan_preserves_current_ik_branch(self):
        for side in ("left", "right"):
            planned = plan_cartesian({side: {"gripper": 1}}, self.targets, self.limits)
            for joint in ("shoulder_lift", "elbow_flex"):
                name = f"{side}_arm_{joint}"
                self.assertAlmostEqual(planned[name], self.targets[name], places=9)

    def test_small_motion_reaches_requested_gripper_tip_pose(self):
        for side in ("left", "right"):
            before = arm_pose(side, self.targets)
            planned = plan_cartesian({side: {"reach": .001, "height": -.001, "pitch": .5}}, self.targets, self.limits)
            merged = {**self.targets, **planned}
            after = arm_pose(side, merged)
            self.assertGreater(after["reach"], before["reach"])
            self.assertLess(after["height"], before["height"])
            self.assertLessEqual(after["reach"]-before["reach"], .001000001)
            self.assertLessEqual(before["height"]-after["height"], .001000001)
            self.assertAlmostEqual(after["pitch"], before["pitch"] + .5, places=6)

    def test_pose_includes_the_urdf_wrist_to_gripper_length(self):
        for side in ("left", "right"):
            pose = arm_pose(side, self.targets)
            distance = math.hypot(pose["reach"]-pose["wrist_reach"],
                                  pose["height"]-pose["wrist_height"])
            self.assertAlmostEqual(distance, TOOL_LENGTH, places=9)


    def test_dual_arm_and_input_guards(self):
        planned = plan_cartesian({"left": {"pan": .5}, "right": {"roll": -.5}}, self.targets, self.limits)
        self.assertIn("left_arm_shoulder_pan", planned)
        self.assertIn("right_arm_wrist_roll", planned)
        invalid = [
            {"left": {"reach": DELTA_LIMITS["reach"] + .001}},
            {"left": {"height": math.nan}},
            {"left": {"unknown": 1}},
            {"middle": {"reach": 0}},
            {},
        ]
        for command in invalid:
            with self.subTest(command=command), self.assertRaises(ValueError):
                plan_cartesian(command, self.targets, self.limits)

    def test_measured_joint_limits_are_enforced(self):
        targets = dict(self.targets)
        targets["left_arm_gripper"] = self.limits["left_arm_gripper"][1] - .1
        with self.assertRaisesRegex(ValueError, "left_arm_gripper"):
            plan_cartesian({"left": {"gripper": 1}}, targets, self.limits)

    def test_every_angular_target_has_a_hard_jump_limit(self):
        for side in ("left", "right"):
            planned = plan_cartesian({side: {"reach": .003, "height": .003}}, self.targets, self.limits)
            for name, value in planned.items():
                if not name.endswith("gripper"):
                    self.assertLessEqual(abs(value - self.targets[name]), MAX_JOINT_STEP_DEG)

    def test_small_steps_accumulate_in_the_target_state(self):
        targets = dict(self.targets)
        start = targets["right_arm_shoulder_lift"]
        first = plan_cartesian({"right": {"height": .003}}, targets, self.limits)
        targets.update(first)
        second = plan_cartesian({"right": {"height": .003}}, targets, self.limits)
        targets.update(second)
        self.assertGreater(abs(targets["right_arm_shoulder_lift"] - start),
                           abs(first["right_arm_shoulder_lift"] - start))

    def test_previously_blocked_right_arm_extension_is_valid(self):
        targets = dict(self.targets)
        targets.update({
            "right_arm_shoulder_pan": -24.175824175824175,
            "right_arm_shoulder_lift": -11.912087912087912,
            "right_arm_elbow_flex": 18.725274725274726,
            "right_arm_wrist_flex": 44.043956043956044,
            "right_arm_wrist_roll": -0.3076923076923077,
            "right_arm_gripper": 5.320600272851296,
        })
        before = arm_pose("right", targets)
        planned = plan_cartesian({"right": {"reach": .003}}, targets, self.limits)
        after = arm_pose("right", {**targets, **planned})
        self.assertGreater(after["reach"], before["reach"])
        self.assertLessEqual(after["reach"] - before["reach"], .003000001)
        for name, value in planned.items():
            if not name.endswith("gripper"):
                self.assertLessEqual(abs(value - targets[name]), MAX_JOINT_STEP_DEG)


if __name__ == "__main__":
    unittest.main()
