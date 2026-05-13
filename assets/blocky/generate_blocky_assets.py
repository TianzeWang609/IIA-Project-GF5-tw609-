from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt


Vec3 = npt.NDArray[np.float64]

SMPL24_PROXY_NAME = "SMPL-24 Proxy"
SMPL24_JOINT_NAMES = (
    "pelvis",
    "left_hip",
    "right_hip",
    "spine1",
    "left_knee",
    "right_knee",
    "spine2",
    "left_ankle",
    "right_ankle",
    "spine3",
    "left_foot",
    "right_foot",
    "neck",
    "left_collar",
    "right_collar",
    "head",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hand",
    "right_hand",
)
SMPL24_PARENTS = (
    -1,
    0,
    0,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    9,
    9,
    12,
    13,
    14,
    16,
    17,
    18,
    19,
    20,
    21,
)

# SMPL-X neutral template joints collapsed to the course SMPL-24 body profile and
# rotated into GF5 viewer body space (+Z up, +Y forward, anatomical right +X).
# The pelvis is centered in X/Y and the lowest foot joint is on the ground. This
# baked snapshot lets the Part 3 proxy match the SMPL motion convention without
# requiring licensed model files at student runtime.
SMPL24_TEMPLATE_REST_JOINTS_VIEWER = np.asarray(
    [
        [0.0, 0.0, 0.935344],
        [-0.058189, -0.026001, 0.842581],
        [0.063267, -0.02125, 0.831436],
        [0.002763, -0.027618, 1.045235],
        [-0.112885, -0.035397, 0.463827],
        [0.107477, -0.038074, 0.469056],
        [-0.006685, -0.033558, 1.177088],
        [-0.069431, -0.067273, 0.060768],
        [0.092061, -0.058267, 0.058329],
        [0.004645, -0.005111, 1.229323],
        [-0.116689, 0.050943, 0.002771],
        [0.130873, 0.060782, 0.0],
        [0.01681, -0.036726, 1.39449],
        [-0.041719, -0.012331, 1.314267],
        [0.05234, -0.018511, 1.313662],
        [-0.007974, -0.015989, 1.554942],
        [-0.160958, -0.027792, 1.371995],
        [0.154918, -0.031179, 1.367186],
        [-0.415081, -0.070251, 1.299845],
        [0.426068, -0.057646, 1.330694],
        [-0.667067, -0.072723, 1.323066],
        [0.675335, -0.072971, 1.326161],
        [-0.753753, -0.078746, 1.311706],
        [0.759999, -0.078746, 1.311706],
    ],
    dtype=np.float64,
)


def as_vec3(values: tuple[float, float, float] | list[float]) -> Vec3:
    return np.asarray(values, dtype=np.float64)


def normalize(vector: Vec3) -> Vec3:
    length = np.linalg.norm(vector)
    if length == 0.0:
        raise ValueError("Cannot normalize a zero-length vector.")
    return vector / length


def orthonormal_basis(axis: Vec3) -> tuple[Vec3, Vec3]:
    axis = normalize(axis)
    helper = as_vec3([0.0, 0.0, 1.0])
    if abs(float(np.dot(axis, helper))) > 0.9:
        helper = as_vec3([0.0, 1.0, 0.0])
    side = normalize(np.cross(axis, helper))
    up = normalize(np.cross(side, axis))
    return side, up


def make_box(center: Vec3, size: Vec3) -> tuple[list[list[float]], list[list[int]]]:
    sx, sy, sz = size / 2.0
    offsets = [
        as_vec3([-sx, -sy, -sz]),
        as_vec3([sx, -sy, -sz]),
        as_vec3([sx, sy, -sz]),
        as_vec3([-sx, sy, -sz]),
        as_vec3([-sx, -sy, sz]),
        as_vec3([sx, -sy, sz]),
        as_vec3([sx, sy, sz]),
        as_vec3([-sx, sy, sz]),
    ]
    vertices = [[round(float(v), 6) for v in center + offset] for offset in offsets]
    faces = [
        [0, 1, 2],
        [0, 2, 3],
        [4, 5, 6],
        [4, 6, 7],
        [0, 1, 5],
        [0, 5, 4],
        [1, 2, 6],
        [1, 6, 5],
        [2, 3, 7],
        [2, 7, 6],
        [3, 0, 4],
        [3, 4, 7],
    ]
    return vertices, faces


def make_bone_block(
    end: Vec3,
    width: float,
    depth: float,
) -> tuple[list[list[float]], list[list[int]]]:
    axis = end
    side, up = orthonormal_basis(axis)
    ring_start = [
        side * -width + up * -depth,
        side * width + up * -depth,
        side * width + up * depth,
        side * -width + up * depth,
    ]
    ring_end = [offset + axis for offset in ring_start]

    vertices = [
        [round(float(v), 6) for v in vertex]
        for vertex in [*ring_start, *ring_end]
    ]
    faces = [
        [0, 1, 2],
        [0, 2, 3],
        [4, 6, 5],
        [4, 7, 6],
        [0, 5, 1],
        [0, 4, 5],
        [1, 6, 2],
        [1, 5, 6],
        [2, 7, 3],
        [2, 6, 7],
        [3, 4, 0],
        [3, 7, 4],
    ]
    return vertices, faces


def compute_rest_positions(joints: list[dict[str, Any]]) -> list[Vec3]:
    positions: list[Vec3] = [np.zeros(3, dtype=np.float64) for _ in joints]
    for idx, joint in enumerate(joints):
        parent = int(joint["parent"])
        local = as_vec3(joint["translation"])
        if parent < 0:
            positions[idx] = local
        else:
            positions[idx] = positions[parent] + local
    return positions


def add_bone_part(
    parts: list[dict[str, Any]],
    part_name: str,
    joint_name: str,
    end: list[float],
    width: float,
    depth: float,
    color: list[int],
) -> None:
    vertices, faces = make_bone_block(as_vec3(end), width, depth)
    parts.append(
        {
            "name": part_name,
            "joint": joint_name,
            "vertices": vertices,
            "faces": faces,
            "color": color,
            "flat_shading": True,
            "side": "double",
        }
    )


def add_joint_box(
    parts: list[dict[str, Any]],
    part_name: str,
    joint_name: str,
    center: list[float],
    size: list[float],
    color: list[int],
) -> None:
    vertices, faces = make_box(as_vec3(center), as_vec3(size))
    parts.append(
        {
            "name": part_name,
            "joint": joint_name,
            "vertices": vertices,
            "faces": faces,
            "color": color,
            "flat_shading": True,
            "side": "double",
        }
    )


def add_head_face_patches(
    parts: list[dict[str, Any]],
    *,
    head_size: list[float],
    head_center: list[float],
    color: list[int],
) -> None:
    head_half_depth = head_size[1] / 2.0
    patch_depth = 0.008
    face_y = head_center[1] + head_half_depth + patch_depth / 2.0 + 0.002
    for side, eye_x in (("left", -0.038), ("right", 0.038)):
        add_joint_box(
            parts,
            f"{side}_eye_patch",
            "head",
            [head_center[0] + eye_x, face_y, head_center[2] + 0.026],
            [0.026, patch_depth, 0.018],
            color,
        )
    add_joint_box(
        parts,
        "nose_patch",
        "head",
        [head_center[0], face_y + 0.001, head_center[2] - 0.004],
        [0.018, patch_depth * 1.2, 0.038],
        color,
    )


def base_joint_spec(
    root_height: float,
    shoulder_span: float,
    upper_arm: float,
    forearm: float,
    hip_offset: float,
    thigh: float,
    shin: float,
    foot: float,
) -> list[dict[str, Any]]:
    return [
        {"name": "root", "parent": -1, "translation": [0.0, 0.0, root_height]},
        {"name": "spine", "parent": 0, "translation": [0.0, 0.0, 0.18]},
        {"name": "chest", "parent": 1, "translation": [0.0, 0.0, 0.18]},
        {"name": "neck", "parent": 2, "translation": [0.0, 0.0, 0.12]},
        {"name": "head", "parent": 3, "translation": [0.0, 0.0, 0.10]},
        {"name": "left_shoulder", "parent": 2, "translation": [-shoulder_span, 0.0, 0.05]},
        {"name": "left_elbow", "parent": 5, "translation": [-upper_arm, 0.0, 0.0]},
        {"name": "left_wrist", "parent": 6, "translation": [-forearm, 0.0, 0.0]},
        {"name": "right_shoulder", "parent": 2, "translation": [shoulder_span, 0.0, 0.05]},
        {"name": "right_elbow", "parent": 8, "translation": [upper_arm, 0.0, 0.0]},
        {"name": "right_wrist", "parent": 9, "translation": [forearm, 0.0, 0.0]},
        {"name": "left_hip", "parent": 0, "translation": [-hip_offset, 0.0, -0.06]},
        {"name": "left_knee", "parent": 11, "translation": [0.0, 0.0, -thigh]},
        {"name": "left_ankle", "parent": 12, "translation": [0.0, 0.0, -shin]},
        {"name": "left_toe", "parent": 13, "translation": [0.0, foot, 0.0]},
        {"name": "right_hip", "parent": 0, "translation": [hip_offset, 0.0, -0.06]},
        {"name": "right_knee", "parent": 15, "translation": [0.0, 0.0, -thigh]},
        {"name": "right_ankle", "parent": 16, "translation": [0.0, 0.0, -shin]},
        {"name": "right_toe", "parent": 17, "translation": [0.0, foot, 0.0]},
    ]


def build_rigid_asset(
    name: str,
    description: str,
    color_body: list[int],
    color_joints: list[int],
    proportions: dict[str, float],
) -> dict[str, Any]:
    root_height = 0.06 + proportions["thigh"] + proportions["shin"] + proportions["limb_depth"] * 0.8
    joints = base_joint_spec(
        root_height=root_height,
        shoulder_span=proportions["shoulder_span"],
        upper_arm=proportions["upper_arm"],
        forearm=proportions["forearm"],
        hip_offset=proportions["hip_offset"],
        thigh=proportions["thigh"],
        shin=proportions["shin"],
        foot=proportions["foot"],
    )
    rest_positions = compute_rest_positions(joints)
    parts: list[dict[str, Any]] = []

    torso_width = proportions["torso_width"]
    torso_depth = proportions["torso_depth"]
    limb_width = proportions["limb_width"]
    limb_depth = proportions["limb_depth"]
    joint_size = proportions["joint_size"]

    add_bone_part(parts, "pelvis", "root", [0.0, 0.0, 0.12], torso_width, torso_depth, color_body)
    add_bone_part(parts, "spine", "spine", [0.0, 0.0, 0.18], torso_width * 0.9, torso_depth, color_body)
    add_bone_part(parts, "chest", "chest", [0.0, 0.0, 0.12], torso_width * 1.1, torso_depth * 1.1, color_body)
    add_bone_part(parts, "neck", "neck", [0.0, 0.0, 0.08], torso_width * 0.35, torso_depth * 0.35, color_body)

    add_bone_part(parts, "left_upper_arm", "left_shoulder", joints[6]["translation"], limb_width, limb_depth, color_body)
    add_bone_part(parts, "left_forearm", "left_elbow", joints[7]["translation"], limb_width * 0.9, limb_depth * 0.9, color_body)
    add_bone_part(parts, "right_upper_arm", "right_shoulder", joints[9]["translation"], limb_width, limb_depth, color_body)
    add_bone_part(parts, "right_forearm", "right_elbow", joints[10]["translation"], limb_width * 0.9, limb_depth * 0.9, color_body)

    add_bone_part(parts, "left_thigh", "left_hip", joints[12]["translation"], limb_width * 1.15, limb_depth * 1.15, color_body)
    add_bone_part(parts, "left_shin", "left_knee", joints[13]["translation"], limb_width, limb_depth, color_body)
    add_bone_part(parts, "left_foot", "left_ankle", joints[14]["translation"], limb_width * 0.95, limb_depth * 0.8, color_body)
    add_bone_part(parts, "right_thigh", "right_hip", joints[16]["translation"], limb_width * 1.15, limb_depth * 1.15, color_body)
    add_bone_part(parts, "right_shin", "right_knee", joints[17]["translation"], limb_width, limb_depth, color_body)
    add_bone_part(parts, "right_foot", "right_ankle", joints[18]["translation"], limb_width * 0.95, limb_depth * 0.8, color_body)

    add_joint_box(parts, "root_joint", "root", [0.0, 0.0, 0.03], [joint_size * 1.6, joint_size * 1.2, joint_size * 1.4], color_joints)
    add_joint_box(parts, "chest_joint", "chest", [0.0, 0.0, 0.02], [joint_size * 1.2, joint_size * 1.2, joint_size * 1.2], color_joints)
    add_joint_box(parts, "head_box", "head", [0.0, 0.0, 0.08], [0.16, 0.14, 0.16], color_joints)
    add_joint_box(parts, "left_shoulder_joint", "left_shoulder", [0.0, 0.0, 0.0], [joint_size, joint_size, joint_size], color_joints)
    add_joint_box(parts, "left_elbow_joint", "left_elbow", [0.0, 0.0, 0.0], [joint_size * 0.95, joint_size * 0.95, joint_size * 0.95], color_joints)
    add_joint_box(parts, "left_wrist_joint", "left_wrist", [0.0, 0.0, 0.0], [joint_size * 0.8, joint_size * 0.8, joint_size * 0.8], color_joints)
    add_joint_box(parts, "right_shoulder_joint", "right_shoulder", [0.0, 0.0, 0.0], [joint_size, joint_size, joint_size], color_joints)
    add_joint_box(parts, "right_elbow_joint", "right_elbow", [0.0, 0.0, 0.0], [joint_size * 0.95, joint_size * 0.95, joint_size * 0.95], color_joints)
    add_joint_box(parts, "right_wrist_joint", "right_wrist", [0.0, 0.0, 0.0], [joint_size * 0.8, joint_size * 0.8, joint_size * 0.8], color_joints)
    add_joint_box(parts, "left_hip_joint", "left_hip", [0.0, 0.0, 0.0], [joint_size, joint_size, joint_size], color_joints)
    add_joint_box(parts, "left_knee_joint", "left_knee", [0.0, 0.0, 0.0], [joint_size, joint_size, joint_size], color_joints)
    add_joint_box(parts, "left_ankle_joint", "left_ankle", [0.0, 0.0, 0.0], [joint_size * 0.9, joint_size * 0.9, joint_size * 0.9], color_joints)
    add_joint_box(parts, "right_hip_joint", "right_hip", [0.0, 0.0, 0.0], [joint_size, joint_size, joint_size], color_joints)
    add_joint_box(parts, "right_knee_joint", "right_knee", [0.0, 0.0, 0.0], [joint_size, joint_size, joint_size], color_joints)
    add_joint_box(parts, "right_ankle_joint", "right_ankle", [0.0, 0.0, 0.0], [joint_size * 0.9, joint_size * 0.9, joint_size * 0.9], color_joints)

    return {
        "asset_format": "gf5_rigid_character",
        "asset_version": 1,
        "name": name,
        "description": description,
        "units": "meters",
        "display": {
            "up_axis": [0.0, 0.0, 1.0],
            "forward_axis": [0.0, 1.0, 0.0],
            "anatomical_right_axis": [1.0, 0.0, 0.0],
        },
        "skeleton": {
            "joints": [
                {
                    "name": joint["name"],
                    "parent": joint["parent"],
                    "translation": joint["translation"],
                    "rest_position": [round(float(v), 6) for v in rest_positions[idx]],
                }
                for idx, joint in enumerate(joints)
            ],
            "bone_edges": [
                [int(joint["parent"]), idx]
                for idx, joint in enumerate(joints)
                if int(joint["parent"]) >= 0
            ],
        },
        "rigid_parts": parts,
    }


def smpl24_bone_size(parent_name: str, child_name: str) -> tuple[float, float]:
    names = {parent_name, child_name}
    if names & {"spine1", "spine2", "spine3", "neck"}:
        return 0.055, 0.045
    if names & {"left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"}:
        return 0.044, 0.04
    if names & {"left_foot", "right_foot"}:
        return 0.042, 0.035
    if names & {"left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist"}:
        return 0.034, 0.032
    if names & {"left_hand", "right_hand"}:
        return 0.03, 0.028
    return 0.035, 0.032


def smpl24_joint_box_size(joint_name: str) -> list[float]:
    if joint_name == "pelvis":
        return [0.14, 0.10, 0.11]
    if joint_name in {"spine1", "spine2", "spine3"}:
        return [0.10, 0.08, 0.08]
    if joint_name == "head":
        return [0.16, 0.14, 0.16]
    if joint_name in {"left_foot", "right_foot"}:
        return [0.10, 0.15, 0.055]
    if joint_name in {"left_hand", "right_hand"}:
        return [0.08, 0.05, 0.07]
    if "shoulder" in joint_name or "elbow" in joint_name or "wrist" in joint_name:
        return [0.052, 0.052, 0.052]
    if "hip" in joint_name or "knee" in joint_name or "ankle" in joint_name:
        return [0.058, 0.058, 0.058]
    return [0.045, 0.045, 0.045]


def build_smpl24_proxy_asset() -> dict[str, Any]:
    rest_positions = SMPL24_TEMPLATE_REST_JOINTS_VIEWER
    joints: list[dict[str, Any]] = []
    for joint_index, joint_name in enumerate(SMPL24_JOINT_NAMES):
        parent_index = SMPL24_PARENTS[joint_index]
        rest_position = rest_positions[joint_index]
        if parent_index < 0:
            translation = rest_position
        else:
            translation = rest_position - rest_positions[parent_index]
        joints.append(
            {
                "name": joint_name,
                "parent": parent_index,
                "translation": [round(float(v), 6) for v in translation],
            }
        )

    body_color = [114, 180, 205]
    joint_color = [45, 65, 85]
    head_size = smpl24_joint_box_size("head")
    parts: list[dict[str, Any]] = []
    for child_index, parent_index in enumerate(SMPL24_PARENTS):
        if parent_index < 0:
            continue
        parent_name = SMPL24_JOINT_NAMES[parent_index]
        child_name = SMPL24_JOINT_NAMES[child_index]
        width, depth = smpl24_bone_size(parent_name, child_name)
        add_bone_part(
            parts,
            f"{parent_name}_to_{child_name}",
            parent_name,
            joints[child_index]["translation"],
            width,
            depth,
            body_color,
        )

    for joint_name in SMPL24_JOINT_NAMES:
        add_joint_box(
            parts,
            f"{joint_name}_joint",
            joint_name,
            [0.0, 0.0, 0.0],
            smpl24_joint_box_size(joint_name),
            joint_color,
        )

    add_head_face_patches(
        parts,
        head_size=head_size,
        head_center=[0.0, 0.0, 0.0],
        color=body_color,
    )

    return {
        "asset_format": "gf5_rigid_character",
        "asset_version": 2,
        "name": SMPL24_PROXY_NAME,
        "description": (
            "Part 3 SMPL-24 blocky proxy generated from the SMPL-X neutral "
            "template rest skeleton collapsed to the GF5 course body profile."
        ),
        "units": "meters",
        "display": {
            "up_axis": [0.0, 0.0, 1.0],
            "forward_axis": [0.0, 1.0, 0.0],
            "anatomical_right_axis": [1.0, 0.0, 0.0],
        },
        "skeleton": {
            "joints": [
                {
                    "name": joint["name"],
                    "parent": joint["parent"],
                    "translation": joint["translation"],
                    "rest_position": [round(float(v), 6) for v in rest_positions[idx]],
                }
                for idx, joint in enumerate(joints)
            ],
            "bone_edges": [
                [int(parent_index), child_index]
                for child_index, parent_index in enumerate(SMPL24_PARENTS)
                if int(parent_index) >= 0
            ],
        },
        "rigid_parts": parts,
    }


def write_asset(path: Path, asset: dict[str, Any]) -> None:
    path.write_text(json.dumps(asset, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    out_dir = Path(__file__).resolve().parent

    marigold = build_rigid_asset(
        name="Marigold",
        description="Part 1 rigid character for forward-kinematics exercises.",
        color_body=[230, 170, 90],
        color_joints=[80, 80, 80],
        proportions={
            "shoulder_span": 0.17,
            "upper_arm": 0.20,
            "forearm": 0.18,
            "hip_offset": 0.09,
            "thigh": 0.27,
            "shin": 0.25,
            "foot": 0.11,
            "torso_width": 0.09,
            "torso_depth": 0.06,
            "limb_width": 0.035,
            "limb_depth": 0.035,
            "joint_size": 0.06,
        },
    )
    azure = build_rigid_asset(
        name="Azure",
        description="Shorter, chunkier variant for testing asset loading in the viewer.",
        color_body=[110, 180, 210],
        color_joints=[45, 65, 85],
        proportions={
            "shoulder_span": 0.16,
            "upper_arm": 0.17,
            "forearm": 0.16,
            "hip_offset": 0.10,
            "thigh": 0.23,
            "shin": 0.21,
            "foot": 0.10,
            "torso_width": 0.10,
            "torso_depth": 0.07,
            "limb_width": 0.042,
            "limb_depth": 0.042,
            "joint_size": 0.065,
        },
    )
    smpl24_proxy = build_smpl24_proxy_asset()

    marigold_path = out_dir / "marigold.asset.json"
    azure_path = out_dir / "azure.asset.json"
    smpl24_proxy_path = out_dir / "smpl24_proxy.asset.json"
    write_asset(marigold_path, marigold)
    write_asset(azure_path, azure)
    write_asset(smpl24_proxy_path, smpl24_proxy)

    print(f"Wrote {marigold_path.name}, {azure_path.name}, and {smpl24_proxy_path.name}")
    print(
        "Marigold asset:",
        f"{len(marigold['skeleton']['joints'])} joints,",
        f"{len(marigold['rigid_parts'])} rigid parts",
    )
    print(
        "SMPL-24 proxy asset:",
        f"{len(smpl24_proxy['skeleton']['joints'])} joints,",
        f"{len(smpl24_proxy['rigid_parts'])} rigid parts",
    )


if __name__ == "__main__":
    main()
