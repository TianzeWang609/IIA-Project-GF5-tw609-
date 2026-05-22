from __future__ import annotations

import argparse
import copy
import html
import io
import json
import math
import os
import re
import shutil
import stat
import subprocess
import time
import traceback
import webbrowser
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import viser
os.environ.setdefault("MPLCONFIGDIR", str(Path("/tmp") / "gf5_matplotlib"))
from matplotlib import colormaps
from viser._messages import GuiSliderMark

from implementation_loader import (
    VALID_IMPLEMENTATION_SOURCES,
    get_part1_fk_module,
    set_active_implementation_sources,
)
from motion_sequences import (
    CLIP_NAMES,
    PoseSample,
    rotation_x,
    rotation_y,
    rotation_z,
    sample_motion_clip,
)
from skeleton_profiles import (
    COURSE_BODY_24_PROFILE,
    SMPL_24_PROFILE,
    compute_topological_order,
    detect_profile,
    get_profile,
    retarget_local_rotations,
)
from smpl_support import (
    SmplModelData,
    format_exception_summary,
    get_skinning_weights,
    load_smpl_model_data,
    rotate_points_to_viewer,
    skin_smpl_mesh,
)


Vec3f = np.ndarray
Mat3f = np.ndarray


@dataclass
class JointSpec:
    name: str
    parent: int
    translation: Vec3f
    rest_position: Vec3f


@dataclass
class PartSpec:
    name: str
    joint_index: int
    vertices: np.ndarray
    faces: np.ndarray
    surface_points: np.ndarray
    color: tuple[int, int, int]
    flat_shading: bool
    side: str


@dataclass
class AssetData:
    path: Path
    label: str
    joints: list[JointSpec]
    parts: list[PartSpec]
    bone_edges: list[tuple[int, int]]
    joint_names: tuple[str, ...]
    joint_lookup: dict[str, int]
    topological_order: tuple[int, ...]
    profile_name: str | None
    joint_palette: np.ndarray
    asset_kind: str = "rigid"
    mesh_vertices: np.ndarray | None = None
    mesh_faces: np.ndarray | None = None
    mesh_vertex_colors: np.ndarray | None = None
    smpl_model_data: SmplModelData | None = None
    skinned_model_data: Any | None = None
    skinning_error: str | None = None


@dataclass
class SkinnedMeshData:
    rest_vertices: np.ndarray
    rest_joints: np.ndarray
    skinning_weights: np.ndarray
    one_hot_skinning_weights: np.ndarray
    ground_translation: Vec3f


@dataclass
class ViewerState:
    asset: AssetData | None = None
    part_handles: list[Any] | None = None
    mesh_handle: Any | None = None
    skinning_weight_handle: Any | None = None
    skeleton_handle: Any | None = None
    joint_marker_handles: list[Any] | None = None
    joint_label_handles: list[Any] | None = None
    joint_frame_handles: list[Any] | None = None
    current_local_rotations: list[Mat3f] | None = None
    current_root_offset: Vec3f | None = None
    current_world_rotations: np.ndarray | None = None
    current_world_positions: np.ndarray | None = None
    manual_local_rotations: list[Mat3f] | None = None
    manual_root_offset: Vec3f | None = None
    selected_joint_index: int | None = None
    suppress_joint_dropdown_callbacks: bool = False
    suppress_joint_slider_callbacks: bool = False
    suppress_timeline_time_callbacks: bool = False
    suppress_timeline_end_callbacks: bool = False
    suppress_motion_preview_time_callbacks: bool = False
    suppress_root_slider_callbacks: bool = False
    suppress_use_lbs_callbacks: bool = False
    transform_control_handle: Any | None = None
    root_transform_handle: Any | None = None
    suppress_transform_callback: bool = False
    suppress_root_transform_callback: bool = False
    keyframes: list[dict[str, Any]] | None = None
    working_sequence_source_kind: str | None = None
    working_sequence_source_path: Path | None = None
    working_sequence_source_name: str | None = None
    last_export_path: Path | None = None
    is_loading_asset: bool = False
    is_exporting_video: bool = False


def joint_color(name: str) -> tuple[int, int, int]:
    if name.startswith("left_"):
        return (220, 110, 60)
    if name.startswith("right_"):
        return (70, 130, 220)
    return (70, 70, 70)


def bone_colors(asset: AssetData) -> np.ndarray:
    colors = []
    for parent, child in asset.bone_edges:
        color = np.asarray(joint_color(asset.joints[child].name), dtype=np.uint8)
        colors.append(np.stack([color, color], axis=0))
    return np.asarray(colors, dtype=np.uint8)


def copy_rotations(rotations: list[Mat3f]) -> list[Mat3f]:
    return [rotation.copy() for rotation in rotations]


def skinning_weight_colors(weights: np.ndarray) -> np.ndarray:
    weights = np.clip(np.asarray(weights, dtype=np.float32), 0.0, 1.0)
    rgba = np.asarray(colormaps["magma"](weights), dtype=np.float32)
    return np.clip(rgba[:, :3] * 255.0, 0.0, 255.0).astype(np.uint8)


def joint_palette(asset: AssetData) -> np.ndarray:
    return asset.joint_palette


def all_skinning_weight_colors(weights: np.ndarray, palette: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=np.float32)
    palette = np.asarray(palette, dtype=np.float32)
    sharpened = np.power(np.clip(weights, 0.0, 1.0), 0.75)
    normalization = np.clip(sharpened.sum(axis=1, keepdims=True), 1e-6, None)
    return np.clip((sharpened / normalization) @ palette, 0.0, 255.0).astype(np.uint8)


def sample_triangle_surface(
    triangle_vertices: np.ndarray,
    sample_count: int,
) -> np.ndarray:
    if sample_count <= 1:
        return np.asarray(triangle_vertices.mean(axis=0, keepdims=True), dtype=np.float32)

    v0, v1, v2 = [np.asarray(vertex, dtype=np.float32) for vertex in triangle_vertices]
    sequence = np.arange(sample_count, dtype=np.float32)
    u = (sequence + 0.5) / float(sample_count)
    v = np.mod(0.5 + sequence * 0.61803398875, 1.0)
    sqrt_u = np.sqrt(u)
    bary0 = 1.0 - sqrt_u
    bary1 = sqrt_u * (1.0 - v)
    bary2 = sqrt_u * v
    return (
        bary0[:, None] * v0[None, :]
        + bary1[:, None] * v1[None, :]
        + bary2[:, None] * v2[None, :]
    ).astype(np.float32)


def sample_mesh_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_spacing: float = 0.03,
) -> np.ndarray:
    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int32)
    target_triangle_area = max(target_spacing * target_spacing * math.sqrt(3.0) / 2.0, 1e-6)
    samples: list[np.ndarray] = []
    for face in faces:
        triangle = vertices[face]
        edge01 = triangle[1] - triangle[0]
        edge02 = triangle[2] - triangle[0]
        area = 0.5 * float(np.linalg.norm(np.cross(edge01, edge02)))
        sample_count = max(1, int(math.ceil(area / target_triangle_area)))
        samples.append(sample_triangle_surface(triangle, sample_count))
    if not samples:
        return np.zeros((0, 3), dtype=np.float32)
    return np.concatenate(samples, axis=0).astype(np.float32)


def rgb_distance(color_a: np.ndarray, color_b: np.ndarray) -> float:
    diff = np.asarray(color_a, dtype=np.float32) - np.asarray(color_b, dtype=np.float32)
    return float(np.linalg.norm(diff))


def candidate_joint_colors(count: int) -> list[np.ndarray]:
    rgba = np.asarray(colormaps["tab20"].colors, dtype=np.float32)
    colors = [
        np.clip(color[:3] * 255.0, 0.0, 255.0).astype(np.uint8)
        for color in rgba
    ]
    if count <= len(colors):
        return [color.copy() for color in colors]
    repeat_count = count - len(colors)
    for index in range(repeat_count):
        base = colors[index % len(colors)].astype(np.float32)
        scale = 0.88 if (index // len(colors)) % 2 == 0 else 1.08
        colors.append(np.clip(base * scale, 0.0, 255.0).astype(np.uint8))
    return colors


def joint_adjacency(asset: AssetData) -> tuple[tuple[int, ...], ...]:
    adjacency: list[set[int]] = [set() for _ in asset.joints]
    for parent_index, child_index in asset.bone_edges:
        adjacency[parent_index].add(child_index)
        adjacency[child_index].add(parent_index)
    return tuple(tuple(sorted(neighbors)) for neighbors in adjacency)


def build_joint_palette(asset: AssetData) -> np.ndarray:
    adjacency = joint_adjacency(asset)
    two_hop_neighbors: list[set[int]] = []
    for joint_index, neighbors in enumerate(adjacency):
        expanded = set()
        for neighbor in neighbors:
            expanded.update(adjacency[neighbor])
        expanded.discard(joint_index)
        expanded.difference_update(neighbors)
        two_hop_neighbors.append(expanded)

    candidate_colors = candidate_joint_colors(len(asset.joints))
    assignment: list[np.ndarray | None] = [None] * len(asset.joints)
    used_candidate_indices: set[int] = set()
    order = sorted(
        range(len(asset.joints)),
        key=lambda joint_index: (
            -len(adjacency[joint_index]),
            asset.joints[joint_index].parent < 0,
            asset.joints[joint_index].name,
        ),
    )

    for joint_index in order:
        available_indices = [
            candidate_index
            for candidate_index in range(len(candidate_colors))
            if candidate_index not in used_candidate_indices
        ]
        if not available_indices:
            available_indices = list(range(len(candidate_colors)))

        best_candidate_index = available_indices[0]
        best_color = candidate_colors[best_candidate_index]
        best_score = (-1.0, -1.0, -1.0)
        direct_neighbor_colors = [
            assignment[neighbor]
            for neighbor in adjacency[joint_index]
            if assignment[neighbor] is not None
        ]
        nearby_colors = [
            assignment[neighbor]
            for neighbor in two_hop_neighbors[joint_index]
            if assignment[neighbor] is not None
        ]
        assigned_colors = [color for color in assignment if color is not None]
        for candidate_index in available_indices:
            candidate_color = candidate_colors[candidate_index]
            direct_margin = (
                min(rgb_distance(candidate_color, neighbor_color) for neighbor_color in direct_neighbor_colors)
                if direct_neighbor_colors
                else 512.0
            )
            nearby_margin = (
                min(rgb_distance(candidate_color, neighbor_color) for neighbor_color in nearby_colors)
                if nearby_colors
                else direct_margin
            )
            global_margin = (
                min(rgb_distance(candidate_color, assigned_color) for assigned_color in assigned_colors)
                if assigned_colors
                else nearby_margin
            )
            score = (direct_margin, nearby_margin, global_margin)
            if score > best_score:
                best_score = score
                best_color = candidate_color
                best_candidate_index = candidate_index
        assignment[joint_index] = best_color
        used_candidate_indices.add(best_candidate_index)

    return np.asarray([color for color in assignment if color is not None], dtype=np.uint8)


def transform_points(points: np.ndarray, rotation: np.ndarray, position: np.ndarray) -> np.ndarray:
    return np.asarray(points, dtype=np.float32) @ np.asarray(rotation, dtype=np.float32).T + np.asarray(
        position,
        dtype=np.float32,
    )


def rigid_skinning_overlay_points_and_colors(
    asset: AssetData,
    world_rotations: np.ndarray,
    world_positions: np.ndarray,
    selected_joint_index: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    palette = joint_palette(asset)
    point_groups: list[np.ndarray] = []
    color_groups: list[np.ndarray] = []
    for part in asset.parts:
        joint_index = part.joint_index
        points = transform_points(
            part.surface_points,
            world_rotations[joint_index],
            world_positions[joint_index],
        )
        point_groups.append(points)
        if selected_joint_index is None:
            color_groups.append(np.tile(palette[joint_index][None, :], (len(points), 1)))
        else:
            weights = np.full(
                len(points),
                1.0 if joint_index == selected_joint_index else 0.0,
                dtype=np.float32,
            )
            color_groups.append(skinning_weight_colors(weights))
    if not point_groups:
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.uint8)
    return (
        np.concatenate(point_groups, axis=0).astype(np.float32),
        np.concatenate(color_groups, axis=0).astype(np.uint8),
    )


def skinned_mesh_overlay_points_and_colors(
    asset: AssetData,
    mesh_vertices: np.ndarray,
    *,
    use_blended_weights: bool,
    selected_joint_index: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    assert asset.skinned_model_data is not None
    weights = get_skinning_weights(
        asset.skinned_model_data,
        use_blended_weights=use_blended_weights,
    )
    if selected_joint_index is None:
        colors = all_skinning_weight_colors(weights, joint_palette(asset))
    else:
        colors = skinning_weight_colors(weights[:, selected_joint_index])
    return np.asarray(mesh_vertices, dtype=np.float32), colors


def euler_xyz_degrees_to_matrix(x_deg: float, y_deg: float, z_deg: float) -> Mat3f:
    return (
        rotation_x(math.radians(x_deg))
        @ rotation_y(math.radians(y_deg))
        @ rotation_z(math.radians(z_deg))
    )


def matrix_to_euler_xyz_degrees(matrix: Mat3f) -> list[float]:
    y_rad = math.asin(max(-1.0, min(1.0, float(matrix[0, 2]))))
    cos_y = math.cos(y_rad)
    if abs(cos_y) > 1e-6:
        x_rad = math.atan2(-float(matrix[1, 2]), float(matrix[2, 2]))
        z_rad = math.atan2(-float(matrix[0, 1]), float(matrix[0, 0]))
    else:
        x_rad = math.atan2(float(matrix[2, 1]), float(matrix[1, 1]))
        z_rad = 0.0
    return [
        round(math.degrees(x_rad), 6),
        round(math.degrees(y_rad), 6),
        round(math.degrees(z_rad), 6),
    ]


def matrix_to_quaternion(matrix: Mat3f) -> np.ndarray:
    m = matrix
    trace = float(m[0, 0] + m[1, 1] + m[2, 2])
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s

    quaternion = np.asarray([w, x, y, z], dtype=np.float32)
    return quaternion / np.linalg.norm(quaternion)


def quaternion_to_matrix(quaternion: np.ndarray) -> Mat3f:
    w, x, y, z = [float(v) for v in quaternion]
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float32,
    )


def quaternion_slerp(q0: np.ndarray, q1: np.ndarray, alpha: float) -> np.ndarray:
    q0 = np.asarray(q0, dtype=np.float32)
    q1 = np.asarray(q1, dtype=np.float32)
    q0 = q0 / np.linalg.norm(q0)
    q1 = q1 / np.linalg.norm(q1)

    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot

    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        blended = (1.0 - alpha) * q0 + alpha * q1
        return blended / np.linalg.norm(blended)

    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * alpha
    sin_theta = math.sin(theta)
    s0 = math.sin(theta_0 - theta) / sin_theta_0
    s1 = sin_theta / sin_theta_0
    return (s0 * q0 + s1 * q1).astype(np.float32)


def normalize_video_size(width: int, height: int) -> tuple[int, int]:
    width = max(2, int(width))
    height = max(2, int(height))
    if width % 2 != 0:
        width -= 1
    if height % 2 != 0:
        height -= 1
    return width, height


def write_mp4_with_ffmpeg(
    frames: list[np.ndarray],
    output_path: Path,
    fps: int,
) -> None:
    if not frames:
        raise ValueError("Cannot export a video with zero frames.")

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError("Could not find an ffmpeg binary on PATH.")

    first_frame = np.asarray(frames[0], dtype=np.uint8)
    height, width = first_frame.shape[:2]
    command = [
        ffmpeg_path,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vcodec",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    try:
        for frame in frames:
            rgb_frame = np.asarray(frame[..., :3], dtype=np.uint8)
            process.stdin.write(rgb_frame.tobytes())
    finally:
        process.stdin.close()
    stderr_bytes = process.stderr.read() if process.stderr is not None else b""
    return_code = process.wait()
    if return_code != 0:
        stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(stderr_text or "ffmpeg failed to encode the video.")


SMPL_24_PARENTS = (
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

PACKAGE_SKINNING_VERSION = 5
WORKING_SEQUENCE_LABEL = "Working Sequence"
DEFAULT_WORKING_SEQUENCE_DURATION = 10.0
PACKAGE_SKINNING_COORDINATE_SPACE = "up2you_smpl_native_y_up"
PACKAGE_SKINNING_REST_POSE = "gf5_smpl24_template_neutral_bind_pose"
PACKAGE_SKINNING_MOTION_POSE_SPACE = "gf5_course_body_24_absolute_local"
MAX_AVATAR_ZIP_BYTES = 768 * 1024 * 1024
MAX_AVATAR_EXTRACTED_BYTES = 1536 * 1024 * 1024


def avatar_import_label_from_filename(file_name: str) -> str:
    stem = Path(file_name).stem
    cleaned = re.sub(r"[_\-\s]+", " ", stem).strip()
    return f"Avatar: {cleaned or 'uploaded character'}"


def unique_avatar_import_dir(import_root: Path, file_name: str) -> Path:
    stem = Path(file_name).stem or "avatar"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-") or "avatar"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{safe_stem}_{timestamp}_{time.time_ns() % 1_000_000:06d}"
    destination = import_root / base_name
    suffix = 2
    while destination.exists():
        destination = import_root / f"{base_name}_{suffix}"
        suffix += 1
    return destination


def validate_avatar_zip_member(info: zipfile.ZipInfo) -> PurePosixPath | None:
    name = info.filename.replace("\\", "/").strip()
    if not name or name.endswith("/"):
        return None
    member_path = PurePosixPath(name)
    if (
        member_path.is_absolute()
        or ".." in member_path.parts
        or not member_path.parts
    ):
        raise ValueError(f"Unsafe zip entry: {info.filename!r}")
    if member_path.parts[0] == "__MACOSX" or member_path.name == ".DS_Store":
        return None
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError(f"Zip entry is a symbolic link: {info.filename!r}")
    return member_path


def safe_extract_avatar_zip(zip_file: zipfile.ZipFile, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    extracted_count = 0
    total_size = 0
    for info in zip_file.infolist():
        member_path = validate_avatar_zip_member(info)
        if member_path is None:
            continue
        total_size += info.file_size
        if total_size > MAX_AVATAR_EXTRACTED_BYTES:
            raise ValueError("Avatar zip is too large after extraction.")
        target = destination.joinpath(*member_path.parts)
        if not target.resolve().is_relative_to(destination_root):
            raise ValueError(f"Unsafe zip entry: {info.filename!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        extracted_count += 1
    if extracted_count == 0:
        raise ValueError("Avatar zip did not contain any files.")


def parse_obj_mesh(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    vertices: list[list[float]] = []
    vertex_colors: list[list[float] | None] = []
    faces: list[list[int]] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if parts[0] == "v" and len(parts) >= 4:
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                if len(parts) >= 7:
                    vertex_colors.append([float(parts[4]), float(parts[5]), float(parts[6])])
                else:
                    vertex_colors.append(None)
            elif parts[0] == "f" and len(parts) >= 4:
                face_indices = []
                for token in parts[1:]:
                    vertex_token = token.split("/", 1)[0]
                    index = int(vertex_token)
                    if index < 0:
                        index = len(vertices) + index
                    else:
                        index -= 1
                    face_indices.append(index)
                for offset in range(1, len(face_indices) - 1):
                    faces.append([face_indices[0], face_indices[offset], face_indices[offset + 1]])

    if not vertices:
        raise ValueError(f"{path} does not contain any OBJ vertices.")
    if not faces:
        raise ValueError(f"{path} does not contain any OBJ faces.")

    color_array: np.ndarray | None = None
    if any(color is not None for color in vertex_colors):
        resolved_colors = [
            color if color is not None else [0.75, 0.75, 0.75]
            for color in vertex_colors
        ]
        color_values = np.asarray(resolved_colors, dtype=np.float32)
        if float(np.nanmax(color_values)) <= 1.0:
            color_values = color_values * 255.0
        color_array = np.clip(color_values, 0.0, 255.0).astype(np.uint8)

    return (
        np.asarray(vertices, dtype=np.float32),
        np.asarray(faces, dtype=np.uint32),
        color_array,
    )


def packaged_skinning_weights_path(animation_mesh_path: Path) -> Path:
    return animation_mesh_path.with_name(f"{animation_mesh_path.stem}_skinning_weights.npz")


def package_metadata_string(data: np.lib.npyio.NpzFile, key: str) -> str:
    value = np.asarray(data[key])
    if value.shape == ():
        return str(value.item())
    return str(value)


def load_packaged_skinning_weights(
    animation_mesh_path: Path,
    *,
    vertex_count: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    path = packaged_skinning_weights_path(animation_mesh_path)
    if not path.exists():
        return None
    with np.load(path, allow_pickle=False) as data:
        version = int(data["version"]) if "version" in data else 0
        package_format = str(data["format"]) if "format" in data else ""
        if package_format != "gf5_smpl24_skinning_weights" or version < PACKAGE_SKINNING_VERSION:
            raise ValueError(
                f"{path.name} is not a current GF5 SMPL-24 skinning package. "
                "Regenerate the avatar package from the human character demo."
            )
        expected_metadata = {
            "rest_joint_coordinate_space": PACKAGE_SKINNING_COORDINATE_SPACE,
            "rest_pose": PACKAGE_SKINNING_REST_POSE,
            "motion_pose_space": PACKAGE_SKINNING_MOTION_POSE_SPACE,
        }
        for key, expected in expected_metadata.items():
            if key not in data or package_metadata_string(data, key) != expected:
                raise ValueError(
                    f"{path.name} has unexpected {key}; expected {expected!r}. "
                    "Regenerate the avatar package from the human character demo."
                )
        if "skinning_weights" not in data:
            raise ValueError(f"{path.name} does not contain skinning_weights.")
        if "rest_joints" not in data:
            raise ValueError(f"{path.name} does not contain rest_joints.")
        weights = np.asarray(data["skinning_weights"], dtype=np.float32)
        rest_joints = np.asarray(data["rest_joints"], dtype=np.float32)
        if "joint_names" in data:
            joint_names = tuple(str(item) for item in data["joint_names"])
        else:
            joint_names = SMPL_24_PROFILE.joint_names
    if weights.shape != (vertex_count, len(SMPL_24_PROFILE.joint_names)):
        raise ValueError(
            f"{path.name} has skinning weights with shape {weights.shape}, "
            f"expected {(vertex_count, len(SMPL_24_PROFILE.joint_names))}."
        )
    if joint_names != SMPL_24_PROFILE.joint_names:
        raise ValueError(f"{path.name} uses an unexpected joint order.")
    if rest_joints.shape != (len(SMPL_24_PROFILE.joint_names), 3):
        raise ValueError(f"{path.name} has rest_joints with unexpected shape {rest_joints.shape}.")
    row_sums = np.clip(weights.sum(axis=1, keepdims=True), 1e-8, None)
    return (weights / row_sums).astype(np.float32), rest_joints


def infer_character_label(character_root: Path) -> str:
    if character_root.name == "outputs":
        if character_root.parent.name.lower() == "up2you":
            return "UP2You Character"
        return f"UP2You {character_root.parent.name}"
    if character_root.name == "output" and character_root.parent.name:
        return f"UP2You {character_root.parent.name}"
    return f"UP2You {character_root.name}"


def valid_up2you_character_root(path: Path) -> bool:
    output_dir = path / "outputs"
    if not output_dir.is_dir():
        return False
    animation_mesh = output_dir / "animation_lowres.obj"
    return (
        animation_mesh.exists()
        and packaged_skinning_weights_path(animation_mesh).exists()
        and (output_dir / "smplx_mesh.obj").exists()
    )


def iter_up2you_character_roots(search_dir: Path) -> list[Path]:
    if not search_dir.exists():
        return []

    candidates: list[Path] = [search_dir]
    if search_dir.name == "jobs":
        candidates.extend(path / "output" for path in sorted(search_dir.iterdir()) if path.is_dir())
    else:
        for child in sorted(search_dir.iterdir()) if search_dir.is_dir() else []:
            if not child.is_dir():
                continue
            candidates.append(child)
            candidates.append(child / "output")

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not valid_up2you_character_root(resolved):
            continue
        seen.add(resolved)
        unique_roots.append(resolved)
    return unique_roots


def find_up2you_character_root(search_dir: Path) -> Path | None:
    candidates: list[Path] = [search_dir]
    if search_dir.is_dir():
        candidates.extend(path.parent for path in search_dir.rglob("outputs") if path.is_dir())
    unique_candidates = sorted(
        {candidate.resolve() for candidate in candidates},
        key=lambda path: (len(path.parts), str(path)),
    )
    for candidate in unique_candidates:
        if valid_up2you_character_root(candidate):
            return candidate
    return None


def import_avatar_zip_bytes(
    file_name: str,
    content: bytes,
    import_root: Path,
) -> Path:
    if not content:
        raise ValueError("Uploaded avatar zip is empty.")
    if len(content) > MAX_AVATAR_ZIP_BYTES:
        raise ValueError("Uploaded avatar zip is too large.")
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            destination = unique_avatar_import_dir(import_root, file_name)
            try:
                safe_extract_avatar_zip(zf, destination)
                character_root = find_up2you_character_root(destination)
                if character_root is None:
                    raise ValueError(
                        "Avatar zip must contain an outputs/ folder with "
                        "animation_lowres.obj, animation_lowres_skinning_weights.npz, and smplx_mesh.obj."
                    )
                return character_root
            except Exception:
                if destination.exists():
                    shutil.rmtree(destination)
                raise
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid zip archive.") from exc


def discover_up2you_characters(character_dirs: list[Path]) -> dict[str, Path]:
    characters: dict[str, Path] = {}
    for character_dir in character_dirs:
        for character_root in iter_up2you_character_roots(character_dir):
            label = infer_character_label(character_root)
            suffix = 2
            unique_label = label
            while unique_label in characters:
                unique_label = f"{label} ({suffix})"
                suffix += 1
            characters[unique_label] = character_root
    return characters


def discover_assets(asset_dir: Path) -> dict[str, Path]:
    assets: dict[str, Path] = {}
    for path in sorted(asset_dir.glob("*.asset.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("asset_format") != "gf5_rigid_character":
            continue
        label = str(raw.get("name", path.stem))
        assets[label] = path
    return assets


def infer_smpl_label(model_path: Path) -> str:
    stem = model_path.stem.lower()
    if "neutral" in stem:
        return "SMPL Neutral"
    if "_f_" in stem or "female" in stem:
        return "SMPL Female"
    if "_m_" in stem or "male" in stem:
        return "SMPL Male"
    return f"SMPL {model_path.stem}"


def discover_smpl_models(smpl_model_path: Path | None) -> dict[str, Path]:
    if smpl_model_path is None:
        return {}

    candidate_paths: list[Path] = []
    if smpl_model_path.is_dir():
        candidate_paths.extend(sorted(smpl_model_path.glob("*.pkl")))
    elif smpl_model_path.exists():
        candidate_paths.extend(sorted(smpl_model_path.parent.glob("*.pkl")))
        if smpl_model_path not in candidate_paths:
            candidate_paths.append(smpl_model_path)

    smpl_paths: dict[str, Path] = {}
    for path in candidate_paths:
        if "basicmodel" not in path.stem.lower() and "smpl" not in path.stem.lower():
            continue
        smpl_paths[infer_smpl_label(path)] = path

    ordered: dict[str, Path] = {}
    for label in ("SMPL Neutral", "SMPL Female", "SMPL Male"):
        if label in smpl_paths:
            ordered[label] = smpl_paths.pop(label)
    for label in sorted(smpl_paths):
        ordered[label] = smpl_paths[label]
    return ordered


def discover_asset_sources(
    asset_dir: Path,
    smpl_model_path: Path | None,
    character_dirs: list[Path],
) -> dict[str, tuple[str, Path]]:
    sources = {label: ("rigid", path) for label, path in discover_assets(asset_dir).items()}
    for label, path in discover_smpl_models(smpl_model_path).items():
        sources[label] = ("smpl", path)
    for label, path in discover_up2you_characters(character_dirs).items():
        sources[label] = ("up2you", path)
    return sources


def discover_motion_library(motion_dir: Path, *, label_prefix: str = "Saved") -> dict[str, Path]:
    motions: dict[str, Path] = {}
    if not motion_dir.exists():
        return motions
    for path in sorted(motion_dir.rglob("*.motion.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("format") != "gf5_keyframed_motion":
            continue
        if raw.get("profile_name") != COURSE_BODY_24_PROFILE.name:
            continue
        name = str(raw.get("name", path.stem))
        label = f"{label_prefix}: {name}"
        suffix = 2
        while label in motions:
            label = f"{label_prefix}: {name} ({suffix})"
            suffix += 1
        motions[label] = path
    return motions


def discover_pose_library(pose_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    named_poses: dict[str, Path] = {}
    recent_poses: dict[str, Path] = {}
    if not pose_dir.exists():
        return named_poses, recent_poses

    def register_pose(path: Path, destination: dict[str, Path]) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if raw.get("format") != "gf5_saved_pose":
            return
        if raw.get("profile_name") != COURSE_BODY_24_PROFILE.name:
            return
        name = str(raw.get("name", path.stem))
        label = name
        suffix = 2
        while label in destination:
            label = f"{name} ({suffix})"
            suffix += 1
        destination[label] = path

    for path in sorted(pose_dir.glob("*.pose.json")):
        register_pose(path, named_poses)

    recent_dir = pose_dir / "recent"
    if recent_dir.exists():
        for path in sorted(
            recent_dir.glob("*.pose.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            register_pose(path, recent_poses)

    return named_poses, recent_poses


def format_status_html(label: str, message: str) -> str:
    safe_label = html.escape(label)
    safe_message = html.escape(message).replace("\n", "<br>")
    return (
        '<div style="display:block; width:100%; box-sizing:border-box; '
        'font-size:12px; line-height:1.3; text-align:left; '
        'color:var(--mantine-color-text); white-space:normal; '
        'overflow-wrap:anywhere; word-break:break-word; margin:-2px 0 3px 0; '
        'padding:0 var(--mantine-spacing-xs);">'
        f"<strong>{safe_label}:</strong> {safe_message}</div>"
    )


def load_asset(path: Path) -> AssetData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("asset_format") != "gf5_rigid_character":
        raise ValueError(f"{path.name} is not a rigid Part-1 asset.")

    joints = [
        JointSpec(
            name=str(joint["name"]),
            parent=int(joint["parent"]),
            translation=np.asarray(joint["translation"], dtype=np.float32),
            rest_position=np.asarray(joint["rest_position"], dtype=np.float32),
        )
        for joint in raw["skeleton"]["joints"]
    ]
    joint_lookup = {joint.name: idx for idx, joint in enumerate(joints)}
    parts = [
        PartSpec(
            name=str(part["name"]),
            joint_index=joint_lookup[str(part["joint"])],
            vertices=(vertices := np.asarray(part["vertices"], dtype=np.float32)),
            faces=(faces := np.asarray(part["faces"], dtype=np.uint32)),
            surface_points=sample_mesh_surface(vertices, faces),
            color=tuple(int(v) for v in part["color"]),
            flat_shading=bool(part.get("flat_shading", True)),
            side=str(part.get("side", "double")),
        )
        for part in raw["rigid_parts"]
    ]
    bone_edges = [tuple(edge) for edge in raw["skeleton"]["bone_edges"]]
    joint_names = tuple(joint.name for joint in joints)
    parents = tuple(joint.parent for joint in joints)
    profile = detect_profile(joint_names)
    asset = AssetData(
        path=path,
        label=str(raw["name"]),
        joints=joints,
        parts=parts,
        bone_edges=bone_edges,
        joint_names=joint_names,
        joint_lookup=joint_lookup,
        topological_order=compute_topological_order(parents),
        profile_name=None if profile is None else profile.name,
        joint_palette=np.zeros((len(joints), 3), dtype=np.uint8),
    )
    asset.joint_palette = build_joint_palette(asset)
    return asset


def load_smpl_asset(model_path: Path) -> AssetData:
    smpl_model_data = load_smpl_model_data(model_path)
    skinning_error = smpl_model_data.skinning_setup_error
    rest_positions = smpl_model_data.rest_joints + smpl_model_data.ground_translation
    joints: list[JointSpec] = []
    bone_edges: list[tuple[int, int]] = []
    for joint_index, joint_name in enumerate(smpl_model_data.joint_names):
        parent_index = smpl_model_data.parents[joint_index]
        rest_position = np.asarray(rest_positions[joint_index], dtype=np.float32)
        if parent_index < 0:
            translation = rest_position.copy()
        else:
            translation = rest_position - rest_positions[parent_index]
            bone_edges.append((parent_index, joint_index))
        joints.append(
            JointSpec(
                name=joint_name,
                parent=parent_index,
                translation=np.asarray(translation, dtype=np.float32),
                rest_position=rest_position,
            )
        )

    joint_names = tuple(joint.name for joint in joints)
    joint_lookup = {joint.name: idx for idx, joint in enumerate(joints)}
    mesh_vertices = smpl_model_data.rest_vertices + smpl_model_data.ground_translation
    asset = AssetData(
        path=model_path,
        label=infer_smpl_label(model_path),
        joints=joints,
        parts=[],
        bone_edges=bone_edges,
        joint_names=joint_names,
        joint_lookup=joint_lookup,
        topological_order=compute_topological_order(tuple(joint.parent for joint in joints)),
        profile_name=SMPL_24_PROFILE.name,
        joint_palette=np.zeros((len(joints), 3), dtype=np.uint8),
        asset_kind="smpl",
        mesh_vertices=np.asarray(mesh_vertices, dtype=np.float32),
        mesh_faces=smpl_model_data.faces,
        smpl_model_data=smpl_model_data,
        skinned_model_data=None if skinning_error is not None else smpl_model_data,
        skinning_error=skinning_error,
    )
    asset.joint_palette = build_joint_palette(asset)
    return asset


def load_up2you_character_asset(character_root: Path, _smplx_model_path: Path) -> AssetData:
    output_dir = character_root / "outputs"
    animation_mesh_path = output_dir / "animation_lowres.obj"
    smplx_mesh_path = output_dir / "smplx_mesh.obj"
    if not animation_mesh_path.exists():
        raise FileNotFoundError(f"No animation_lowres.obj found under {output_dir}")
    if not smplx_mesh_path.exists():
        raise FileNotFoundError(f"No fitted SMPL-X mesh found under {output_dir}")

    animation_vertices_raw, animation_faces, vertex_colors = parse_obj_mesh(animation_mesh_path)
    packaged_skinning = load_packaged_skinning_weights(
        animation_mesh_path,
        vertex_count=animation_vertices_raw.shape[0],
    )
    if packaged_skinning is None:
        raise ValueError(
            "Avatar package must include outputs/animation_lowres_skinning_weights.npz "
            "with SMPL-24 skinning_weights and rest_joints."
        )
    skinning_weights, rest_joints_raw = packaged_skinning
    rest_joints = rotate_points_to_viewer(rest_joints_raw)

    dominant_joint = np.argmax(skinning_weights, axis=1)
    one_hot_weights = np.zeros_like(skinning_weights, dtype=np.float32)
    one_hot_weights[np.arange(skinning_weights.shape[0]), dominant_joint] = 1.0

    rest_vertices = rotate_points_to_viewer(animation_vertices_raw)
    ground_translation = np.asarray([0.0, 0.0, -float(rest_vertices[:, 2].min())], dtype=np.float32)
    rest_positions = rest_joints + ground_translation
    joints: list[JointSpec] = []
    bone_edges: list[tuple[int, int]] = []
    for joint_index, joint_name in enumerate(SMPL_24_PROFILE.joint_names):
        parent_index = SMPL_24_PARENTS[joint_index]
        rest_position = np.asarray(rest_positions[joint_index], dtype=np.float32)
        if parent_index < 0:
            translation = rest_position.copy()
        else:
            translation = rest_position - rest_positions[parent_index]
            bone_edges.append((parent_index, joint_index))
        joints.append(
            JointSpec(
                name=joint_name,
                parent=parent_index,
                translation=np.asarray(translation, dtype=np.float32),
                rest_position=rest_position,
            )
        )

    skinned_model_data = SkinnedMeshData(
        rest_vertices=rest_vertices,
        rest_joints=rest_joints,
        skinning_weights=np.asarray(skinning_weights, dtype=np.float32),
        one_hot_skinning_weights=one_hot_weights,
        ground_translation=ground_translation,
    )
    asset = AssetData(
        path=character_root,
        label=infer_character_label(character_root),
        joints=joints,
        parts=[],
        bone_edges=bone_edges,
        joint_names=SMPL_24_PROFILE.joint_names,
        joint_lookup={joint.name: idx for idx, joint in enumerate(joints)},
        topological_order=compute_topological_order(tuple(joint.parent for joint in joints)),
        profile_name=SMPL_24_PROFILE.name,
        joint_palette=np.zeros((len(joints), 3), dtype=np.uint8),
        asset_kind="up2you",
        mesh_vertices=np.asarray(rest_vertices + ground_translation, dtype=np.float32),
        mesh_faces=animation_faces,
        mesh_vertex_colors=vertex_colors,
        skinned_model_data=skinned_model_data,
    )
    asset.joint_palette = build_joint_palette(asset)
    return asset


def pose_sample_to_asset_local_rotations(asset: AssetData, pose_sample: PoseSample) -> list[Mat3f]:
    if len(pose_sample.local_rotations) != len(get_profile(pose_sample.profile_name).joint_names):
        raise ValueError(
            f"Pose sample for profile {pose_sample.profile_name} has "
            f"{len(pose_sample.local_rotations)} rotations, which does not match the profile definition."
        )
    return retarget_local_rotations(
        pose_sample.local_rotations,
        pose_sample.profile_name,
        asset.joint_names,
        asset.profile_name,
    )


def forward_kinematics(
    joints: list[JointSpec],
    local_rotations: list[Mat3f],
    root_offset: Vec3f,
    topological_order: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    return get_part1_fk_module().forward_kinematics(
        joints,
        local_rotations,
        root_offset,
        topological_order=topological_order,
    )


def clear_scene(state: ViewerState) -> None:
    if state.part_handles is not None:
        for handle in state.part_handles:
            handle.remove()
    if state.mesh_handle is not None:
        state.mesh_handle.remove()
    if state.skinning_weight_handle is not None:
        state.skinning_weight_handle.remove()
    if state.skeleton_handle is not None:
        state.skeleton_handle.remove()
    if state.joint_marker_handles is not None:
        for handle in state.joint_marker_handles:
            handle.remove()
    if state.joint_label_handles is not None:
        for handle in state.joint_label_handles:
            handle.remove()
    if state.joint_frame_handles is not None:
        for handle in state.joint_frame_handles:
            handle.remove()
    if state.transform_control_handle is not None:
        state.transform_control_handle.remove()
    if state.root_transform_handle is not None:
        state.root_transform_handle.remove()
    state.asset = None
    state.part_handles = None
    state.mesh_handle = None
    state.skinning_weight_handle = None
    state.skeleton_handle = None
    state.joint_marker_handles = None
    state.joint_label_handles = None
    state.joint_frame_handles = None
    state.current_local_rotations = None
    state.current_root_offset = None
    state.current_world_rotations = None
    state.current_world_positions = None
    state.manual_local_rotations = None
    state.manual_root_offset = None
    state.selected_joint_index = None
    state.transform_control_handle = None
    state.root_transform_handle = None
    state.last_export_path = None


def add_character_mesh(
    server: viser.ViserServer,
    asset: AssetData,
    *,
    name: str = "/character/mesh",
) -> Any:
    assert asset.mesh_vertices is not None
    assert asset.mesh_faces is not None
    if asset.mesh_vertex_colors is not None:
        try:
            return server.scene.add_mesh_simple(
                name,
                vertices=asset.mesh_vertices,
                faces=asset.mesh_faces,
                vertex_colors=asset.mesh_vertex_colors,
                flat_shading=False,
                side="double",
            )
        except TypeError:
            pass
    return server.scene.add_mesh_simple(
        name,
        vertices=asset.mesh_vertices,
        faces=asset.mesh_faces,
        color=(214, 189, 161),
        flat_shading=False,
        side="double",
    )


def render_asset(server: viser.ViserServer, state: ViewerState, asset: AssetData) -> None:
    clear_scene(state)
    handles = []
    mesh_handle = None
    if asset.asset_kind == "rigid":
        rest_weight_points, _ = rigid_skinning_overlay_points_and_colors(
            asset,
            np.tile(np.eye(3, dtype=np.float32)[None, :, :], (len(asset.joints), 1, 1)),
            np.asarray([joint.rest_position for joint in asset.joints], dtype=np.float32),
            selected_joint_index=None,
        )
    else:
        rest_weight_points = (
            np.asarray(asset.mesh_vertices, dtype=np.float32)
            if asset.mesh_vertices is not None
            else np.zeros((0, 3), dtype=np.float32)
        )
    skinning_weight_handle = server.scene.add_point_cloud(
        "/character/skinning_weights",
        points=rest_weight_points,
        colors=np.tile(np.asarray([[80, 80, 80]], dtype=np.uint8), (len(rest_weight_points), 1)),
        point_size=0.012,
        point_shape="circle",
        visible=False,
    )
    if asset.asset_kind == "rigid":
        for part in asset.parts:
            handles.append(
                server.scene.add_mesh_simple(
                    f"/character/{part.name}",
                    vertices=part.vertices,
                    faces=part.faces,
                    color=part.color,
                    flat_shading=part.flat_shading,
                    side=part.side,
                )
            )
    elif asset.mesh_vertices is not None and asset.mesh_faces is not None:
        mesh_handle = add_character_mesh(server, asset)

    skeleton_handle = server.scene.add_line_segments(
        "/character/skeleton",
        points=np.zeros((len(asset.bone_edges), 2, 3), dtype=np.float32),
        colors=bone_colors(asset),
        line_width=4.0,
    )
    joint_marker_handles = []
    joint_label_handles = []
    joint_frame_handles = []
    for joint in asset.joints:
        joint_marker_handles.append(
            server.scene.add_icosphere(
                f"/character/markers/{joint.name}",
                radius=0.018,
                color=joint_color(joint.name),
                position=joint.rest_position,
                opacity=0.95,
                visible=False,
            )
        )
        joint_label_handles.append(
            server.scene.add_label(
                f"/character/labels/{joint.name}",
                text=joint.name,
                position=joint.rest_position + np.asarray([0.0, 0.0, 0.04], dtype=np.float32),
                font_size_mode="screen",
                font_screen_scale=1.,
                depth_test=False,
                anchor="bottom-center",
                visible=False,
            )
        )
        joint_frame_handles.append(
            server.scene.add_frame(
                f"/character/frames/{joint.name}",
                position=joint.rest_position,
                axes_length=0.08,
                axes_radius=0.004,
                visible=False,
            )
        )
    transform_control_handle = server.scene.add_transform_controls(
        "/character/joint_drag_control",
        scale=0.18,
        disable_axes=True,
        disable_sliders=True,
        visible=False,
    )
    root_transform_handle = server.scene.add_transform_controls(
        "/character/root_translation_control",
        scale=0.22,
        disable_rotations=True,
        line_width=3.0,
        opacity=0.95,
        visible=False,
    )
    state.asset = asset
    state.part_handles = handles
    state.mesh_handle = mesh_handle
    state.skinning_weight_handle = skinning_weight_handle
    state.skeleton_handle = skeleton_handle
    state.joint_marker_handles = joint_marker_handles
    state.joint_label_handles = joint_label_handles
    state.joint_frame_handles = joint_frame_handles
    state.transform_control_handle = transform_control_handle
    state.root_transform_handle = root_transform_handle


def update_visualization_visibility(
    state: ViewerState,
    *,
    show_skeleton: bool,
    show_mesh: bool,
    show_skinning_weights: bool,
    show_joint_handles: bool,
    show_joint_labels: bool,
    show_joint_axes: bool,
) -> None:
    if state.part_handles is not None:
        for handle in state.part_handles:
            handle.visible = show_mesh
            if show_mesh and show_skinning_weights:
                handle.opacity = 0.18
            elif show_mesh and show_joint_handles:
                handle.opacity = 0.35
            else:
                handle.opacity = 1.0
    if state.mesh_handle is not None:
        state.mesh_handle.visible = show_mesh
        if show_mesh and show_skinning_weights:
            state.mesh_handle.opacity = 0.18
        elif show_mesh and show_joint_handles:
            state.mesh_handle.opacity = 0.35
        else:
            state.mesh_handle.opacity = 1.0
    if state.skinning_weight_handle is not None:
        state.skinning_weight_handle.visible = show_skinning_weights
    if state.skeleton_handle is not None:
        state.skeleton_handle.visible = show_skeleton
    if state.joint_marker_handles is not None:
        asset = state.asset
        for joint_index, handle in enumerate(state.joint_marker_handles):
            handle.visible = show_joint_handles
            is_selected = state.selected_joint_index == joint_index
            if asset is None or joint_index >= len(asset.joints):
                handle.visible = False
                continue
            handle.color = (255, 215, 0) if is_selected else joint_color(asset.joints[joint_index].name)
            handle.scale = 1.4 if is_selected else 1.0
    if state.transform_control_handle is not None:
        state.transform_control_handle.visible = show_joint_handles and state.selected_joint_index is not None
    if state.root_transform_handle is not None:
        state.root_transform_handle.visible = show_joint_handles and state.asset is not None
    if state.joint_label_handles is not None:
        for handle in state.joint_label_handles:
            handle.visible = show_skeleton and show_joint_labels
    if state.joint_frame_handles is not None:
        for handle in state.joint_frame_handles:
            handle.visible = show_skeleton and show_joint_axes


def apply_pose(
    state: ViewerState,
    world_rotations: np.ndarray,
    world_positions: np.ndarray,
    mesh_vertices: np.ndarray | None,
    show_skeleton: bool,
    show_mesh: bool,
    show_skinning_weights: bool,
    show_joint_handles: bool,
    show_joint_labels: bool,
    show_joint_axes: bool,
) -> None:
    if (
        state.asset is None
        or state.skeleton_handle is None
        or state.joint_marker_handles is None
        or state.joint_label_handles is None
        or state.joint_frame_handles is None
    ):
        return

    if state.asset.asset_kind == "rigid":
        if state.part_handles is None:
            return
        for part, handle in zip(state.asset.parts, state.part_handles):
            joint_index = part.joint_index
            handle.wxyz = matrix_to_quaternion(world_rotations[joint_index])
            handle.position = world_positions[joint_index]
    elif state.mesh_handle is not None and mesh_vertices is not None:
        state.mesh_handle.vertices = mesh_vertices

    skeleton_points = np.asarray(
        [
            [world_positions[child], world_positions[parent]]
            for parent, child in state.asset.bone_edges
        ],
        dtype=np.float32,
    )
    state.skeleton_handle.points = skeleton_points
    for marker_handle, joint, label_handle, frame_handle, world_rotation, world_position in zip(
        state.joint_marker_handles,
        state.asset.joints,
        state.joint_label_handles,
        state.joint_frame_handles,
        world_rotations,
        world_positions,
    ):
        marker_handle.position = world_position
        label_handle.position = world_position + np.asarray([0.0, 0.0, 0.04], dtype=np.float32)
        frame_handle.position = world_position
        frame_handle.wxyz = matrix_to_quaternion(world_rotation)

    if state.transform_control_handle is not None and state.selected_joint_index is not None:
        state.suppress_transform_callback = True
        state.transform_control_handle.position = world_positions[state.selected_joint_index]
        state.transform_control_handle.wxyz = matrix_to_quaternion(
            world_rotations[state.selected_joint_index]
        )
        state.suppress_transform_callback = False
    if state.root_transform_handle is not None:
        state.suppress_root_transform_callback = True
        state.root_transform_handle.position = world_positions[0]
        state.root_transform_handle.wxyz = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        state.suppress_root_transform_callback = False

    update_visualization_visibility(
        state,
        show_skeleton=show_skeleton,
        show_mesh=show_mesh,
        show_skinning_weights=show_skinning_weights,
        show_joint_handles=show_joint_handles,
        show_joint_labels=show_joint_labels,
        show_joint_axes=show_joint_axes,
    )


def main() -> None:
    viewer_dir = Path(__file__).resolve().parent
    project_root = viewer_dir.parent

    parser = argparse.ArgumentParser(description="3D character animation viewer for FK and skinning demos.")
    parser.add_argument(
        "--asset-dir",
        default=str(project_root / "assets" / "blocky"),
        help="Directory containing *.asset.json files.",
    )
    parser.add_argument(
        "--smpl-model",
        default=str(project_root / "assets/smpl/models"),
        help="Optional path to a SMPL model file or a directory of *.pkl model files.",
    )
    parser.add_argument(
        "--character-dir",
        action="append",
        default=None,
        help=(
            "Directory containing UP2You character exports. May be passed more "
            "than once. By default, UP2You characters are loaded only when you "
            "upload an avatar zip in the viewer."
        ),
    )
    parser.add_argument(
        "--smplx-model",
        default="",
        help=(
            "Legacy option kept for older launch scripts. Current avatar packages "
            "must include precomputed GF5 SMPL-24 skinning weights."
        ),
    )
    parser.add_argument(
        "--fk-source",
        choices=VALID_IMPLEMENTATION_SOURCES,
        default="student",
        help="Load FK from the student implementation file.",
    )
    parser.add_argument(
        "--skinning-source",
        choices=VALID_IMPLEMENTATION_SOURCES,
        default="student",
        help="Load SMPL skinning from the student implementation file.",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Do not automatically open the local viewer page in a browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the local viser server.",
    )
    args = parser.parse_args()
    set_active_implementation_sources(
        fk_source=args.fk_source,
        skinning_source=args.skinning_source,
    )

    asset_dir = Path(args.asset_dir).resolve()
    smpl_model_path = Path(args.smpl_model).resolve()
    smplx_model_path = Path(args.smplx_model).resolve()
    if args.character_dir:
        character_dirs = [Path(path).resolve() for path in args.character_dir]
    else:
        character_dirs = []
    avatar_import_root = project_root / ".viewer_imports" / "avatars"
    asset_sources = discover_asset_sources(asset_dir, smpl_model_path, character_dirs)
    pose_library_dir = project_root / "libraries" / "poses"
    motion_library_dir = project_root / "libraries" / "motions"
    video_export_dir = project_root / "exports" / "videos"
    motion_payload_cache: dict[Path, tuple[float, dict[str, Any]]] = {}
    if not asset_sources:
        raise FileNotFoundError(f"No assets found in {asset_dir}")

    named_pose_sources, recent_pose_sources = discover_pose_library(pose_library_dir)
    preset_motion_dir = project_root / "assets" / "motions"
    motion_sources: dict[str, tuple[str, str | Path]] = {
        WORKING_SEQUENCE_LABEL: ("working_sequence", WORKING_SEQUENCE_LABEL),
    }
    for clip_name in CLIP_NAMES:
        motion_sources[clip_name] = ("built_in", clip_name)
    for label, path in discover_motion_library(preset_motion_dir, label_prefix="Preset").items():
        motion_sources[label] = ("preset", path)
    for label, path in discover_motion_library(motion_library_dir).items():
        motion_sources[label] = ("saved", path)

    server = viser.ViserServer(port=args.port)
    server.scene.set_up_direction("+z")
    server.initial_camera.position = (1.25, 2.75, 1.45)
    server.initial_camera.look_at = (0.0, 0.0, 0.88)
    server.initial_camera.up = (0.0, 0.0, 1.0)
    server.initial_camera.fov = math.radians(45.0)
    if not args.no_open_browser:
        webbrowser.open(f"http://localhost:{server.get_port()}", new=2)
    server.scene.add_grid("/grid", width=4.0, height=4.0, plane="xy", position=(0.0, 0.0, 0.0))

    state = ViewerState()
    state.keyframes = []

    with server.gui.add_folder("Animation Viewer"):
        asset_dropdown = server.gui.add_dropdown(
            "Asset",
            tuple(asset_sources.keys()),
            initial_value=next(iter(asset_sources)),
        )
        avatar_zip_upload = server.gui.add_upload_button(
            "Upload Avatar Zip",
            icon=getattr(getattr(viser, "Icon", None), "UPLOAD", None),
            mime_type=".zip,application/zip,application/x-zip-compressed",
        )
        avatar_import_status_text = server.gui.add_html(
            format_status_html("Avatar Import", "No uploaded avatar yet")
        )
        clip_dropdown = server.gui.add_dropdown(
            "Motion",
            tuple(motion_sources.keys()),
            initial_value=CLIP_NAMES[0] if CLIP_NAMES else WORKING_SEQUENCE_LABEL,
        )
        motion_preview_time_slider = server.gui.add_slider(
            "Motion Time",
            min=0.0,
            max=4.0,
            step=0.1,
            initial_value=0.0,
        )
        animate_checkbox = server.gui.add_checkbox("Animate", initial_value=True)
        show_skeleton_checkbox = server.gui.add_checkbox("Show Skeleton", initial_value=True)
        show_mesh_checkbox = server.gui.add_checkbox("Show Mesh", initial_value=True)
        show_skinning_weights_checkbox = server.gui.add_checkbox(
            "Show Skinning Weights",
            initial_value=False,
            disabled=True,
        )
        show_joint_handles_checkbox = server.gui.add_checkbox("Show Joint Handles", initial_value=False)
        show_joint_labels_checkbox = server.gui.add_checkbox("Label Joints", initial_value=False)
        show_joint_axes_checkbox = server.gui.add_checkbox("Show Joint Axes", initial_value=False)
        use_lbs_checkbox = server.gui.add_checkbox("Use LBS", initial_value=False, disabled=True)
        skinning_status_text = server.gui.add_html(
            format_status_html("Skinning", "Load an asset to inspect skinning.")
        )
        reset_button = server.gui.add_button("Reset Pose")

    with server.gui.add_folder("Joint Editor"):
        selected_joint_dropdown = server.gui.add_dropdown(
            "Selected Joint",
            ("None",),
            initial_value="None",
            disabled=True,
        )
        joint_x_slider = server.gui.add_slider(
            "Rotate X",
            min=-180.0,
            max=180.0,
            step=1.0,
            initial_value=0.0,
            disabled=True,
        )
        joint_y_slider = server.gui.add_slider(
            "Rotate Y",
            min=-180.0,
            max=180.0,
            step=1.0,
            initial_value=0.0,
            disabled=True,
        )
        joint_z_slider = server.gui.add_slider(
            "Rotate Z",
            min=-180.0,
            max=180.0,
            step=1.0,
            initial_value=0.0,
            disabled=True,
        )
        clear_selection_button = server.gui.add_button("Clear Joint Selection")
        root_x_slider = server.gui.add_slider(
            "Root X",
            min=-2.0,
            max=2.0,
            step=0.01,
            initial_value=0.0,
            disabled=True,
        )
        root_y_slider = server.gui.add_slider(
            "Root Y",
            min=-2.0,
            max=2.0,
            step=0.01,
            initial_value=0.0,
            disabled=True,
        )
        root_z_slider = server.gui.add_slider(
            "Root Z",
            min=-2.0,
            max=2.0,
            step=0.01,
            initial_value=0.0,
            disabled=True,
        )
        reset_root_button = server.gui.add_button("Reset Root Translation")

    with server.gui.add_folder("Working Sequence"):
        timeline_time_slider = server.gui.add_slider(
            "Time",
            min=0.0,
            max=10.0,
            step=0.1,
            initial_value=0.0,
        )
        timeline_length_slider = server.gui.add_slider(
            "Duration",
            min=1.0,
            max=60.0,
            step=0.5,
            initial_value=DEFAULT_WORKING_SEQUENCE_DURATION,
        )
        capture_pose_button = server.gui.add_button("Add Pose To Sequence")
        load_motion_sequence_button = server.gui.add_button("Load Motion Into Sequence")
        remove_keyframe_button = server.gui.add_button("Remove Keyframe", disabled=True)
        clear_keyframes_button = server.gui.add_button("Clear Sequence")
        captured_count_text = server.gui.add_html(
            format_status_html("Sequence", "0 keyframes")
        )
        timeline_status_text = server.gui.add_html(
            format_status_html("Working Sequence", "No sequence edits yet")
        )

    with server.gui.add_folder("Pose Library"):
        pose_name_text = server.gui.add_text(
            "Pose Name",
            initial_value="custom_pose",
        )
        save_pose_button = server.gui.add_button("Save Current Pose")
        named_pose_dropdown = server.gui.add_dropdown(
            "Named Poses",
            ("None",),
            initial_value="None",
        )
        recent_pose_dropdown = server.gui.add_dropdown(
            "Recent Poses",
            ("None",),
            initial_value="None",
        )
        load_pose_button = server.gui.add_button("Load Pose")
        clear_pose_library_button = server.gui.add_button("Clear Pose Library")
        clear_recent_poses_button = server.gui.add_button("Clear Recent Poses")
        pose_status_text = server.gui.add_html(
            format_status_html("Pose Library", "No saved pose yet")
        )

    with server.gui.add_folder("Motion Library"):
        motion_name_text = server.gui.add_text(
            "Sequence Name",
            initial_value="custom_sequence",
        )
        save_current_sequence_button = server.gui.add_button("Save Current Sequence", disabled=True)
        save_new_sequence_button = server.gui.add_button("Save Sequence As New", disabled=True)
        clear_motion_library_button = server.gui.add_button("Clear Motion Library")
        motion_library_status_text = server.gui.add_html(
            format_status_html("Motion Library", "No saved motion yet")
        )

    with server.gui.add_folder("Video Export"):
        video_duration_number = server.gui.add_number(
            "Video Duration",
            initial_value=4.0,
            step=0.5,
            min=0.5,
        )
        video_fps_number = server.gui.add_number(
            "Video FPS",
            initial_value=24,
            step=1,
            min=1,
        )
        video_width_number = server.gui.add_number(
            "Video Width",
            initial_value=960,
            step=2,
            min=2,
        )
        video_height_number = server.gui.add_number(
            "Video Height",
            initial_value=540,
            step=2,
            min=2,
        )
        export_video_button = server.gui.add_button("Export Motion Video")
        video_status_text = server.gui.add_html(
            format_status_html("Video Export", "No video export yet")
        )

    def set_joint_sliders_enabled(enabled: bool) -> None:
        joint_x_slider.disabled = not enabled
        joint_y_slider.disabled = not enabled
        joint_z_slider.disabled = not enabled

    def set_root_sliders_enabled(enabled: bool) -> None:
        root_x_slider.disabled = not enabled
        root_y_slider.disabled = not enabled
        root_z_slider.disabled = not enabled

    def set_selected_joint_dropdown_value(value: str) -> None:
        state.suppress_joint_dropdown_callbacks = True
        selected_joint_dropdown.value = value
        state.suppress_joint_dropdown_callbacks = False

    def set_markdown_status(handle: Any, label: str, message: str) -> None:
        handle.content = format_status_html(label, message)

    def sync_root_sliders(root_offset: Vec3f) -> None:
        state.suppress_root_slider_callbacks = True
        root_x_slider.value = float(root_offset[0])
        root_y_slider.value = float(root_offset[1])
        root_z_slider.value = float(root_offset[2])
        state.suppress_root_slider_callbacks = False

    def sorted_keyframes() -> list[dict[str, Any]]:
        return sorted(state.keyframes or [], key=lambda item: float(item["time_sec"]))

    def selected_keyframed_motion_payload() -> dict[str, Any] | None:
        source_kind, source_value = motion_sources[clip_dropdown.value]
        if source_kind in {"built_in", "working_sequence"}:
            return None
        try:
            return load_saved_motion_payload(Path(source_value))
        except Exception:
            return None

    def selected_motion_preview_duration() -> float:
        if motion_sources[clip_dropdown.value][0] == "working_sequence":
            ordered_keyframes = sorted_keyframes()
            if len(ordered_keyframes) >= 2:
                start_time = float(ordered_keyframes[0]["time_sec"])
                end_time = float(ordered_keyframes[-1]["time_sec"])
                return max(0.1, end_time - start_time)
            return max(0.1, float(timeline_length_slider.value))
        payload = selected_keyframed_motion_payload()
        if payload is None:
            return 4.0
        duration = float(payload.get("duration_sec", 0.0))
        if duration > 0.0:
            return duration
        keyframes = payload.get("keyframes") or []
        if keyframes:
            return max(float(keyframe["time_sec"]) for keyframe in keyframes)
        return 4.0

    def selected_motion_preview_marks() -> tuple[GuiSliderMark, ...] | None:
        source_kind, _source_value = motion_sources[clip_dropdown.value]
        if source_kind == "working_sequence":
            keyframes = sorted_keyframes()
            if not keyframes:
                return None
            start_time = float(keyframes[0]["time_sec"])
            return tuple(
                GuiSliderMark(value=max(0.0, float(keyframe["time_sec"]) - start_time), label=None)
                for keyframe in keyframes
            )
        payload = selected_keyframed_motion_payload()
        if payload is None:
            return None
        return tuple(
            GuiSliderMark(value=float(keyframe["time_sec"]), label=None)
            for keyframe in sorted(payload["keyframes"], key=lambda item: float(item["time_sec"]))
        )

    def selected_motion_is_animatable() -> bool:
        source_kind, _source_value = motion_sources[clip_dropdown.value]
        if source_kind == "built_in":
            return True
        if source_kind == "working_sequence":
            return bool(state.keyframes)
        payload = selected_keyframed_motion_payload()
        return bool(payload and payload.get("keyframes"))

    def find_keyframe_index_at_time(
        time_sec: float,
        *,
        tolerance: float = 1e-4,
    ) -> int | None:
        for index, keyframe in enumerate(state.keyframes or []):
            if abs(float(keyframe["time_sec"]) - time_sec) <= tolerance:
                return index
        return None

    def current_timeline_time() -> float:
        return round(float(timeline_time_slider.value), 6)

    def sync_timeline_length_control(length: float) -> None:
        clamped_length = max(
            float(timeline_length_slider.min),
            min(float(length), float(timeline_length_slider.max)),
        )
        clamped_length = round(clamped_length, 6)
        state.suppress_timeline_end_callbacks = True
        timeline_length_slider.value = clamped_length
        state.suppress_timeline_end_callbacks = False

    def sync_timeline_time_controls(time_sec: float) -> None:
        clamped_time = max(0.0, min(float(time_sec), float(timeline_length_slider.value)))
        clamped_time = round(clamped_time, 6)
        state.suppress_timeline_time_callbacks = True
        timeline_time_slider.value = clamped_time
        state.suppress_timeline_time_callbacks = False

    def sync_motion_preview_time_control(time_sec: float) -> None:
        clamped_time = max(0.0, min(float(time_sec), float(motion_preview_time_slider.max)))
        clamped_time = round(clamped_time, 6)
        state.suppress_motion_preview_time_callbacks = True
        motion_preview_time_slider.value = clamped_time
        state.suppress_motion_preview_time_callbacks = False

    def update_motion_preview_controls() -> None:
        duration = selected_motion_preview_duration()
        motion_preview_time_slider.min = 0.0
        motion_preview_time_slider.max = max(0.1, duration)
        motion_preview_time_slider.step = 0.1
        motion_preview_time_slider._marks = selected_motion_preview_marks()
        sync_motion_preview_time_control(motion_preview_time_slider.value)
        update_animation_controls()

    def update_animation_controls() -> None:
        skinning_ready = state.asset is None or state.asset.skinning_error is None
        can_preview_motion = (
            state.asset is not None
            and selected_motion_is_animatable()
            and skinning_ready
        )
        motion_preview_time_slider.disabled = not can_preview_motion
        animate_checkbox.disabled = not can_preview_motion
        export_video_button.disabled = state.is_exporting_video or not can_preview_motion
        if not can_preview_motion and animate_checkbox.value:
            animate_checkbox.value = False

    def selected_motion_export_duration() -> float:
        source_kind, _source_value = motion_sources[clip_dropdown.value]
        if source_kind == "working_sequence":
            ordered_keyframes = sorted_keyframes()
            if len(ordered_keyframes) < 2:
                raise ValueError("Add at least two sequence keyframes first")
            start_time = float(ordered_keyframes[0]["time_sec"])
            end_time = float(ordered_keyframes[-1]["time_sec"])
            duration = end_time - start_time
            if duration <= 0.0:
                raise ValueError("Sequence keyframes need positive timestamps")
            return duration

        if selected_keyframed_motion_payload() is not None:
            duration = selected_motion_preview_duration()
        else:
            duration = float(video_duration_number.value)
        if duration <= 0.0:
            raise ValueError("Video duration must be positive")
        return duration

    def update_video_duration_control() -> None:
        source_kind, _source_value = motion_sources[clip_dropdown.value]
        video_duration_number.disabled = source_kind != "built_in"
        if source_kind == "built_in":
            return
        try:
            video_duration_number.value = round(selected_motion_export_duration(), 3)
        except ValueError:
            video_duration_number.value = round(max(0.1, selected_motion_preview_duration()), 3)

    def has_saveable_working_sequence() -> bool:
        return bool(state.keyframes and len(state.keyframes) >= 2)

    def working_sequence_has_editable_source() -> bool:
        return (
            state.working_sequence_source_kind == "saved"
            and state.working_sequence_source_path is not None
        )

    def update_sequence_save_controls() -> None:
        can_save = has_saveable_working_sequence()
        save_current_sequence_button.disabled = not (can_save and working_sequence_has_editable_source())
        save_new_sequence_button.disabled = not can_save

    def set_working_sequence_source(
        *,
        source_kind: str | None,
        source_path: Path | None,
        source_name: str | None,
    ) -> None:
        state.working_sequence_source_kind = source_kind
        state.working_sequence_source_path = None if source_path is None else source_path.resolve()
        state.working_sequence_source_name = source_name
        update_sequence_save_controls()

    def update_timeline_controls() -> None:
        latest_keyframe_time = (
            max(float(keyframe["time_sec"]) for keyframe in state.keyframes)
            if state.keyframes
            else 0.0
        )
        if latest_keyframe_time > float(timeline_length_slider.value):
            sync_timeline_length_control(math.ceil(latest_keyframe_time * 2.0) / 2.0)

        slider_max = float(timeline_length_slider.value)
        timeline_time_slider.min = 0.0
        timeline_time_slider.max = slider_max
        timeline_time_slider.step = 0.1
        keyframe_marks = tuple(
            GuiSliderMark(value=float(keyframe["time_sec"]), label=None)
            for keyframe in sorted_keyframes()
        )
        timeline_time_slider._marks = keyframe_marks if keyframe_marks else None

        current_time = max(0.0, min(float(timeline_time_slider.value), slider_max))
        sync_timeline_time_controls(current_time)
        has_keyframe_at_time = find_keyframe_index_at_time(current_time) is not None
        capture_pose_button.label = (
            "Update Pose In Sequence"
            if has_keyframe_at_time
            else "Add Pose To Sequence"
        )
        load_motion_sequence_button.disabled = selected_keyframed_motion_payload() is None
        remove_keyframe_button.disabled = not has_keyframe_at_time
        update_sequence_save_controls()
        update_video_duration_control()
        if motion_sources[clip_dropdown.value][0] == "working_sequence":
            update_motion_preview_controls()

    def update_joint_dropdown_options() -> None:
        state.suppress_joint_dropdown_callbacks = True
        if state.asset is None:
            selected_joint_dropdown.options = ("None",)
            selected_joint_dropdown.value = "None"
            selected_joint_dropdown.disabled = True
        else:
            selected_joint_dropdown.options = ("None",) + tuple(
                joint.name for joint in state.asset.joints
            )
            selected_joint_dropdown.value = "None"
            selected_joint_dropdown.disabled = False
        state.suppress_joint_dropdown_callbacks = False

    def update_skinning_controls() -> None:
        has_asset = state.asset is not None
        is_skinned = (
            has_asset
            and state.asset.skinned_model_data is not None
            and state.asset.skinning_error is None
        )
        use_lbs_checkbox.disabled = not is_skinned
        show_skinning_weights_checkbox.disabled = (
            not has_asset
            or (
                state.asset.asset_kind != "rigid"
                and not is_skinned
            )
        )
        if not is_skinned:
            state.suppress_use_lbs_callbacks = True
            use_lbs_checkbox.value = False
            state.suppress_use_lbs_callbacks = False
        if show_skinning_weights_checkbox.disabled and show_skinning_weights_checkbox.value:
            show_skinning_weights_checkbox.value = False
        if not has_asset:
            set_markdown_status(skinning_status_text, "Skinning", "No asset loaded.")
        elif state.asset.skinning_error is not None:
            set_markdown_status(
                skinning_status_text,
                "Skinning",
                f"Rest mesh only. {state.asset.skinning_error}",
            )
        elif is_skinned:
            set_markdown_status(skinning_status_text, "Skinning", "SMPL skinning ready.")
        else:
            set_markdown_status(skinning_status_text, "Skinning", "Rigid asset.")

    def update_skinning_weight_overlay(mesh_vertices: np.ndarray | None) -> None:
        if (
            state.asset is None
            or state.skinning_weight_handle is None
        ):
            if state.skinning_weight_handle is not None:
                state.skinning_weight_handle.visible = False
            return

        if not show_skinning_weights_checkbox.value:
            state.skinning_weight_handle.visible = False
            return

        if state.asset.asset_kind == "rigid":
            if state.current_world_rotations is None or state.current_world_positions is None:
                state.skinning_weight_handle.visible = False
                return
            points, colors = rigid_skinning_overlay_points_and_colors(
                state.asset,
                state.current_world_rotations,
                state.current_world_positions,
                state.selected_joint_index,
            )
        else:
            if state.asset.skinned_model_data is None or mesh_vertices is None:
                state.skinning_weight_handle.visible = False
                return
            points, colors = skinned_mesh_overlay_points_and_colors(
                state.asset,
                mesh_vertices,
                use_blended_weights=use_lbs_checkbox.value,
                selected_joint_index=state.selected_joint_index,
            )
        state.skinning_weight_handle.points = points
        state.skinning_weight_handle.colors = colors
        state.skinning_weight_handle.visible = True

    def reset_joint_sliders() -> None:
        state.suppress_joint_slider_callbacks = True
        joint_x_slider.value = 0.0
        joint_y_slider.value = 0.0
        joint_z_slider.value = 0.0
        state.suppress_joint_slider_callbacks = False

    def sync_joint_sliders_to_rotation(rotation: Mat3f) -> None:
        x_deg, y_deg, z_deg = matrix_to_euler_xyz_degrees(rotation)
        state.suppress_joint_slider_callbacks = True
        joint_x_slider.value = x_deg
        joint_y_slider.value = y_deg
        joint_z_slider.value = z_deg
        state.suppress_joint_slider_callbacks = False

    def clear_joint_selection() -> None:
        state.selected_joint_index = None
        set_selected_joint_dropdown_value("None")
        set_joint_sliders_enabled(False)
        reset_joint_sliders()
        if state.current_local_rotations is not None and state.current_root_offset is not None:
            show_pose(state.current_local_rotations, state.current_root_offset)
            return
        update_visualization_visibility(
            state,
            show_skeleton=show_skeleton_checkbox.value,
            show_mesh=show_mesh_checkbox.value,
            show_skinning_weights=show_skinning_weights_checkbox.value,
            show_joint_handles=show_joint_handles_checkbox.value,
            show_joint_labels=show_joint_labels_checkbox.value,
            show_joint_axes=show_joint_axes_checkbox.value,
        )

    def reset_current_pose() -> None:
        if state.asset is None:
            return
        state.selected_joint_index = None
        set_selected_joint_dropdown_value("None")
        set_joint_sliders_enabled(False)
        reset_joint_sliders()
        identity_rotations = [np.eye(3, dtype=np.float32) for _ in state.asset.joints]
        root_offset = np.zeros(3, dtype=np.float32)
        state.manual_local_rotations = copy_rotations(identity_rotations)
        state.manual_root_offset = root_offset.copy()
        show_pose(identity_rotations, root_offset)

    def sync_drag_handle() -> None:
        if (
            state.transform_control_handle is None
            or state.selected_joint_index is None
            or state.current_world_rotations is None
            or state.current_world_positions is None
        ):
            return
        state.suppress_transform_callback = True
        state.transform_control_handle.position = state.current_world_positions[state.selected_joint_index]
        state.transform_control_handle.wxyz = matrix_to_quaternion(
            state.current_world_rotations[state.selected_joint_index]
        )
        state.suppress_transform_callback = False

    def update_keyframe_status() -> None:
        count = len(state.keyframes or [])
        set_markdown_status(captured_count_text, "Sequence", f"{count} keyframes")

    def preview_timeline_time(time_sec: float) -> None:
        if state.asset is None:
            return
        animate_checkbox.value = False
        sampled_pose = sample_captured_keyframe_pose(time_sec)
        if sampled_pose is None:
            reset_current_pose()
            return
        local_rotations, root_offset = sampled_pose
        state.manual_local_rotations = copy_rotations(local_rotations)
        state.manual_root_offset = root_offset.copy()
        show_pose(local_rotations, root_offset)

    def preview_selected_motion(time_sec: float) -> None:
        if state.asset is None:
            return
        if state.asset.skinning_error is not None:
            animate_checkbox.value = False
            reset_current_pose()
            return
        try:
            pose_sample = sample_selected_motion(time_sec)
        except Exception as exc:
            if motion_sources[clip_dropdown.value][0] == "working_sequence":
                animate_checkbox.value = False
                reset_current_pose()
                set_markdown_status(motion_library_status_text, "Motion Library", str(exc))
                return
            set_markdown_status(motion_library_status_text, "Motion Library", f"Could not load motion: {exc}")
            traceback.print_exc()
            return
        local_rotations = pose_sample_to_asset_local_rotations(state.asset, pose_sample)
        root_offset = pose_sample.root_offset
        clear_joint_selection()
        state.manual_local_rotations = copy_rotations(local_rotations)
        state.manual_root_offset = root_offset.copy()
        show_pose(local_rotations, root_offset)

    def refresh_motion_dropdown_options() -> None:
        motion_sources.clear()
        motion_sources[WORKING_SEQUENCE_LABEL] = ("working_sequence", WORKING_SEQUENCE_LABEL)
        for clip_name in CLIP_NAMES:
            motion_sources[clip_name] = ("built_in", clip_name)
        for label, path in discover_motion_library(preset_motion_dir, label_prefix="Preset").items():
            motion_sources[label] = ("preset", path)
        for label, path in discover_motion_library(motion_library_dir).items():
            motion_sources[label] = ("saved", path)
        previous_value = clip_dropdown.value if clip_dropdown.value in motion_sources else None
        clip_dropdown.options = tuple(motion_sources.keys())
        if previous_value is not None:
            clip_dropdown.value = previous_value
        else:
            clip_dropdown.value = CLIP_NAMES[0] if CLIP_NAMES else WORKING_SEQUENCE_LABEL

    def sanitize_filename_stem(value: str, default: str) -> str:
        cleaned = "".join(character.lower() if character.isalnum() else "_" for character in value.strip())
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        cleaned = cleaned.strip("_")
        return cleaned or default

    def incremented_name(name: str, default: str) -> str:
        stripped = name.strip() or default
        match = re.match(r"^(.*?)(?:_(\d+))?$", stripped)
        if match is None:
            return f"{stripped}_2"
        root = match.group(1) or default
        suffix = match.group(2)
        if suffix is None:
            return f"{root}_2"
        return f"{root}_{int(suffix) + 1}"

    def next_available_library_name(
        desired_name: str,
        *,
        default: str,
        existing_stems: set[str],
    ) -> str:
        candidate_name = desired_name.strip() or default
        while sanitize_filename_stem(candidate_name, default) in existing_stems:
            candidate_name = incremented_name(candidate_name, default)
        return candidate_name

    def existing_pose_library_stems() -> set[str]:
        if not pose_library_dir.exists():
            return set()
        return {
            path.stem.removesuffix(".pose")
            for path in pose_library_dir.glob("*.pose.json")
        }

    def existing_motion_library_stems() -> set[str]:
        if not motion_library_dir.exists():
            return set()
        return {
            path.stem.removesuffix(".motion")
            for path in motion_library_dir.glob("*.motion.json")
        }

    def motion_display_name(label: str, payload: dict[str, Any]) -> str:
        payload_name = str(payload.get("name", "")).strip()
        if payload_name:
            return payload_name
        for prefix in ("Preset: ", "Saved: "):
            if label.startswith(prefix):
                return label.removeprefix(prefix)
        return label

    def suggest_sequence_name(source_name: str) -> str:
        return next_available_library_name(
            incremented_name(source_name, "custom_sequence"),
            default="custom_sequence",
            existing_stems=existing_motion_library_stems(),
        )

    def refresh_saved_pose_options() -> None:
        named_pose_sources.clear()
        recent_pose_sources.clear()
        discovered_named, discovered_recent = discover_pose_library(pose_library_dir)
        named_pose_sources.update(discovered_named)
        recent_pose_sources.update(discovered_recent)

        named_options = ("None",) + tuple(named_pose_sources.keys())
        recent_options = ("None",) + tuple(recent_pose_sources.keys())
        current_named = (
            named_pose_dropdown.value if named_pose_dropdown.value in named_options else "None"
        )
        current_recent = (
            recent_pose_dropdown.value if recent_pose_dropdown.value in recent_options else "None"
        )
        named_pose_dropdown.options = named_options
        named_pose_dropdown.value = current_named
        recent_pose_dropdown.options = recent_options
        recent_pose_dropdown.value = current_recent

    def clear_other_pose_dropdown(*, keep: str) -> None:
        if keep == "named":
            recent_pose_dropdown.value = "None"
        elif keep == "recent":
            named_pose_dropdown.value = "None"

    def selected_pose_path() -> Path | None:
        if named_pose_dropdown.value != "None":
            return named_pose_sources.get(named_pose_dropdown.value)
        if recent_pose_dropdown.value != "None":
            return recent_pose_sources.get(recent_pose_dropdown.value)
        return None

    def clear_saved_pose_library() -> int:
        removed_pose_count = 0
        if pose_library_dir.exists():
            for path in pose_library_dir.glob("*.pose.json"):
                path.unlink(missing_ok=True)
                removed_pose_count += 1
        refresh_saved_pose_options()
        return removed_pose_count

    def clear_recent_pose_library() -> int:
        removed_pose_count = 0
        recent_dir = pose_library_dir / "recent"
        if recent_dir.exists():
            for path in recent_dir.glob("*.pose.json"):
                path.unlink(missing_ok=True)
                removed_pose_count += 1
        refresh_saved_pose_options()
        return removed_pose_count

    def clear_saved_motion_library() -> int:
        removed_motion_count = 0
        if motion_library_dir.exists():
            for path in motion_library_dir.glob("*.motion.json"):
                path.unlink(missing_ok=True)
                removed_motion_count += 1
        motion_payload_cache.clear()
        refresh_motion_dropdown_options()
        return removed_motion_count

    def asset_slug(asset: AssetData) -> str:
        return asset.label.lower().replace(" ", "_")

    def current_pose_to_canonical_rotations() -> list[Mat3f] | None:
        if (
            state.asset is None
            or state.asset.profile_name is None
            or state.current_local_rotations is None
        ):
            return None
        return retarget_local_rotations(
            state.current_local_rotations,
            state.asset.profile_name,
            COURSE_BODY_24_PROFILE.joint_names,
            COURSE_BODY_24_PROFILE.name,
        )

    def build_pose_payload(
        pose_name: str,
        keyframe: dict[str, Any],
        *,
        storage_class: str,
    ) -> dict[str, Any]:
        return {
            "format": "gf5_saved_pose",
            "version": 1,
            "name": pose_name,
            "storage_class": storage_class,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "profile_name": COURSE_BODY_24_PROFILE.name,
            "joint_order": list(COURSE_BODY_24_PROFILE.joint_names),
            "pose": keyframe,
        }

    def autosave_recent_pose(keyframe: dict[str, Any]) -> Path | None:
        if state.asset is None:
            return None
        recent_dir = pose_library_dir / "recent"
        recent_dir.mkdir(parents=True, exist_ok=True)
        source_slug = asset_slug(state.asset)
        time_tag = f"{float(keyframe['time_sec']):05.2f}".replace(".", "p")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        pose_name = f"{state.asset.label} {time_tag}s {timestamp}"
        payload = build_pose_payload(pose_name, keyframe, storage_class="recent")
        snapshot_path = recent_dir / f"{source_slug}_recent_{time_tag}s_{timestamp}.pose.json"
        snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        refresh_saved_pose_options()
        return snapshot_path

    def build_motion_library_payload(
        motion_name: str,
        keyframes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        duration_sec = float(keyframes[-1]["time_sec"]) if keyframes else 0.0
        return {
            "format": "gf5_keyframed_motion",
            "version": 1,
            "name": motion_name,
            "profile_name": COURSE_BODY_24_PROFILE.name,
            "joint_order": list(COURSE_BODY_24_PROFILE.joint_names),
            "duration_sec": round(duration_sec, 6),
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "source_asset_name": None if state.asset is None else state.asset.label,
            "keyframes": keyframes,
        }

    def write_motion_library_payload(
        *,
        motion_name: str,
        export_path: Path,
    ) -> None:
        keyframes = copy.deepcopy(sorted_keyframes())
        payload = build_motion_library_payload(motion_name, keyframes)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        motion_payload_cache.pop(export_path, None)
        motion_payload_cache.pop(export_path.resolve(), None)

    def serialize_current_pose(time_sec: float) -> dict[str, Any] | None:
        if (
            state.asset is None
            or state.current_local_rotations is None
            or state.current_root_offset is None
            or state.asset.profile_name is None
        ):
            return None
        canonical_rotations = current_pose_to_canonical_rotations()
        if canonical_rotations is None:
            return None
        return {
            "time_sec": round(float(time_sec), 6),
            "root_offset": [round(float(v), 6) for v in state.current_root_offset],
            "local_rotation_matrices": [
                [[round(float(value), 6) for value in row] for row in rotation]
                for rotation in canonical_rotations
            ],
        }

    def deserialize_canonical_keyframe_pose(keyframe: dict[str, Any]) -> tuple[list[Mat3f], Vec3f]:
        root_offset = np.asarray(keyframe["root_offset"], dtype=np.float32)
        local_rotations = [
            np.asarray(rotation, dtype=np.float32)
            for rotation in keyframe["local_rotation_matrices"]
        ]
        return local_rotations, root_offset

    def canonical_keyframe_to_asset_pose(
        keyframe: dict[str, Any],
    ) -> tuple[list[Mat3f], Vec3f] | None:
        if state.asset is None:
            return None
        canonical_rotations, root_offset = deserialize_canonical_keyframe_pose(keyframe)
        pose_sample = PoseSample(
            profile_name=COURSE_BODY_24_PROFILE.name,
            root_offset=root_offset,
            local_rotations=canonical_rotations,
        )
        return pose_sample_to_asset_local_rotations(state.asset, pose_sample), root_offset

    def upsert_keyframe(keyframe: dict[str, Any]) -> str:
        if state.keyframes is None:
            state.keyframes = []
        target_time = float(keyframe["time_sec"])
        for index, existing in enumerate(state.keyframes):
            if abs(float(existing["time_sec"]) - target_time) < 1e-6:
                state.keyframes[index] = keyframe
                state.keyframes.sort(key=lambda item: float(item["time_sec"]))
                return "updated"
        state.keyframes.append(keyframe)
        state.keyframes.sort(key=lambda item: float(item["time_sec"]))
        return "added"

    def load_saved_pose_payload(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != "gf5_saved_pose":
            raise ValueError(f"{path.name} is not a saved pose file.")
        if payload.get("profile_name") != COURSE_BODY_24_PROFILE.name:
            raise ValueError(f"{path.name} does not use the course pose profile.")
        if tuple(payload.get("joint_order", ())) != COURSE_BODY_24_PROFILE.joint_names:
            raise ValueError(f"{path.name} has an unexpected joint order.")
        pose = payload.get("pose")
        if not isinstance(pose, dict):
            raise ValueError(f"{path.name} does not contain a valid pose.")
        return payload

    def load_saved_motion_payload(path: Path) -> dict[str, Any]:
        mtime = path.stat().st_mtime
        cached = motion_payload_cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != "gf5_keyframed_motion":
            raise ValueError(f"{path.name} is not a GF5 motion library file.")
        if payload.get("profile_name") != COURSE_BODY_24_PROFILE.name:
            raise ValueError(f"{path.name} does not use the course motion profile.")
        if tuple(payload.get("joint_order", ())) != COURSE_BODY_24_PROFILE.joint_names:
            raise ValueError(f"{path.name} has an unexpected joint order.")
        if not payload.get("keyframes"):
            raise ValueError(f"{path.name} does not contain any keyframes.")

        motion_payload_cache[path] = (mtime, payload)
        return payload

    def sample_keyframes_as_pose_sample(
        keyframes: list[dict[str, Any]],
        sample_time: float,
        *,
        loop_duration: float | None,
    ) -> PoseSample:
        ordered_keyframes = sorted(keyframes, key=lambda item: float(item["time_sec"]))
        if len(ordered_keyframes) == 1:
            local_rotations, root_offset = deserialize_canonical_keyframe_pose(ordered_keyframes[0])
            return PoseSample(
                profile_name=COURSE_BODY_24_PROFILE.name,
                root_offset=root_offset,
                local_rotations=local_rotations,
            )

        if loop_duration is not None and loop_duration > 0.0:
            sample_time = math.fmod(sample_time, loop_duration)
            if sample_time < 0.0:
                sample_time += loop_duration

        if sample_time <= float(ordered_keyframes[0]["time_sec"]):
            local_rotations, root_offset = deserialize_canonical_keyframe_pose(ordered_keyframes[0])
            return PoseSample(
                profile_name=COURSE_BODY_24_PROFILE.name,
                root_offset=root_offset,
                local_rotations=local_rotations,
            )

        if loop_duration is None and sample_time >= float(ordered_keyframes[-1]["time_sec"]):
            local_rotations, root_offset = deserialize_canonical_keyframe_pose(ordered_keyframes[-1])
            return PoseSample(
                profile_name=COURSE_BODY_24_PROFILE.name,
                root_offset=root_offset,
                local_rotations=local_rotations,
            )

        for first, second in zip(ordered_keyframes[:-1], ordered_keyframes[1:]):
            t0 = float(first["time_sec"])
            t1 = float(second["time_sec"])
            if t0 <= sample_time <= t1:
                if abs(t1 - t0) < 1e-6:
                    local_rotations, root_offset = deserialize_canonical_keyframe_pose(second)
                    return PoseSample(
                        profile_name=COURSE_BODY_24_PROFILE.name,
                        root_offset=root_offset,
                        local_rotations=local_rotations,
                    )
                alpha = (sample_time - t0) / (t1 - t0)
                rotations0, root0 = deserialize_canonical_keyframe_pose(first)
                rotations1, root1 = deserialize_canonical_keyframe_pose(second)
                root_offset = ((1.0 - alpha) * root0 + alpha * root1).astype(np.float32)
                local_rotations: list[Mat3f] = []
                for rotation0, rotation1 in zip(rotations0, rotations1):
                    q0 = matrix_to_quaternion(rotation0)
                    q1 = matrix_to_quaternion(rotation1)
                    local_rotations.append(quaternion_to_matrix(quaternion_slerp(q0, q1, alpha)))
                return PoseSample(
                    profile_name=COURSE_BODY_24_PROFILE.name,
                    root_offset=root_offset,
                    local_rotations=local_rotations,
                )

        local_rotations, root_offset = deserialize_canonical_keyframe_pose(ordered_keyframes[-1])
        return PoseSample(
            profile_name=COURSE_BODY_24_PROFILE.name,
            root_offset=root_offset,
            local_rotations=local_rotations,
        )

    def sample_saved_motion_payload(payload: dict[str, Any], sample_time: float) -> PoseSample:
        duration_sec = float(payload.get("duration_sec", payload["keyframes"][-1]["time_sec"]))
        return sample_keyframes_as_pose_sample(
            payload["keyframes"],
            sample_time,
            loop_duration=duration_sec if duration_sec > 0.0 else None,
        )

    def sample_working_sequence_as_motion(sample_time: float) -> PoseSample:
        ordered_keyframes = sorted_keyframes()
        if not ordered_keyframes:
            raise ValueError("Working Sequence has no keyframes.")
        start_time = float(ordered_keyframes[0]["time_sec"])
        end_time = float(ordered_keyframes[-1]["time_sec"])
        duration_sec = end_time - start_time
        if duration_sec > 1e-6:
            local_time = math.fmod(max(0.0, float(sample_time)), duration_sec)
            source_time = start_time + local_time
        else:
            source_time = start_time
        return sample_keyframes_as_pose_sample(
            ordered_keyframes,
            source_time,
            loop_duration=None,
        )

    def sample_selected_motion(sample_time: float) -> PoseSample:
        source_kind, source_value = motion_sources[clip_dropdown.value]
        if source_kind == "working_sequence":
            return sample_working_sequence_as_motion(sample_time)
        if source_kind == "built_in":
            return sample_motion_clip(str(source_value), sample_time)
        payload = load_saved_motion_payload(Path(source_value))
        return sample_saved_motion_payload(payload, sample_time)

    def sample_captured_keyframe_pose(sample_time: float) -> tuple[list[Mat3f], Vec3f] | None:
        if state.asset is None or not state.keyframes:
            return None
        ordered_keyframes = sorted_keyframes()
        sample_time = float(sample_time)
        start_time = float(ordered_keyframes[0]["time_sec"])
        end_time = float(ordered_keyframes[-1]["time_sec"])
        if sample_time < start_time - 1e-6 or sample_time > end_time + 1e-6:
            return None
        pose_sample = sample_keyframes_as_pose_sample(
            ordered_keyframes,
            sample_time,
            loop_duration=None,
        )
        return pose_sample_to_asset_local_rotations(state.asset, pose_sample), pose_sample.root_offset

    def sample_export_pose(sample_time: float) -> tuple[list[Mat3f], Vec3f] | None:
        if state.asset is None:
            return None
        pose_sample = sample_selected_motion(sample_time)
        return pose_sample_to_asset_local_rotations(state.asset, pose_sample), pose_sample.root_offset

    def show_pose(local_rotations: list[Mat3f], root_offset: Vec3f) -> None:
        if state.asset is None:
            return
        world_rotations, fk_world_positions = forward_kinematics(
            state.asset.joints,
            local_rotations,
            root_offset,
            state.asset.topological_order,
        )
        mesh_vertices = None
        world_positions = fk_world_positions
        if state.asset.skinned_model_data is not None:
            try:
                mesh_vertices = skin_smpl_mesh(
                    state.asset.skinned_model_data,
                    world_rotations,
                    world_positions,
                    use_blended_weights=use_lbs_checkbox.value,
                )
            except Exception as exc:
                state.asset.skinning_error = (
                    "Part 2 mesh skinning is not ready: "
                    f"{format_exception_summary(exc)}"
                )
                state.asset.skinned_model_data = None
                animate_checkbox.value = False
                update_skinning_controls()
                update_animation_controls()
                traceback.print_exc()
                mesh_vertices = (
                    np.asarray(state.asset.mesh_vertices, dtype=np.float32)
                    if state.asset.mesh_vertices is not None
                    else None
                )
        state.current_local_rotations = copy_rotations(local_rotations)
        state.current_root_offset = root_offset.copy()
        state.current_world_rotations = world_rotations.copy()
        state.current_world_positions = world_positions.copy()
        sync_root_sliders(root_offset)
        update_skinning_weight_overlay(mesh_vertices)
        update_keyframe_status()
        apply_pose(
            state,
            world_rotations,
            world_positions,
            mesh_vertices,
            show_skeleton_checkbox.value,
            show_mesh_checkbox.value,
            show_skinning_weights_checkbox.value,
            show_joint_handles_checkbox.value,
            show_joint_labels_checkbox.value,
            show_joint_axes_checkbox.value,
        )

    def select_joint(joint_index: int) -> None:
        if state.asset is None or state.current_local_rotations is None or state.current_root_offset is None:
            return
        animate_checkbox.value = False
        state.manual_local_rotations = copy_rotations(state.current_local_rotations)
        state.manual_root_offset = state.current_root_offset.copy()
        state.selected_joint_index = joint_index
        if not show_joint_handles_checkbox.value:
            show_joint_handles_checkbox.value = True
        set_selected_joint_dropdown_value(state.asset.joints[joint_index].name)
        set_joint_sliders_enabled(True)
        sync_joint_sliders_to_rotation(state.manual_local_rotations[joint_index])
        sync_drag_handle()
        show_pose(state.manual_local_rotations, state.manual_root_offset)

    def apply_joint_slider_rotation() -> None:
        if (
            state.suppress_joint_slider_callbacks
            or state.selected_joint_index is None
            or state.manual_local_rotations is None
            or state.manual_root_offset is None
        ):
            return
        state.manual_local_rotations[state.selected_joint_index] = euler_xyz_degrees_to_matrix(
            joint_x_slider.value,
            joint_y_slider.value,
            joint_z_slider.value,
        )
        show_pose(state.manual_local_rotations, state.manual_root_offset)

    def apply_root_translation() -> None:
        if (
            state.suppress_root_slider_callbacks
            or state.current_local_rotations is None
            or state.current_root_offset is None
        ):
            return
        animate_checkbox.value = False
        if state.manual_local_rotations is None:
            state.manual_local_rotations = copy_rotations(state.current_local_rotations)
        state.manual_root_offset = np.asarray(
            [root_x_slider.value, root_y_slider.value, root_z_slider.value],
            dtype=np.float32,
        )
        show_pose(state.manual_local_rotations, state.manual_root_offset)

    def load_selected_asset() -> None:
        state.is_loading_asset = True
        try:
            asset_kind, asset_path = asset_sources[asset_dropdown.value]
            if asset_kind == "smpl":
                asset = load_smpl_asset(asset_path)
            elif asset_kind == "up2you":
                asset = load_up2you_character_asset(asset_path, smplx_model_path)
            else:
                asset = load_asset(asset_path)
            render_asset(server, state, asset)
            update_joint_dropdown_options()
            update_skinning_controls()
            set_root_sliders_enabled(True)
            clear_joint_selection()
            refresh_saved_pose_options()
            update_motion_preview_controls()
            sync_motion_preview_time_control(0.0)
            if asset.skinning_error is not None:
                animate_checkbox.value = False
                reset_current_pose()
            else:
                preview_selected_motion(0.0)

            if state.joint_marker_handles is not None:
                for joint_index, marker_handle in enumerate(state.joint_marker_handles):
                    def set_callback_in_closure(joint_index: int, marker_handle: Any) -> None:
                        @marker_handle.on_click
                        def _(_: Any) -> None:
                            select_joint(joint_index)

                    set_callback_in_closure(joint_index, marker_handle)
            if state.transform_control_handle is not None:
                @state.transform_control_handle.on_update
                def _(_: Any) -> None:
                    if (
                        state.is_loading_asset
                        or state.suppress_transform_callback
                        or state.asset is None
                        or state.selected_joint_index is None
                        or state.manual_local_rotations is None
                        or state.manual_root_offset is None
                        or state.current_world_rotations is None
                    ):
                        return

                    joint_index = state.selected_joint_index
                    target_world_rotation = quaternion_to_matrix(
                        np.asarray(state.transform_control_handle.wxyz, dtype=np.float32)
                    )
                    parent_index = state.asset.joints[joint_index].parent
                    if parent_index >= 0:
                        parent_world_rotation = state.current_world_rotations[parent_index]
                        local_rotation = parent_world_rotation.T @ target_world_rotation
                    else:
                        local_rotation = target_world_rotation

                    state.manual_local_rotations[joint_index] = local_rotation
                    sync_joint_sliders_to_rotation(local_rotation)
                    show_pose(state.manual_local_rotations, state.manual_root_offset)
            if state.root_transform_handle is not None:
                @state.root_transform_handle.on_update
                def _(_: Any) -> None:
                    if (
                        state.is_loading_asset
                        or state.suppress_root_transform_callback
                        or state.asset is None
                        or state.current_local_rotations is None
                        or state.current_root_offset is None
                    ):
                        return

                    animate_checkbox.value = False
                    if state.manual_local_rotations is None:
                        state.manual_local_rotations = copy_rotations(state.current_local_rotations)
                    target_root_position = np.asarray(state.root_transform_handle.position, dtype=np.float32)
                    root_offset = target_root_position - state.asset.joints[0].translation
                    state.manual_root_offset = root_offset.astype(np.float32)
                    sync_root_sliders(state.manual_root_offset)
                    show_pose(state.manual_local_rotations, state.manual_root_offset)
            set_markdown_status(timeline_status_text, "Working Sequence", "No sequence edits yet")
            set_markdown_status(pose_status_text, "Pose Library", "No saved pose yet")
            set_markdown_status(motion_library_status_text, "Motion Library", "No saved motion yet")
            set_markdown_status(video_status_text, "Video Export", "No video export yet")
            update_keyframe_status()
            update_timeline_controls()
        finally:
            state.is_loading_asset = False

    def unique_asset_source_label(base_label: str) -> str:
        label = base_label
        suffix = 2
        while label in asset_sources:
            label = f"{base_label} ({suffix})"
            suffix += 1
        return label

    def add_imported_avatar_source(file_name: str, character_root: Path) -> str:
        label = unique_asset_source_label(avatar_import_label_from_filename(file_name))
        asset_sources[label] = ("up2you", character_root)
        asset_dropdown.options = tuple(asset_sources.keys())
        asset_dropdown.value = label
        return label

    @avatar_zip_upload.on_upload
    def _(_: Any) -> None:
        uploaded_file = avatar_zip_upload.value
        avatar_zip_upload.disabled = True
        try:
            set_markdown_status(
                avatar_import_status_text,
                "Avatar Import",
                f"Importing {uploaded_file.name}",
            )
            character_root = import_avatar_zip_bytes(
                uploaded_file.name,
                uploaded_file.content,
                avatar_import_root,
            )
            label = add_imported_avatar_source(uploaded_file.name, character_root)
            load_selected_asset()
            set_markdown_status(
                avatar_import_status_text,
                "Avatar Import",
                f"Loaded {label}",
            )
        except Exception as exc:
            set_markdown_status(
                avatar_import_status_text,
                "Avatar Import",
                f"Could not load avatar zip: {exc}",
            )
            traceback.print_exc()
        finally:
            avatar_zip_upload.disabled = False

    @asset_dropdown.on_update
    def _(_: Any) -> None:
        try:
            load_selected_asset()
        except Exception:
            traceback.print_exc()

    @selected_joint_dropdown.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset or state.suppress_joint_dropdown_callbacks or state.asset is None:
            return
        if selected_joint_dropdown.value == "None":
            clear_joint_selection()
            return
        for joint_index, joint in enumerate(state.asset.joints):
            if joint.name == selected_joint_dropdown.value:
                select_joint(joint_index)
                return

    @show_skeleton_checkbox.on_update
    def _(_: Any) -> None:
        update_visualization_visibility(
            state,
            show_skeleton=show_skeleton_checkbox.value,
            show_mesh=show_mesh_checkbox.value,
            show_skinning_weights=show_skinning_weights_checkbox.value,
            show_joint_handles=show_joint_handles_checkbox.value,
            show_joint_labels=show_joint_labels_checkbox.value,
            show_joint_axes=show_joint_axes_checkbox.value,
        )

    @show_mesh_checkbox.on_update
    def _(_: Any) -> None:
        update_visualization_visibility(
            state,
            show_skeleton=show_skeleton_checkbox.value,
            show_mesh=show_mesh_checkbox.value,
            show_skinning_weights=show_skinning_weights_checkbox.value,
            show_joint_handles=show_joint_handles_checkbox.value,
            show_joint_labels=show_joint_labels_checkbox.value,
            show_joint_axes=show_joint_axes_checkbox.value,
        )

    @show_skinning_weights_checkbox.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset:
            return
        if state.current_local_rotations is not None and state.current_root_offset is not None:
            show_pose(state.current_local_rotations, state.current_root_offset)
        else:
            update_visualization_visibility(
                state,
                show_skeleton=show_skeleton_checkbox.value,
                show_mesh=show_mesh_checkbox.value,
                show_skinning_weights=show_skinning_weights_checkbox.value,
                show_joint_handles=show_joint_handles_checkbox.value,
                show_joint_labels=show_joint_labels_checkbox.value,
                show_joint_axes=show_joint_axes_checkbox.value,
            )

    @show_joint_handles_checkbox.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset:
            return
        if not show_joint_handles_checkbox.value:
            clear_joint_selection()
            return
        update_visualization_visibility(
            state,
            show_skeleton=show_skeleton_checkbox.value,
            show_mesh=show_mesh_checkbox.value,
            show_skinning_weights=show_skinning_weights_checkbox.value,
            show_joint_handles=show_joint_handles_checkbox.value,
            show_joint_labels=show_joint_labels_checkbox.value,
            show_joint_axes=show_joint_axes_checkbox.value,
        )

    @show_joint_labels_checkbox.on_update
    def _(_: Any) -> None:
        update_visualization_visibility(
            state,
            show_skeleton=show_skeleton_checkbox.value,
            show_mesh=show_mesh_checkbox.value,
            show_skinning_weights=show_skinning_weights_checkbox.value,
            show_joint_handles=show_joint_handles_checkbox.value,
            show_joint_labels=show_joint_labels_checkbox.value,
            show_joint_axes=show_joint_axes_checkbox.value,
        )

    @show_joint_axes_checkbox.on_update
    def _(_: Any) -> None:
        update_visualization_visibility(
            state,
            show_skeleton=show_skeleton_checkbox.value,
            show_mesh=show_mesh_checkbox.value,
            show_skinning_weights=show_skinning_weights_checkbox.value,
            show_joint_handles=show_joint_handles_checkbox.value,
            show_joint_labels=show_joint_labels_checkbox.value,
            show_joint_axes=show_joint_axes_checkbox.value,
        )

    @timeline_time_slider.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset or state.suppress_timeline_time_callbacks:
            return
        sync_timeline_time_controls(timeline_time_slider.value)
        update_timeline_controls()
        preview_timeline_time(timeline_time_slider.value)

    @timeline_length_slider.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset or state.suppress_timeline_end_callbacks:
            return
        sync_timeline_length_control(timeline_length_slider.value)
        sync_timeline_time_controls(timeline_time_slider.value)
        update_timeline_controls()
        preview_timeline_time(timeline_time_slider.value)

    @motion_preview_time_slider.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset or state.suppress_motion_preview_time_callbacks:
            return
        animate_checkbox.value = False
        sync_motion_preview_time_control(motion_preview_time_slider.value)
        preview_selected_motion(motion_preview_time_slider.value)

    @use_lbs_checkbox.on_update
    def _(_: Any) -> None:
        if state.is_loading_asset or state.suppress_use_lbs_callbacks:
            return
        if (
            state.asset is None
            or state.asset.skinned_model_data is None
            or state.current_local_rotations is None
            or state.current_root_offset is None
        ):
            return
        show_pose(state.current_local_rotations, state.current_root_offset)

    @animate_checkbox.on_update
    def _(_: Any) -> None:
        if animate_checkbox.value:
            clear_joint_selection()
            return
        if state.current_local_rotations is not None and state.current_root_offset is not None:
            state.manual_local_rotations = copy_rotations(state.current_local_rotations)
            state.manual_root_offset = state.current_root_offset.copy()

    @clip_dropdown.on_update
    def _(_: Any) -> None:
        if state.asset is None:
            return
        update_motion_preview_controls()
        sync_motion_preview_time_control(0.0)
        preview_selected_motion(0.0)
        update_timeline_controls()
        update_video_duration_control()

    @reset_button.on_click
    def _(_: Any) -> None:
        animate_checkbox.value = False
        if state.asset is None:
            return
        reset_current_pose()

    @joint_x_slider.on_update
    def _(_: Any) -> None:
        apply_joint_slider_rotation()

    @joint_y_slider.on_update
    def _(_: Any) -> None:
        apply_joint_slider_rotation()

    @joint_z_slider.on_update
    def _(_: Any) -> None:
        apply_joint_slider_rotation()

    @root_x_slider.on_update
    def _(_: Any) -> None:
        apply_root_translation()

    @root_y_slider.on_update
    def _(_: Any) -> None:
        apply_root_translation()

    @root_z_slider.on_update
    def _(_: Any) -> None:
        apply_root_translation()

    @reset_root_button.on_click
    def _(_: Any) -> None:
        state.suppress_root_slider_callbacks = True
        root_x_slider.value = 0.0
        root_y_slider.value = 0.0
        root_z_slider.value = 0.0
        state.suppress_root_slider_callbacks = False
        apply_root_translation()

    @clear_selection_button.on_click
    def _(_: Any) -> None:
        clear_joint_selection()

    @named_pose_dropdown.on_update
    def _(_: Any) -> None:
        if named_pose_dropdown.value != "None":
            clear_other_pose_dropdown(keep="named")

    @recent_pose_dropdown.on_update
    def _(_: Any) -> None:
        if recent_pose_dropdown.value != "None":
            clear_other_pose_dropdown(keep="recent")

    @capture_pose_button.on_click
    def _(_: Any) -> None:
        keyframe = serialize_current_pose(current_timeline_time())
        if keyframe is None:
            set_markdown_status(timeline_status_text, "Working Sequence", "No pose available to add to the sequence")
            return
        action = upsert_keyframe(keyframe)
        autosave_path = autosave_recent_pose(keyframe)
        if autosave_path is not None:
            set_markdown_status(
                timeline_status_text,
                "Working Sequence",
                f"{action.title()} keyframe at {keyframe['time_sec']:.2f}s and cached pose {autosave_path.name}",
            )
            state.last_export_path = autosave_path
        else:
            set_markdown_status(
                timeline_status_text,
                "Working Sequence",
                f"{action.title()} keyframe at {keyframe['time_sec']:.2f}s",
            )
        sync_timeline_time_controls(round(current_timeline_time() + 1.0, 2))
        update_keyframe_status()
        update_timeline_controls()

    @load_motion_sequence_button.on_click
    def _(_: Any) -> None:
        source_label = clip_dropdown.value
        source_kind, source_value = motion_sources[source_label]
        payload = selected_keyframed_motion_payload()
        if payload is None:
            set_markdown_status(
                timeline_status_text,
                "Working Sequence",
                "Selected motion is preview-only and has no stored keyframes",
            )
            return
        keyframes = sorted(
            copy.deepcopy(payload["keyframes"]),
            key=lambda item: float(item["time_sec"]),
        )
        state.keyframes = keyframes
        source_path = Path(source_value).resolve() if source_kind in {"preset", "saved"} else None
        source_name = motion_display_name(source_label, payload)
        set_working_sequence_source(
            source_kind=source_kind,
            source_path=source_path,
            source_name=source_name,
        )
        motion_name_text.value = suggest_sequence_name(source_name)
        duration = float(payload.get("duration_sec", 0.0))
        if duration <= 0.0 and keyframes:
            duration = max(float(keyframe["time_sec"]) for keyframe in keyframes)
        if duration > 0.0:
            sync_timeline_length_control(duration)
        sync_timeline_time_controls(0.0)
        animate_checkbox.value = False
        update_keyframe_status()
        update_timeline_controls()
        if clip_dropdown.value != WORKING_SEQUENCE_LABEL:
            clip_dropdown.value = WORKING_SEQUENCE_LABEL
        else:
            update_motion_preview_controls()
            sync_motion_preview_time_control(0.0)
            preview_selected_motion(0.0)
        set_markdown_status(
            timeline_status_text,
            "Working Sequence",
            f"Loaded {len(keyframes)} keyframes from {source_label}",
        )
        if source_kind == "saved":
            set_markdown_status(motion_library_status_text, "Motion Library", f"Editing saved sequence {source_name}")
        elif source_kind == "preset":
            set_markdown_status(motion_library_status_text, "Motion Library", f"Loaded preset {source_name}; save as new to keep edits")

    @remove_keyframe_button.on_click
    def _(_: Any) -> None:
        if not state.keyframes:
            set_markdown_status(timeline_status_text, "Working Sequence", "No keyframes to remove")
            update_timeline_controls()
            return
        current_time = current_timeline_time()
        keyframe_index = find_keyframe_index_at_time(current_time)
        if keyframe_index is None:
            set_markdown_status(
                timeline_status_text,
                "Working Sequence",
                f"No keyframe found at {current_time:.2f}s",
            )
            update_timeline_controls()
            return
        removed_keyframe = state.keyframes.pop(keyframe_index)
        set_markdown_status(
            timeline_status_text,
            "Working Sequence",
            f"Removed keyframe at {float(removed_keyframe['time_sec']):.2f}s",
        )
        update_keyframe_status()
        update_timeline_controls()
        preview_timeline_time(current_time)

    @clear_keyframes_button.on_click
    def _(_: Any) -> None:
        state.keyframes = []
        sync_timeline_length_control(DEFAULT_WORKING_SEQUENCE_DURATION)
        sync_timeline_time_controls(0.0)
        set_markdown_status(timeline_status_text, "Working Sequence", "Cleared the current sequence")
        update_keyframe_status()
        update_timeline_controls()
        if motion_sources[clip_dropdown.value][0] == "working_sequence":
            reset_current_pose()

    @save_pose_button.on_click
    def _(_: Any) -> None:
        keyframe = serialize_current_pose(current_timeline_time())
        if keyframe is None:
            set_markdown_status(pose_status_text, "Pose Library", "No pose available to save")
            return
        pose_name = next_available_library_name(
            pose_name_text.value,
            default="custom_pose",
            existing_stems=existing_pose_library_stems(),
        )
        pose_dir = pose_library_dir
        pose_dir.mkdir(parents=True, exist_ok=True)
        pose_filename = sanitize_filename_stem(pose_name, "custom_pose")
        pose_path = pose_dir / f"{pose_filename}.pose.json"
        payload = build_pose_payload(pose_name, keyframe, storage_class="named")
        pose_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        refresh_saved_pose_options()
        if pose_name in named_pose_sources:
            named_pose_dropdown.value = pose_name
            recent_pose_dropdown.value = "None"
        pose_name_text.value = incremented_name(pose_name, "custom_pose")
        set_markdown_status(pose_status_text, "Pose Library", f"Saved {pose_path.name}")

    @load_pose_button.on_click
    def _(_: Any) -> None:
        if state.asset is None:
            set_markdown_status(pose_status_text, "Pose Library", "No asset loaded")
            return
        pose_path = selected_pose_path()
        if pose_path is None:
            set_markdown_status(pose_status_text, "Pose Library", "Choose a named or recent pose first")
            return
        if not pose_path.exists():
            set_markdown_status(pose_status_text, "Pose Library", "Saved pose file not found")
            return
        try:
            payload = load_saved_pose_payload(pose_path)
        except Exception as exc:
            set_markdown_status(pose_status_text, "Pose Library", f"Could not load pose: {exc}")
            return
        pose_payload = dict(payload["pose"])
        pose_preview = canonical_keyframe_to_asset_pose(pose_payload)
        if pose_preview is None:
            set_markdown_status(pose_status_text, "Pose Library", "No asset loaded")
            return
        animate_checkbox.value = False
        local_rotations, root_offset = pose_preview
        state.manual_local_rotations = copy_rotations(local_rotations)
        state.manual_root_offset = root_offset.copy()
        show_pose(local_rotations, root_offset)
        clear_joint_selection()
        set_markdown_status(
            pose_status_text,
            "Pose Library",
            f"Loaded {pose_path.name}. Click Add Pose To Sequence to place it at {current_timeline_time():.2f}s",
        )

    @save_current_sequence_button.on_click
    def _(_: Any) -> None:
        if not has_saveable_working_sequence():
            set_markdown_status(motion_library_status_text, "Motion Library", "Add at least two sequence keyframes first")
            return
        if not working_sequence_has_editable_source() or state.working_sequence_source_path is None:
            set_markdown_status(
                motion_library_status_text,
                "Motion Library",
                "Current sequence has no editable saved-library source",
            )
            return
        motion_name = state.working_sequence_source_name or state.working_sequence_source_path.stem.removesuffix(".motion")
        write_motion_library_payload(
            motion_name=motion_name,
            export_path=state.working_sequence_source_path,
        )
        refresh_motion_dropdown_options()
        if clip_dropdown.value != WORKING_SEQUENCE_LABEL:
            clip_dropdown.value = WORKING_SEQUENCE_LABEL
        else:
            update_motion_preview_controls()
        set_markdown_status(
            motion_library_status_text,
            "Motion Library",
            f"Updated {state.working_sequence_source_path.name}",
        )
        update_sequence_save_controls()

    @save_new_sequence_button.on_click
    def _(_: Any) -> None:
        if not has_saveable_working_sequence():
            set_markdown_status(motion_library_status_text, "Motion Library", "Add at least two sequence keyframes first")
            return
        motion_name = next_available_library_name(
            motion_name_text.value,
            default="custom_sequence",
            existing_stems=existing_motion_library_stems(),
        )
        motion_filename = sanitize_filename_stem(motion_name, "custom_sequence")
        export_path = motion_library_dir / f"{motion_filename}.motion.json"
        write_motion_library_payload(
            motion_name=motion_name,
            export_path=export_path,
        )
        set_working_sequence_source(
            source_kind="saved",
            source_path=export_path,
            source_name=motion_name,
        )
        refresh_motion_dropdown_options()
        if clip_dropdown.value != WORKING_SEQUENCE_LABEL:
            clip_dropdown.value = WORKING_SEQUENCE_LABEL
        else:
            update_motion_preview_controls()
        motion_name_text.value = suggest_sequence_name(motion_name)
        set_markdown_status(motion_library_status_text, "Motion Library", f"Saved new sequence {export_path.name}")
        update_sequence_save_controls()

    @clear_pose_library_button.on_click
    def _(_: Any) -> None:
        modal = server.gui.add_modal("Confirm Clear Pose Library")
        with modal:
            server.gui.add_markdown(
                "Delete all named pose files in `libraries/poses/`?"
            )
            confirm_button = server.gui.add_button("Confirm Clear Pose Library")
            cancel_button = server.gui.add_button("Cancel")

        @cancel_button.on_click
        def _(_: Any) -> None:
            modal.close()

        @confirm_button.on_click
        def _(_: Any) -> None:
            removed_pose_count = clear_saved_pose_library()
            pose_name_text.value = "custom_pose"
            set_markdown_status(
                pose_status_text,
                "Pose Library",
                f"Cleared {removed_pose_count} named poses",
            )
            modal.close()

    @clear_recent_poses_button.on_click
    def _(_: Any) -> None:
        modal = server.gui.add_modal("Confirm Clear Recent Poses")
        with modal:
            server.gui.add_markdown(
                "Delete all auto-cached recent poses in `libraries/poses/recent/`?"
            )
            confirm_button = server.gui.add_button("Confirm Clear Recent Poses")
            cancel_button = server.gui.add_button("Cancel")

        @cancel_button.on_click
        def _(_: Any) -> None:
            modal.close()

        @confirm_button.on_click
        def _(_: Any) -> None:
            removed_pose_count = clear_recent_pose_library()
            set_markdown_status(
                pose_status_text,
                "Pose Library",
                f"Cleared {removed_pose_count} recent poses",
            )
            modal.close()

    @clear_motion_library_button.on_click
    def _(_: Any) -> None:
        modal = server.gui.add_modal("Confirm Clear Motion Library")
        with modal:
            server.gui.add_markdown(
                "Delete all saved motion files in `libraries/motions/`?"
            )
            confirm_button = server.gui.add_button("Confirm Clear Motion Library")
            cancel_button = server.gui.add_button("Cancel")

        @cancel_button.on_click
        def _(_: Any) -> None:
            modal.close()

        @confirm_button.on_click
        def _(_: Any) -> None:
            removed_motion_count = clear_saved_motion_library()
            if state.working_sequence_source_kind == "saved":
                set_working_sequence_source(
                    source_kind=None,
                    source_path=None,
                    source_name=None,
                )
            motion_name_text.value = "custom_sequence"
            set_markdown_status(
                motion_library_status_text,
                "Motion Library",
                f"Cleared {removed_motion_count} saved motions",
            )
            modal.close()

    @export_video_button.on_click
    def _(event: Any) -> None:
        if state.asset is None:
            set_markdown_status(video_status_text, "Video Export", "No asset loaded")
            return
        if state.asset.skinning_error is not None:
            set_markdown_status(video_status_text, "Video Export", "Implement Part 2 skinning before exporting motion")
            return
        if state.is_exporting_video:
            set_markdown_status(video_status_text, "Video Export", "Video export already in progress")
            return
        if event.client is None:
            set_markdown_status(video_status_text, "Video Export", "Run export from an open browser client")
            return

        try:
            duration_sec = selected_motion_export_duration()
        except ValueError as exc:
            set_markdown_status(video_status_text, "Video Export", str(exc))
            return

        fps = max(1, int(round(float(video_fps_number.value))))
        requested_width = int(round(float(video_width_number.value)))
        requested_height = int(round(float(video_height_number.value)))
        max_width = int(getattr(event.client.camera, "image_width", requested_width))
        max_height = int(getattr(event.client.camera, "image_height", requested_height))
        width = min(requested_width, max_width)
        height = min(requested_height, max_height)
        width, height = normalize_video_size(width, height)
        frame_count = max(1, int(round(duration_sec * fps)))
        frame_times = np.linspace(0.0, duration_sec, frame_count, endpoint=False)

        state.is_exporting_video = True
        export_video_button.disabled = True
        previous_local_rotations = (
            copy_rotations(state.current_local_rotations)
            if state.current_local_rotations is not None
            else None
        )
        previous_root_offset = (
            state.current_root_offset.copy()
            if state.current_root_offset is not None
            else None
        )
        try:
            frames: list[np.ndarray] = []
            for frame_index, sample_time in enumerate(frame_times):
                sampled_pose = sample_export_pose(sample_time)
                if sampled_pose is None:
                    raise RuntimeError("Could not sample a pose for video export.")
                local_rotations, root_offset = sampled_pose
                show_pose(local_rotations, root_offset)
                event.client.flush()
                set_markdown_status(
                    video_status_text,
                    "Video Export",
                    f"Rendering frame {frame_index + 1}/{frame_count}",
                )
                frame = np.asarray(
                    event.client.camera.get_render(
                        height=height,
                        width=width,
                        transport_format="jpeg",
                    ),
                    dtype=np.uint8,
                )
                frames.append(frame[..., :3].copy())

            video_export_dir.mkdir(parents=True, exist_ok=True)
            slug = state.asset.label.lower().replace(" ", "_")
            source_slug = (
                "working_sequence"
                if motion_sources[clip_dropdown.value][0] == "working_sequence"
                else sanitize_filename_stem(clip_dropdown.value, "motion")
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = video_export_dir / f"{slug}_{source_slug}_{timestamp}.mp4"
            set_markdown_status(video_status_text, "Video Export", "Encoding MP4")
            write_mp4_with_ffmpeg(frames, export_path, fps)
            set_markdown_status(video_status_text, "Video Export", f"Saved {export_path.name}")
        except Exception as exc:
            set_markdown_status(video_status_text, "Video Export", f"Video export failed: {exc}")
            traceback.print_exc()
        finally:
            if previous_local_rotations is not None and previous_root_offset is not None:
                show_pose(previous_local_rotations, previous_root_offset)
            state.is_exporting_video = False
            update_animation_controls()

    load_selected_asset()
    update_video_duration_control()
    update_timeline_controls()

    while True:
        if state.asset is not None and not state.is_exporting_video:
            if animate_checkbox.value:
                duration = selected_motion_preview_duration()
                preview_time = math.fmod(time.time(), max(0.001, duration))
                sync_motion_preview_time_control(preview_time)
                try:
                    pose_sample = sample_selected_motion(preview_time)
                except Exception as exc:
                    animate_checkbox.value = False
                    if motion_sources[clip_dropdown.value][0] == "working_sequence":
                        reset_current_pose()
                        set_markdown_status(motion_library_status_text, "Motion Library", str(exc))
                    else:
                        set_markdown_status(motion_library_status_text, "Motion Library", f"Could not load motion: {exc}")
                        traceback.print_exc()
                else:
                    local_rotations = pose_sample_to_asset_local_rotations(state.asset, pose_sample)
                    root_offset = pose_sample.root_offset
                    state.manual_local_rotations = copy_rotations(local_rotations)
                    state.manual_root_offset = root_offset.copy()
                    show_pose(local_rotations, root_offset)
        time.sleep(1.0 / 30.0)


if __name__ == "__main__":
    main()
