from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from implementation_loader import get_part2_skinning_module
from motion_sequences import PoseSample
from skeleton_profiles import COURSE_BODY_24_PROFILE, SMPL_24_PROFILE, retarget_local_rotations


Mat3f = np.ndarray
Vec3f = np.ndarray

# Convert SMPL-native package coordinates into the viewer/course body convention.
#
# SMPL-family data uses +Y as up and its +X side is anatomical left.
# GF5 uses +Z up, +Y forward, and for a character facing +Y anatomical right
# is +X. The extra X flip is intentional: without it, swapping Y/Z is a
# reflection (determinant -1), which mirrors left/right body motion.
SMPL_TO_VIEWER_ROTATION = np.asarray(
    [
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=np.float32,
)
if not np.isclose(np.linalg.det(SMPL_TO_VIEWER_ROTATION), 1.0):
    raise RuntimeError("SMPL_TO_VIEWER_ROTATION must be a proper rotation, not a reflection.")


@dataclass
class SmplModelData:
    model_path: Path
    model: Any
    faces: np.ndarray
    rest_vertices: np.ndarray
    rest_joints: np.ndarray
    skinning_weights: np.ndarray
    one_hot_skinning_weights: np.ndarray
    ground_translation: Vec3f
    parents: tuple[int, ...]
    joint_names: tuple[str, ...]
    skinning_setup_error: str | None = None


def rotate_points_to_viewer(points: np.ndarray) -> np.ndarray:
    return np.asarray(points, dtype=np.float32) @ SMPL_TO_VIEWER_ROTATION.T


def rotate_points_to_smpl(points: np.ndarray) -> np.ndarray:
    return np.asarray(points, dtype=np.float32) @ SMPL_TO_VIEWER_ROTATION


def rotate_matrix_to_smpl(rotation: Mat3f) -> Mat3f:
    return (
        SMPL_TO_VIEWER_ROTATION.T
        @ np.asarray(rotation, dtype=np.float32)
        @ SMPL_TO_VIEWER_ROTATION
    )


def rotate_matrix_to_viewer(rotation: Mat3f) -> Mat3f:
    return (
        SMPL_TO_VIEWER_ROTATION
        @ np.asarray(rotation, dtype=np.float32)
        @ SMPL_TO_VIEWER_ROTATION.T
    )


def axis_angle_to_matrix(axis_angle: np.ndarray) -> Mat3f:
    axis_angle = np.asarray(axis_angle, dtype=np.float32)
    if axis_angle.shape != (3,):
        raise ValueError(f"Expected shape (3,), got {axis_angle.shape}")

    angle = float(np.linalg.norm(axis_angle))
    if angle < 1e-8:
        return np.eye(3, dtype=np.float32)

    axis = axis_angle / angle
    x, y, z = [float(v) for v in axis]
    skew = np.asarray(
        [
            [0.0, -z, y],
            [z, 0.0, -x],
            [-y, x, 0.0],
        ],
        dtype=np.float32,
    )
    identity = np.eye(3, dtype=np.float32)
    return identity + np.sin(angle) * skew + (1.0 - np.cos(angle)) * (skew @ skew)


def smpl_axis_angle_pose_to_rotations(axis_angles: np.ndarray) -> list[Mat3f]:
    axis_angles = np.asarray(axis_angles, dtype=np.float32)
    expected_shape = (len(SMPL_24_PROFILE.joint_names), 3)
    if axis_angles.shape != expected_shape:
        raise ValueError(f"Expected SMPL axis-angle pose with shape {expected_shape}, got {axis_angles.shape}")
    return [
        rotate_matrix_to_viewer(axis_angle_to_matrix(axis_angles[joint_index]))
        for joint_index in range(axis_angles.shape[0])
    ]


def smpl_axis_angle_pose_to_sample(
    axis_angles: np.ndarray,
    root_offset: Vec3f | None = None,
) -> PoseSample:
    if root_offset is None:
        root_offset = np.zeros(3, dtype=np.float32)
    native_rotations = smpl_axis_angle_pose_to_rotations(axis_angles)
    canonical_rotations = retarget_local_rotations(
        native_rotations,
        SMPL_24_PROFILE.name,
        COURSE_BODY_24_PROFILE.joint_names,
        COURSE_BODY_24_PROFILE.name,
    )
    return PoseSample(
        profile_name=COURSE_BODY_24_PROFILE.name,
        root_offset=np.asarray(root_offset, dtype=np.float32),
        local_rotations=canonical_rotations,
    )


def load_smpl_model_data(model_path: str | Path) -> SmplModelData:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    import smplx
    import torch

    model_path = Path(model_path).resolve()
    model = smplx.SMPL(str(model_path))
    with torch.no_grad():
        output = model()

    rest_vertices_smpl = output.vertices[0].detach().cpu().numpy().astype(np.float32)
    rest_joints_smpl = output.joints[0, : len(SMPL_24_PROFILE.joint_names)].detach().cpu().numpy().astype(np.float32)
    rest_vertices = rotate_points_to_viewer(rest_vertices_smpl)
    rest_joints = rotate_points_to_viewer(rest_joints_smpl)
    skinning_weights = model.lbs_weights.detach().cpu().numpy().astype(np.float32)
    skinning_setup_error = None
    try:
        one_hot_skinning_weights = validate_one_hot_skinning_weights(
            make_one_hot_skinning_weights(skinning_weights),
            expected_shape=skinning_weights.shape,
        )
    except Exception as exc:
        one_hot_skinning_weights = np.zeros_like(skinning_weights, dtype=np.float32)
        skinning_setup_error = (
            "Part 2 one-hot skinning is not ready: "
            f"{format_exception_summary(exc)}"
        )
    ground_translation = np.asarray([0.0, 0.0, -float(rest_vertices[:, 2].min())], dtype=np.float32)
    faces = np.asarray(model.faces, dtype=np.uint32)
    parents = tuple(int(parent) for parent in model.parents.detach().cpu().numpy().tolist())

    return SmplModelData(
        model_path=model_path,
        model=model,
        faces=faces,
        rest_vertices=rest_vertices,
        rest_joints=rest_joints,
        skinning_weights=skinning_weights,
        one_hot_skinning_weights=one_hot_skinning_weights,
        ground_translation=ground_translation,
        parents=parents,
        joint_names=SMPL_24_PROFILE.joint_names,
        skinning_setup_error=skinning_setup_error,
    )


def make_one_hot_skinning_weights(weights: np.ndarray) -> np.ndarray:
    return get_part2_skinning_module().make_one_hot_skinning_weights(weights)


def format_exception_summary(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def validate_one_hot_skinning_weights(
    weights: np.ndarray,
    *,
    expected_shape: tuple[int, int],
) -> np.ndarray:
    weights = np.asarray(weights, dtype=np.float32)
    if weights.shape != expected_shape:
        raise ValueError(
            f"make_one_hot_skinning_weights returned shape {weights.shape}; "
            f"expected {expected_shape}."
        )
    if not np.all(np.isfinite(weights)):
        raise ValueError("make_one_hot_skinning_weights returned non-finite values.")
    if not np.allclose(weights.sum(axis=1), 1.0, atol=1e-4):
        raise ValueError("one-hot rows must sum to 1.")
    binary_mask = np.isclose(weights, 0.0, atol=1e-4) | np.isclose(weights, 1.0, atol=1e-4)
    if not np.all(binary_mask):
        raise ValueError("one-hot weights must contain only 0 or 1 values.")
    return weights.astype(np.float32)


def validate_skinned_vertices(vertices: np.ndarray, *, expected_shape: tuple[int, int]) -> np.ndarray:
    vertices = np.asarray(vertices, dtype=np.float32)
    if vertices.shape != expected_shape:
        raise ValueError(
            f"skin_smpl_mesh returned shape {vertices.shape}; expected {expected_shape}."
        )
    if not np.all(np.isfinite(vertices)):
        raise ValueError("skin_smpl_mesh returned non-finite vertex positions.")
    if float(np.ptp(vertices, axis=0).max()) < 1e-5:
        raise ValueError(
            "skin_smpl_mesh returned a collapsed mesh; implement the vertex transforms "
            "instead of returning zeros."
        )
    return vertices.astype(np.float32)


def get_skinning_weights(
    model_data: SmplModelData,
    *,
    use_blended_weights: bool,
) -> np.ndarray:
    return (
        np.asarray(model_data.skinning_weights, dtype=np.float32)
        if use_blended_weights
        else np.asarray(model_data.one_hot_skinning_weights, dtype=np.float32)
    )


def skin_smpl_mesh(
    model_data: SmplModelData,
    world_rotations: np.ndarray,
    world_positions: np.ndarray,
    *,
    use_blended_weights: bool,
) -> np.ndarray:
    return validate_skinned_vertices(
        get_part2_skinning_module().skin_smpl_mesh(
            model_data,
            world_rotations,
            world_positions,
            use_blended_weights=use_blended_weights,
        ),
        expected_shape=np.asarray(model_data.rest_vertices).shape,
    )


def pose_smpl_model(
    model_data: SmplModelData,
    local_rotations: list[Mat3f],
    root_offset: Vec3f,
) -> tuple[np.ndarray, np.ndarray]:
    if len(local_rotations) != len(model_data.joint_names):
        raise ValueError(
            f"Expected {len(model_data.joint_names)} SMPL joint rotations, got {len(local_rotations)}."
        )

    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    import torch

    local_rotations_smpl = [rotate_matrix_to_smpl(rotation) for rotation in local_rotations]
    global_orient = torch.from_numpy(
        np.asarray(local_rotations_smpl[0], dtype=np.float32)[None, None, :, :]
    )
    body_pose = torch.from_numpy(
        np.asarray(local_rotations_smpl[1:], dtype=np.float32)[None, :, :, :]
    )
    translation_viewer = np.asarray(model_data.ground_translation + root_offset, dtype=np.float32)
    transl = torch.from_numpy(
        rotate_points_to_smpl(translation_viewer[None, :])
    )
    with torch.no_grad():
        output = model_data.model(
            global_orient=global_orient,
            body_pose=body_pose,
            transl=transl,
            pose2rot=False,
        )

    vertices = rotate_points_to_viewer(
        output.vertices[0].detach().cpu().numpy().astype(np.float32)
    )
    joints = rotate_points_to_viewer(
        output.joints[0, : len(model_data.joint_names)].detach().cpu().numpy().astype(np.float32)
    )
    return vertices, joints
