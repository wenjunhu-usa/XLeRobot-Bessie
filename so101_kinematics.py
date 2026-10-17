"""Small planar kinematics model used by Bessie's incremental arm planner."""

import math


class SO101Kinematics:
    """Forward kinematics for Bessie's SO-101 shoulder and elbow links."""

    def __init__(self, l1=0.1159, l2=0.1350):
        self.l1 = l1
        self.l2 = l2

    def forward_kinematics(self, shoulder_deg, elbow_deg):
        shoulder_axis = math.radians(90 - shoulder_deg)
        elbow_axis = math.radians(elbow_deg + 90)
        shoulder_offset = math.atan2(0.028, 0.11257)
        elbow_offset = math.atan2(0.0052, 0.1349) + shoulder_offset
        shoulder = shoulder_axis - shoulder_offset
        elbow = elbow_axis - elbow_offset
        reach = self.l1 * math.cos(shoulder) + self.l2 * math.cos(shoulder + elbow - math.pi)
        height = self.l1 * math.sin(shoulder) + self.l2 * math.sin(shoulder + elbow - math.pi)
        return reach, height
