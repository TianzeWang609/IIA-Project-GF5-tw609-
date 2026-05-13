from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from skeleton_profiles import COURSE_BODY_24_PROFILE


Mat3f = np.ndarray
Vec3f = np.ndarray
CLIP_NAMES = ("Walk", "Wave")


class Joint(IntEnum):
    PELVIS = 0
    LEFT_HIP = 1
    RIGHT_HIP = 2
    SPINE1 = 3
    LEFT_KNEE = 4
    RIGHT_KNEE = 5
    SPINE2 = 6
    LEFT_ANKLE = 7
    RIGHT_ANKLE = 8
    SPINE3 = 9
    LEFT_FOOT = 10
    RIGHT_FOOT = 11
    NECK = 12
    LEFT_COLLAR = 13
    RIGHT_COLLAR = 14
    HEAD = 15
    LEFT_SHOULDER = 16
    RIGHT_SHOULDER = 17
    LEFT_ELBOW = 18
    RIGHT_ELBOW = 19
    LEFT_WRIST = 20
    RIGHT_WRIST = 21
    LEFT_HAND = 22
    RIGHT_HAND = 23


@dataclass
class PoseSample:
    profile_name: str
    root_offset: Vec3f
    local_rotations: list[Mat3f]


def rotation_x(angle: float) -> Mat3f:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]],
        dtype=np.float32,
    )


def rotation_y(angle: float) -> Mat3f:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]],
        dtype=np.float32,
    )


def rotation_z(angle: float) -> Mat3f:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def make_identity_rotations() -> list[Mat3f]:
    return [np.eye(3, dtype=np.float32) for _ in COURSE_BODY_24_PROFILE.joint_names]


def walk_clip(t: float) -> PoseSample:
    phase = t * 2.2
    leg_phase = math.sin(phase)
    left_forward = max(0.0, leg_phase)
    right_forward = max(0.0, -leg_phase)
    left_back = max(0.0, -leg_phase)
    right_back = max(0.0, leg_phase)

    left_hip = 0.62 * left_forward - 0.26 * left_back
    right_hip = 0.62 * right_forward - 0.26 * right_back
    left_knee = -0.92 * left_forward
    right_knee = -0.92 * right_forward
    left_ankle = 0.20 * left_forward - 0.08 * left_back
    right_ankle = 0.20 * right_forward - 0.08 * right_back

    arm_swing = 0.34 * leg_phase
    bob = 0.018 * (1.0 - math.cos(phase * 2.0))
    local_rotations = make_identity_rotations()
    local_rotations[Joint.PELVIS] = rotation_x(0.04) @ rotation_z(0.025 * leg_phase)
    local_rotations[Joint.SPINE2] = rotation_z(-0.04 * leg_phase)
    local_rotations[Joint.NECK] = rotation_z(0.02 * leg_phase)
    local_rotations[Joint.LEFT_HIP] = rotation_x(left_hip)
    local_rotations[Joint.RIGHT_HIP] = rotation_x(right_hip)
    local_rotations[Joint.LEFT_KNEE] = rotation_x(left_knee)
    local_rotations[Joint.RIGHT_KNEE] = rotation_x(right_knee)
    local_rotations[Joint.LEFT_ANKLE] = rotation_x(left_ankle)
    local_rotations[Joint.RIGHT_ANKLE] = rotation_x(right_ankle)
    local_rotations[Joint.LEFT_SHOULDER] = rotation_x(-arm_swing) @ rotation_z(0.08)
    local_rotations[Joint.RIGHT_SHOULDER] = rotation_x(arm_swing) @ rotation_z(-0.08)
    local_rotations[Joint.LEFT_ELBOW] = rotation_x(-0.16 - 0.05 * left_forward)
    local_rotations[Joint.RIGHT_ELBOW] = rotation_x(-0.16 - 0.05 * right_forward)

    return PoseSample(
        profile_name=COURSE_BODY_24_PROFILE.name,
        root_offset=np.asarray([0.0, 0.0, bob], dtype=np.float32),
        local_rotations=local_rotations,
    )


def wave_clip(t: float) -> PoseSample:
    phase = t * 1.6
    sway = math.sin(phase)
    wave = math.sin(phase * 3.0)
    local_rotations = make_identity_rotations()
    local_rotations[Joint.PELVIS] = rotation_z(0.02 * sway)
    local_rotations[Joint.SPINE2] = rotation_z(-0.08 + 0.02 * sway)
    local_rotations[Joint.NECK] = rotation_z(0.08 - 0.015 * sway)
    local_rotations[Joint.RIGHT_SHOULDER] = rotation_y(-1.02 + 0.28 * wave) @ rotation_z(-0.10)
    local_rotations[Joint.RIGHT_ELBOW] = rotation_y(-0.65)
    local_rotations[Joint.RIGHT_WRIST] = rotation_z(-0.08 * wave)
    local_rotations[Joint.LEFT_SHOULDER] = rotation_z(-0.16) @ rotation_y(0.14)
    local_rotations[Joint.LEFT_ELBOW] = rotation_x(-0.10)
    local_rotations[Joint.LEFT_HIP] = rotation_x(0.03 * sway)
    local_rotations[Joint.RIGHT_HIP] = rotation_x(-0.03 * sway)

    return PoseSample(
        profile_name=COURSE_BODY_24_PROFILE.name,
        root_offset=np.zeros(3, dtype=np.float32),
        local_rotations=local_rotations,
    )


def sample_motion_clip(clip_name: str, t: float) -> PoseSample:
    if clip_name == "Walk":
        return walk_clip(t)
    if clip_name == "Wave":
        return wave_clip(t)
    raise ValueError(f"Unknown clip: {clip_name}")
