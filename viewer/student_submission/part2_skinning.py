from __future__ import annotations

import numpy as np


def make_one_hot_skinning_weights(weights: np.ndarray) -> np.ndarray:
    """Student part-2 task: convert a dense weight matrix into one-hot weights."""
    weights = np.asarray(weights, dtype=np.float32)

    max_joint_indices = np.argmax(weights, axis=1)

    one_hot = np.zeros_like(weights, dtype=np.float32)
    vertex_indices = np.arange(weights.shape[0])
    one_hot[vertex_indices, max_joint_indices] = 1.0

    return one_hot


def skin_smpl_mesh(
    model_data: object,
    world_rotations: np.ndarray,
    world_positions: np.ndarray,
    *,
    use_blended_weights: bool,
) -> np.ndarray:
    """Student part-2 task: pose the SMPL mesh with one-hot or blended weights."""
    rest_vertices = np.asarray(model_data.rest_vertices, dtype=np.float32)
    rest_joints = np.asarray(model_data.rest_joints, dtype=np.float32)
    world_rotations = np.asarray(world_rotations, dtype=np.float32)
    world_positions = np.asarray(world_positions, dtype=np.float32)

    if use_blended_weights:
        weights = np.asarray(model_data.skinning_weights, dtype=np.float32)
    else:
        weights = make_one_hot_skinning_weights(model_data.skinning_weights)

    offsets = rest_vertices[:, None, :] - rest_joints[None, :, :]
    rotated_offsets = np.einsum("jab,njb->nja", world_rotations, offsets)
    transformed_vertices = rotated_offsets + world_positions[None, :, :]

    posed_vertices = np.sum(weights[:, :, None] * transformed_vertices, axis=1)

    return posed_vertices.astype(np.float32)