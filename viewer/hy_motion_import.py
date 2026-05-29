#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import struct
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


FBX_BINARY_HEADER = b"Kaydara FBX Binary  \x00\x1a\x00"
FBX_TICKS_PER_SECOND = 46_186_158_000.0

COURSE_BODY_24_PROFILE_NAME = "course_body_24"
COURSE_BODY_24_JOINT_NAMES = (
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
GF5_COORDINATE_CONVENTION = {
    "name": "gf5_viewer_body",
    "up_axis": [0.0, 0.0, 1.0],
    "forward_axis": [0.0, 1.0, 0.0],
    "anatomical_right_axis": [1.0, 0.0, 0.0],
    "native_smpl_to_viewer": "viewer=(-native_x, native_z, native_y)",
}

HY_TO_COURSE_JOINT_NAMES = {
    "pelvis": "Pelvis",
    "left_hip": "L_Hip",
    "right_hip": "R_Hip",
    "spine1": "Spine1",
    "left_knee": "L_Knee",
    "right_knee": "R_Knee",
    "spine2": "Spine2",
    "left_ankle": "L_Ankle",
    "right_ankle": "R_Ankle",
    "spine3": "Spine3",
    "left_foot": "L_Foot",
    "right_foot": "R_Foot",
    "neck": "Neck",
    "left_collar": "L_Collar",
    "right_collar": "R_Collar",
    "head": "Head",
    "left_shoulder": "L_Shoulder",
    "right_shoulder": "R_Shoulder",
    "left_elbow": "L_Elbow",
    "right_elbow": "R_Elbow",
    "left_wrist": "L_Wrist",
    "right_wrist": "R_Wrist",
}

# HY-Motion FBX exports use the same native body axes as the AMASS/SMPL-style
# NPZ path: +Y up, +Z forward, and +X on the anatomical-left side. GF5 viewer
# space is +Z up, +Y forward, anatomical right +X. Keep this as a proper
# rotation (determinant +1); a plain Y/Z swap mirrors the body.
HY_TO_VIEWER_ROTATION = np.asarray(
    [
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=np.float32,
)
if not np.isclose(np.linalg.det(HY_TO_VIEWER_ROTATION), 1.0):
    raise RuntimeError("HY_TO_VIEWER_ROTATION must be a proper rotation, not a reflection.")

EULER_ROTATION_ORDERS = {
    0: "XYZ",
    1: "XZY",
    2: "YZX",
    3: "YXZ",
    4: "ZXY",
    5: "ZYX",
    6: "XYZ",
}


@dataclass
class FbxNode:
    name: str
    props: list[Any]
    children: list["FbxNode"] = field(default_factory=list)


@dataclass(frozen=True)
class AnimationCurve:
    times: tuple[int, ...]
    values: tuple[float, ...]
    default: float


@dataclass
class FbxScene:
    models: dict[int, FbxNode]
    model_names: dict[int, str]
    curves: dict[int, AnimationCurve]
    model_curve_nodes: dict[tuple[str, str], int]
    curve_node_curves: dict[int, dict[str, int]]
    global_settings: dict[str, list[Any]]


class BinaryFbxReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        if not self.data.startswith(FBX_BINARY_HEADER):
            raise ValueError(f"{path.name} is not a binary FBX file.")
        self.version = struct.unpack_from("<I", self.data, len(FBX_BINARY_HEADER))[0]
        self.uses_64bit_offsets = self.version >= 7500
        self.null_record_length = 25 if self.uses_64bit_offsets else 13

    def read_nodes(self) -> list[FbxNode]:
        nodes: list[FbxNode] = []
        position = len(FBX_BINARY_HEADER) + 4
        while position < len(self.data):
            node, position = self._read_node(position)
            if node is None:
                break
            nodes.append(node)
        return nodes

    def _read_node(self, position: int) -> tuple[FbxNode | None, int]:
        if self.uses_64bit_offsets:
            end_offset, property_count, _property_bytes = struct.unpack_from(
                "<QQQ",
                self.data,
                position,
            )
            position += 24
        else:
            end_offset, property_count, _property_bytes = struct.unpack_from(
                "<III",
                self.data,
                position,
            )
            position += 12

        name_length = self.data[position]
        position += 1
        if (
            end_offset == 0
            and property_count == 0
            and _property_bytes == 0
            and name_length == 0
        ):
            return None, position

        name = self.data[position : position + name_length].decode("utf-8", errors="replace")
        position += name_length

        props: list[Any] = []
        for _ in range(property_count):
            prop, position = self._read_property(position)
            props.append(prop)

        children: list[FbxNode] = []
        while position < end_offset - self.null_record_length:
            child, position = self._read_node(position)
            if child is not None:
                children.append(child)

        return FbxNode(name=name, props=props, children=children), end_offset

    def _read_property(self, position: int) -> tuple[Any, int]:
        type_code = chr(self.data[position])
        position += 1
        if type_code == "Y":
            return struct.unpack_from("<h", self.data, position)[0], position + 2
        if type_code == "C":
            return bool(self.data[position]), position + 1
        if type_code == "I":
            return struct.unpack_from("<i", self.data, position)[0], position + 4
        if type_code == "F":
            return struct.unpack_from("<f", self.data, position)[0], position + 4
        if type_code == "D":
            return struct.unpack_from("<d", self.data, position)[0], position + 8
        if type_code == "L":
            return struct.unpack_from("<q", self.data, position)[0], position + 8
        if type_code in {"f", "d", "i", "l", "b", "c"}:
            return self._read_array_property(type_code, position)
        if type_code == "S":
            length = struct.unpack_from("<I", self.data, position)[0]
            position += 4
            raw = self.data[position : position + length]
            return raw.decode("utf-8", errors="replace"), position + length
        if type_code == "R":
            length = struct.unpack_from("<I", self.data, position)[0]
            position += 4
            return self.data[position : position + length], position + length
        raise ValueError(f"Unsupported FBX property type {type_code!r} in {self.path.name}.")

    def _read_array_property(self, type_code: str, position: int) -> tuple[tuple[Any, ...], int]:
        length, encoding, compressed_length = struct.unpack_from("<III", self.data, position)
        position += 12
        raw = self.data[position : position + compressed_length]
        position += compressed_length
        if encoding == 1:
            raw = zlib.decompress(raw)
        elif encoding != 0:
            raise ValueError(f"Unsupported FBX array encoding {encoding}.")

        if type_code == "b":
            return tuple(raw[:length]), position
        if type_code == "c":
            return tuple(bool(value) for value in raw[:length]), position

        element_format = {"f": "f", "d": "d", "i": "i", "l": "q"}[type_code]
        return struct.unpack("<" + element_format * length, raw), position


def clean_fbx_name(name: Any) -> str:
    return str(name).split("\x00\x01", 1)[0]


def top_level_node(nodes: list[FbxNode], name: str) -> FbxNode:
    for node in nodes:
        if node.name == name:
            return node
    raise ValueError(f"FBX file does not contain a top-level {name!r} node.")


def properties70(node: FbxNode) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for child in node.children:
        if child.name != "Properties70":
            continue
        for prop in child.children:
            if prop.name == "P" and len(prop.props) >= 4:
                result[str(prop.props[0])] = list(prop.props[4:])
    return result


def child_property(node: FbxNode, child_name: str, default: Any) -> Any:
    for child in node.children:
        if child.name == child_name and child.props:
            return child.props[0]
    return default


def parse_animation_curve(node: FbxNode) -> AnimationCurve:
    raw_times = child_property(node, "KeyTime", ())
    raw_values = child_property(node, "KeyValueFloat", ())
    default = float(child_property(node, "Default", 0.0))
    times = tuple(int(value) for value in raw_times)
    values = tuple(float(value) for value in raw_values)
    if times and len(times) != len(values):
        raise ValueError(
            f"Animation curve {node.props[0] if node.props else '<unknown>'} "
            f"has {len(times)} key times but {len(values)} values."
        )
    return AnimationCurve(times=times, values=values, default=default)


def load_fbx_scene(path: Path) -> FbxScene:
    nodes = BinaryFbxReader(path).read_nodes()
    objects = top_level_node(nodes, "Objects")
    connections = top_level_node(nodes, "Connections")

    models: dict[int, FbxNode] = {}
    model_names: dict[int, str] = {}
    animation_curve_nodes: dict[int, FbxNode] = {}
    curves: dict[int, AnimationCurve] = {}

    for node in objects.children:
        if not node.props:
            continue
        object_id = int(node.props[0])
        if node.name == "Model":
            models[object_id] = node
            model_names[object_id] = clean_fbx_name(node.props[1])
        elif node.name == "AnimationCurveNode":
            animation_curve_nodes[object_id] = node
        elif node.name == "AnimationCurve":
            curves[object_id] = parse_animation_curve(node)

    model_curve_nodes: dict[tuple[str, str], int] = {}
    curve_node_curves: dict[int, dict[str, int]] = {}
    for connection in connections.children:
        if connection.name != "C" or not connection.props:
            continue
        connection_type = connection.props[0]
        if connection_type != "OP":
            continue
        child_id = int(connection.props[1])
        parent_id = int(connection.props[2])
        property_name = str(connection.props[3])
        if parent_id in models and child_id in animation_curve_nodes:
            model_curve_nodes[(model_names[parent_id], property_name)] = child_id
        elif parent_id in animation_curve_nodes and child_id in curves:
            curve_node_curves.setdefault(parent_id, {})[property_name] = child_id

    global_settings_node = top_level_node(nodes, "GlobalSettings")
    return FbxScene(
        models=models,
        model_names=model_names,
        curves=curves,
        model_curve_nodes=model_curve_nodes,
        curve_node_curves=curve_node_curves,
        global_settings=properties70(global_settings_node),
    )


def rotation_x(angle: float) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]],
        dtype=np.float32,
    )


def rotation_y(angle: float) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]],
        dtype=np.float32,
    )


def rotation_z(angle: float) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def euler_degrees_to_matrix(values: np.ndarray, rotation_order: str) -> np.ndarray:
    rotations = {
        "X": rotation_x(math.radians(float(values[0]))),
        "Y": rotation_y(math.radians(float(values[1]))),
        "Z": rotation_z(math.radians(float(values[2]))),
    }
    matrix = np.eye(3, dtype=np.float32)
    # HY-Motion exports Euler angles with transforms3d's static-axis convention
    # (`mat2euler(..., axes="sxyz")` for XYZ), whose matrix reconstruction
    # applies the axis rotations in reverse order.
    for axis in reversed(rotation_order):
        matrix = matrix @ rotations[axis]
    return matrix


def matrix_to_viewer(matrix: np.ndarray) -> np.ndarray:
    return HY_TO_VIEWER_ROTATION @ np.asarray(matrix, dtype=np.float32) @ HY_TO_VIEWER_ROTATION.T


def vector_to_viewer(vector: np.ndarray) -> np.ndarray:
    return np.asarray(vector, dtype=np.float32) @ HY_TO_VIEWER_ROTATION.T


def evaluate_curve(curve: AnimationCurve, tick: int) -> float:
    if not curve.times:
        return curve.default
    index = bisect.bisect_left(curve.times, tick)
    if index < len(curve.times) and curve.times[index] == tick:
        return curve.values[index]
    if index <= 0:
        return curve.values[0]
    if index >= len(curve.times):
        return curve.values[-1]
    t0 = curve.times[index - 1]
    t1 = curve.times[index]
    if t1 == t0:
        return curve.values[index]
    alpha = (tick - t0) / (t1 - t0)
    return float((1.0 - alpha) * curve.values[index - 1] + alpha * curve.values[index])


def model_by_name(scene: FbxScene) -> dict[str, FbxNode]:
    return {name: scene.models[model_id] for model_id, name in scene.model_names.items()}


def model_vector_default(scene: FbxScene, model_name: str, property_name: str) -> np.ndarray:
    node = model_by_name(scene).get(model_name)
    if node is None:
        return np.zeros(3, dtype=np.float32)
    values = properties70(node).get(property_name)
    if values is None or len(values) < 3:
        return np.zeros(3, dtype=np.float32)
    return np.asarray(values[:3], dtype=np.float32)


def model_rotation_order(scene: FbxScene, model_name: str) -> str:
    node = model_by_name(scene).get(model_name)
    if node is None:
        return "XYZ"
    values = properties70(node).get("RotationOrder")
    if not values:
        return "XYZ"
    return EULER_ROTATION_ORDERS.get(int(values[0]), "XYZ")


def animated_vector(
    scene: FbxScene,
    model_name: str,
    property_name: str,
    tick: int,
) -> np.ndarray:
    values = model_vector_default(scene, model_name, property_name)
    curve_node_id = scene.model_curve_nodes.get((model_name, property_name))
    if curve_node_id is None:
        return values

    component_curves = scene.curve_node_curves.get(curve_node_id, {})
    for component_index, component_name in enumerate(("d|X", "d|Y", "d|Z")):
        curve_id = component_curves.get(component_name)
        if curve_id is not None:
            values[component_index] = evaluate_curve(scene.curves[curve_id], tick)
    return values


def collect_sample_ticks(scene: FbxScene) -> list[int]:
    sample_ticks: set[int] = set()
    relevant_models = set(HY_TO_COURSE_JOINT_NAMES.values())
    relevant_models.add("Pelvis")
    for model_name in relevant_models:
        for property_name in ("Lcl Translation", "Lcl Rotation"):
            curve_node_id = scene.model_curve_nodes.get((model_name, property_name))
            if curve_node_id is None:
                continue
            for curve_id in scene.curve_node_curves.get(curve_node_id, {}).values():
                sample_ticks.update(scene.curves[curve_id].times)
    if not sample_ticks:
        sample_ticks.add(0)
    return sorted(sample_ticks)


def prompt_for_fbx(path: Path) -> str | None:
    prompt_path = path.with_suffix(".txt")
    if not prompt_path.exists():
        return None
    prompt = prompt_path.read_text(encoding="utf-8-sig", errors="replace").strip()
    return prompt or None


def safe_motion_filename(path: Path) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("._-")
    return safe_stem or "hy_motion"


def rounded_matrix(matrix: np.ndarray) -> list[list[float]]:
    return [[round(float(value), 6) for value in row] for row in matrix]


def rounded_vector(vector: np.ndarray) -> list[float]:
    return [round(float(value), 6) for value in vector]


def root_contract_for_keyframes(keyframes: list[dict[str, Any]]) -> str:
    if len(keyframes) < 2:
        return "spot"
    root_offsets = np.asarray(
        [keyframe.get("root_offset", [0.0, 0.0, 0.0]) for keyframe in keyframes],
        dtype=np.float32,
    )
    horizontal = root_offsets[:, :2]
    displacement = float(np.linalg.norm(horizontal[-1] - horizontal[0]))
    span = float(np.linalg.norm(horizontal.max(axis=0) - horizontal.min(axis=0)))
    return "scene_path" if max(displacement, span) > 0.25 else "spot"


def build_motion_payload(
    fbx_path: Path,
    *,
    motion_name: str | None,
    unit_scale: float,
    source_fbx_path: str | None = None,
) -> dict[str, Any]:
    scene = load_fbx_scene(fbx_path)
    missing_required = [
        hy_name
        for hy_name in sorted(set(HY_TO_COURSE_JOINT_NAMES.values()))
        if hy_name not in set(scene.model_names.values())
    ]
    if missing_required:
        raise ValueError(
            f"{fbx_path.name} is missing expected HY-Motion joints: "
            + ", ".join(missing_required)
        )

    sample_ticks = collect_sample_ticks(scene)
    first_tick = sample_ticks[0]
    root_reference = animated_vector(scene, "Pelvis", "Lcl Translation", first_tick)
    prompt = prompt_for_fbx(fbx_path)
    name = motion_name or (f"HY-Motion: {prompt}" if prompt else f"HY-Motion: {fbx_path.stem}")

    keyframes: list[dict[str, Any]] = []
    for tick in sample_ticks:
        root_native = animated_vector(scene, "Pelvis", "Lcl Translation", tick)
        root_offset = vector_to_viewer((root_native - root_reference) * unit_scale)

        local_rotations: list[list[list[float]]] = []
        for course_joint_name in COURSE_BODY_24_JOINT_NAMES:
            hy_joint_name = HY_TO_COURSE_JOINT_NAMES.get(course_joint_name)
            if hy_joint_name is None:
                local_rotations.append(rounded_matrix(np.eye(3, dtype=np.float32)))
                continue
            euler_degrees = animated_vector(scene, hy_joint_name, "Lcl Rotation", tick)
            rotation_order = model_rotation_order(scene, hy_joint_name)
            native_rotation = euler_degrees_to_matrix(euler_degrees, rotation_order)
            local_rotations.append(rounded_matrix(matrix_to_viewer(native_rotation)))

        keyframes.append(
            {
                "time_sec": round(float((tick - first_tick) / FBX_TICKS_PER_SECOND), 6),
                "root_offset": rounded_vector(root_offset),
                "local_rotation_matrices": local_rotations,
            }
        )

    duration_sec = keyframes[-1]["time_sec"] if keyframes else 0.0
    root_contract = root_contract_for_keyframes(keyframes)
    return {
        "format": "gf5_keyframed_motion",
        "version": 1,
        "name": name,
        "profile_name": COURSE_BODY_24_PROFILE_NAME,
        "joint_order": list(COURSE_BODY_24_JOINT_NAMES),
        "coordinate_convention": GF5_COORDINATE_CONVENTION,
        "duration_sec": duration_sec,
        "source_class": "hy_motion_import",
        "source_prompt": prompt or "",
        "category": "other",
        "category_label": "Other",
        "root_contract": root_contract,
        "default_root_mode": "path",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "source_asset_name": None,
        "source": {
            "type": "hy_motion_1_0_fbx",
            "fbx_path": source_fbx_path or str(fbx_path),
            "prompt": prompt,
            "unit_scale_to_meters": unit_scale,
            "native_up_axis": "Y",
            "native_front_axis": "Z",
        },
        "keyframes": keyframes,
    }


def default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "libraries" / "motions" / "custom"


def expand_inputs(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.fbx")))
        else:
            expanded.append(path)
    return expanded


def convert_file(
    fbx_path: Path,
    *,
    output_dir: Path,
    motion_name: str | None,
    unit_scale: float,
    source_fbx_path: str | None = None,
) -> Path:
    payload = build_motion_payload(
        fbx_path,
        motion_name=motion_name,
        unit_scale=unit_scale,
        source_fbx_path=source_fbx_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_motion_filename(fbx_path)}.motion.json"
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert HY-Motion-1.0 downloadable FBX files into GF5 viewer motion JSON.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="HY-Motion FBX file(s), or directories containing *.fbx files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir(),
        help="Viewer motion-library directory to write *.motion.json files into.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Motion name to store in the viewer library. Only valid when converting one FBX.",
    )
    parser.add_argument(
        "--unit-scale",
        type=float,
        default=0.01,
        help="Scale from HY-Motion/Maya FBX units to viewer meters.",
    )
    args = parser.parse_args()

    fbx_paths = expand_inputs([path.resolve() for path in args.inputs])
    if not fbx_paths:
        raise SystemExit("No FBX files found.")
    if args.name is not None and len(fbx_paths) != 1:
        raise SystemExit("--name can only be used when converting exactly one FBX file.")

    for fbx_path in fbx_paths:
        if not fbx_path.exists():
            raise SystemExit(f"Missing input file: {fbx_path}")
        output_path = convert_file(
            fbx_path,
            output_dir=args.output_dir.resolve(),
            motion_name=args.name,
            unit_scale=args.unit_scale,
        )
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
