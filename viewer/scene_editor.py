from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import time
import traceback
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import viser
except ModuleNotFoundError as exc:
    missing = exc.name or "a required package"
    raise SystemExit(
        f"Missing Python dependency '{missing}'. Activate the GF5 environment first:\n"
        "  mamba activate gf5\n"
        "  python viewer/scene_editor.py --port 8091 --no-open-browser\n"
        "or run it directly with:\n"
        "  conda run -n gf5 python viewer/scene_editor.py --port 8091 --no-open-browser"
    ) from exc

os.environ.setdefault("MPLCONFIGDIR", str(Path("/tmp") / "gf5_matplotlib"))

from asset_viewer import (
    AssetData,
    Mat3f,
    Vec3f,
    discover_assets,
    forward_kinematics,
    load_asset,
    matrix_to_quaternion,
    normalize_video_size,
    pose_sample_to_asset_local_rotations,
    quaternion_slerp,
    quaternion_to_matrix,
    write_mp4_with_ffmpeg,
)
from motion_sequences import CLIP_NAMES, PoseSample, sample_motion_clip
from skeleton_profiles import COURSE_BODY_24_PROFILE


SCENE_FORMAT = "gf5_motion_scene"
DEFAULT_SCENE_STEM = "group_greeting_scene"
PREFERRED_PROXY_ASSET = "SMPL-24 Proxy"
DEFAULT_CLIP_BLEND_SECONDS = 0.45
MAX_TRANSITION_GAP_SECONDS = 0.25
CAMERA_ORIGIN_TARGET = "__origin__"
EXPORT_MAX_FPS = 24
EXPORT_MAX_WIDTH = 1280
EXPORT_MAX_HEIGHT = 720
CAMERA_PRESETS = (
    "slow_orbit",
    "wide_static",
    "front_stage",
    "follow_character",
    "dolly_in",
    "top_down",
)


@dataclass
class MotionSource:
    label: str
    kind: str
    value: str | Path
    duration: float
    payload: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    category: str = "other"
    category_label: str = "Other"
    root_contract: str = "spot"
    default_root_mode: str = "path"
    loopable: bool = False
    library_visible: bool = True


@dataclass
class TrackClip:
    clip: str
    start: float
    duration: float
    trim_start: float = 0.0
    trim_end: float | None = None
    root_mode: str = "path"
    root_start: Vec3f = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    root_end: Vec3f = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    facing_degrees: float = 0.0
    blend_in: float = DEFAULT_CLIP_BLEND_SECONDS
    blend_out: float = DEFAULT_CLIP_BLEND_SECONDS


@dataclass
class RootKey:
    time: float
    key_id: str = ""
    position: Vec3f = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    facing_degrees: float = 0.0


@dataclass
class RootSegment:
    from_id: str
    to_id: str
    mode: str = "linear"
    facing: str = "manual"


@dataclass
class SceneCharacter:
    character_id: str
    label: str
    proxy_asset: str
    avatar_asset: str = ""
    track: list[TrackClip] = field(default_factory=list)
    root_keys: list[RootKey] = field(default_factory=list)
    root_segments: list[RootSegment] = field(default_factory=list)


@dataclass
class SceneCamera:
    preset: str = "slow_orbit"
    target: str = CAMERA_ORIGIN_TARGET
    height: float = 1.35


@dataclass
class SceneExport:
    fps: int = 24
    width: int = 960
    height: int = 540


@dataclass
class SceneBackground:
    color: str = "#f4f1ea"
    image_path: str = ""
    show_grid: bool = True
    show_floor: bool = True


@dataclass
class MotionScene:
    duration: float = 8.0
    characters: list[SceneCharacter] = field(default_factory=list)
    camera: SceneCamera = field(default_factory=SceneCamera)
    export: SceneExport = field(default_factory=SceneExport)
    background: SceneBackground = field(default_factory=SceneBackground)


@dataclass
class CharacterRuntime:
    character: SceneCharacter
    asset: AssetData
    part_handles: list[Any] = field(default_factory=list)
    skeleton_handle: Any | None = None
    path_handle: Any | None = None
    label_handle: Any | None = None


@dataclass
class EditorState:
    scene: MotionScene
    runtimes: dict[str, CharacterRuntime] = field(default_factory=dict)
    selected_character_id: str = ""
    selected_clip_index: int = 0
    selected_root_key_index: int = 0
    preview_time: float = 0.0
    is_exporting: bool = False
    suppress_callbacks: bool = False


def sanitize_id(value: str, default: str = "character") -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return cleaned or default


def unique_character_id(scene: MotionScene, desired: str) -> str:
    existing = {character.character_id for character in scene.characters}
    base = sanitize_id(desired)
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def parse_color(value: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    text = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return tuple(int(text[index:index + 2], 16) for index in (1, 3, 5))
    return default


def normalize_export_settings(raw: Any) -> SceneExport:
    raw = raw if isinstance(raw, dict) else {}
    fps = int(round(float(raw.get("fps", 24))))
    width = int(round(float(raw.get("width", 960))))
    height = int(round(float(raw.get("height", 540))))
    return SceneExport(
        fps=max(1, min(EXPORT_MAX_FPS, fps)),
        width=max(320, min(EXPORT_MAX_WIDTH, width + (width % 2))),
        height=max(180, min(EXPORT_MAX_HEIGHT, height + (height % 2))),
    )


def color_background_image(color_hex: str) -> np.ndarray:
    color = parse_color(color_hex, (244, 241, 234))
    return np.asarray([[color]], dtype=np.uint8)


def load_background_image(path_text: str) -> np.ndarray | None:
    if not path_text.strip():
        return None
    path = Path(path_text).expanduser()
    if not path.exists():
        return None
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def format_status_html(label: str, message: str) -> str:
    return (
        '<div style="font-size:0.88em; line-height:1.35; '
        'color:var(--mantine-color-text); white-space:normal; '
        'overflow-wrap:anywhere; word-break:break-word; margin:-2px 0 3px 0; '
        'padding:0 var(--mantine-spacing-xs);">'
        f"<strong>{html.escape(label)}:</strong> {html.escape(message)}</div>"
    )


def track_clip_from_json(raw: dict[str, Any]) -> TrackClip:
    duration = max(0.001, float(raw.get("duration", 4.0)))
    return TrackClip(
        clip=str(raw.get("clip", "Walk")),
        start=float(raw.get("start", 0.0)),
        duration=duration,
        trim_start=max(0.0, float(raw.get("trim_start", 0.0))),
        trim_end=(
            None
            if raw.get("trim_end") is None
            else max(0.0, float(raw.get("trim_end")))
        ),
        root_mode=str(raw.get("root_mode", "path")),
        root_start=np.asarray(raw.get("root_start", [0.0, 0.0, 0.0]), dtype=np.float32),
        root_end=np.asarray(raw.get("root_end", raw.get("root_start", [0.0, 0.0, 0.0])), dtype=np.float32),
        facing_degrees=float(raw.get("facing_degrees", 0.0)),
        blend_in=track_clip_blend_from_json(raw, "blend_in", duration),
        blend_out=track_clip_blend_from_json(raw, "blend_out", duration),
    )


def track_clip_blend_from_json(raw: dict[str, Any], key: str, duration: float) -> float:
    default_blend = min(DEFAULT_CLIP_BLEND_SECONDS, max(0.05, duration * 0.3))
    value = raw.get(key, default_blend)
    if value is None or value == "":
        value = default_blend
    return max(0.0, min(duration, float(value)))


def track_clip_to_json(clip: TrackClip) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "clip": clip.clip,
        "start": round(float(clip.start), 6),
        "duration": round(float(clip.duration), 6),
        "trim_start": round(float(clip.trim_start), 6),
        "root_mode": clip.root_mode,
    }
    if clip.trim_end is not None:
        payload["trim_end"] = round(float(clip.trim_end), 6)
    if clip.blend_in > 0.0:
        payload["blend_in"] = round(float(clip.blend_in), 6)
    if clip.blend_out > 0.0:
        payload["blend_out"] = round(float(clip.blend_out), 6)
    return payload


def root_key_from_json(raw: dict[str, Any]) -> RootKey:
    return RootKey(
        key_id=str(raw.get("id", "")),
        time=max(0.0, float(raw.get("time", 0.0))),
        position=np.asarray(raw.get("position", [0.0, 0.0, 0.0]), dtype=np.float32),
        facing_degrees=float(raw.get("facing_degrees", 0.0)),
    )


def root_key_to_json(root_key: RootKey) -> dict[str, Any]:
    payload = {
        "time": round(float(root_key.time), 6),
        "position": [round(float(value), 6) for value in root_key.position],
        "facing_degrees": round(float(root_key.facing_degrees), 6),
    }
    if root_key.key_id:
        payload["id"] = root_key.key_id
    return payload


def root_segment_from_json(raw: dict[str, Any]) -> RootSegment:
    mode = str(raw.get("mode", "linear"))
    if mode not in {"linear", "curve", "hold"}:
        mode = "linear"
    return RootSegment(
        from_id=str(raw.get("from", "")),
        to_id=str(raw.get("to", "")),
        mode=mode,
        facing=str(raw.get("facing", "manual")),
    )


def root_segment_to_json(segment: RootSegment) -> dict[str, Any]:
    return {
        "from": segment.from_id,
        "to": segment.to_id,
        "mode": segment.mode,
        "facing": segment.facing,
    }


def derive_root_keys_from_v1_track(track: list[TrackClip]) -> list[RootKey]:
    keys_by_time: dict[float, RootKey] = {}
    for clip in track:
        start_time = round(float(clip.start), 6)
        end_time = round(float(clip.start + clip.duration), 6)
        keys_by_time[start_time] = RootKey(
            time=start_time,
            position=np.asarray(clip.root_start, dtype=np.float32),
            facing_degrees=float(clip.facing_degrees),
        )
        keys_by_time[end_time] = RootKey(
            time=end_time,
            position=np.asarray(clip.root_end, dtype=np.float32),
            facing_degrees=float(clip.facing_degrees),
        )
    if not keys_by_time:
        return [RootKey(time=0.0)]
    return sorted(keys_by_time.values(), key=lambda item: float(item.time))


def ensure_root_keys(character: SceneCharacter) -> None:
    if character.root_keys:
        character.root_keys.sort(key=lambda item: float(item.time))
        used_ids: set[str] = set()
        for index, key in enumerate(character.root_keys):
            if not key.key_id or key.key_id in used_ids:
                suffix = index
                while f"k{suffix}" in used_ids:
                    suffix += 1
                key.key_id = f"k{suffix}"
            used_ids.add(key.key_id)
        return
    character.root_keys = derive_root_keys_from_v1_track(character.track)
    for index, key in enumerate(character.root_keys):
        key.key_id = f"k{index}"


def scene_character_from_json(raw: dict[str, Any], default_asset: str) -> SceneCharacter:
    character_id = sanitize_id(str(raw.get("id", raw.get("character_id", "character"))))
    track = [track_clip_from_json(item) for item in raw.get("track", raw.get("clips", []))]
    root_keys = [root_key_from_json(item) for item in raw.get("root_keys", [])]
    root_segments = [
        root_segment_from_json(item)
        for item in raw.get("root_segments", [])
        if isinstance(item, dict)
    ]
    character = SceneCharacter(
        character_id=character_id,
        label=str(raw.get("label", character_id)),
        proxy_asset=str(raw.get("proxy_asset", default_asset)),
        avatar_asset=str(raw.get("avatar_asset", raw.get("asset", ""))),
        track=track,
        root_keys=root_keys,
        root_segments=root_segments,
    )
    ensure_root_keys(character)
    return character


def scene_to_json(scene: MotionScene) -> dict[str, Any]:
    return {
        "format": SCENE_FORMAT,
        "version": 3,
        "duration": round(float(scene.duration), 6),
        "background": {
            "color": scene.background.color,
            "image_path": scene.background.image_path,
            "show_grid": scene.background.show_grid,
            "show_floor": scene.background.show_floor,
        },
        "camera": {
            "preset": scene.camera.preset,
            "target": scene.camera.target,
            "height": round(float(scene.camera.height), 6),
        },
        "export": {
            "fps": int(scene.export.fps),
            "width": int(scene.export.width),
            "height": int(scene.export.height),
        },
        "characters": [
            {
                "id": character.character_id,
                "label": character.label,
                "proxy_asset": character.proxy_asset,
                "avatar_asset": character.avatar_asset,
                "track": [track_clip_to_json(clip) for clip in character.track],
                "root_keys": [root_key_to_json(root_key) for root_key in character.root_keys],
                "root_segments": [root_segment_to_json(segment) for segment in character.root_segments],
            }
            for character in scene.characters
        ],
    }


def scene_from_json(raw: dict[str, Any], default_asset: str) -> MotionScene:
    if raw.get("format") != SCENE_FORMAT:
        raise ValueError("Scene file is not a GF5 motion scene.")

    background_raw = raw.get("background", {})
    camera_raw = raw.get("camera", {})
    export_raw = raw.get("export", {})
    scene = MotionScene(
        duration=max(0.5, float(raw.get("duration", 8.0))),
        characters=[
            scene_character_from_json(item, default_asset)
            for item in raw.get("characters", [])
        ],
        camera=SceneCamera(
            preset=str(camera_raw.get("preset", "slow_orbit")),
            target=str(camera_raw.get("target", CAMERA_ORIGIN_TARGET)),
            height=float(camera_raw.get("height", 1.35)),
        ),
        export=normalize_export_settings(export_raw),
        background=SceneBackground(
            color=str(background_raw.get("color", "#f4f1ea")),
            image_path=str(background_raw.get("image_path", "")),
            show_grid=bool(background_raw.get("show_grid", True)),
            show_floor=bool(background_raw.get("show_floor", True)),
        ),
    )
    if not scene.characters:
        scene.characters = make_default_scene({}, {default_asset: Path(default_asset)}).characters
    return scene


def discover_scene_library(scene_dir: Path) -> dict[str, Path]:
    scenes: dict[str, Path] = {}
    if not scene_dir.exists():
        return scenes
    for path in sorted(scene_dir.glob("*.scene.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("format") != SCENE_FORMAT:
            continue
        label = path.stem.removesuffix(".scene")
        suffix = 2
        unique_label = label
        while unique_label in scenes:
            unique_label = f"{label} ({suffix})"
            suffix += 1
        scenes[unique_label] = path
    return scenes


def load_saved_motion_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != "gf5_keyframed_motion":
        raise ValueError(f"{path.name} is not a GF5 motion file.")
    if payload.get("profile_name") != COURSE_BODY_24_PROFILE.name:
        raise ValueError(f"{path.name} does not use the course motion profile.")
    if tuple(payload.get("joint_order", ())) != COURSE_BODY_24_PROFILE.joint_names:
        raise ValueError(f"{path.name} has an unexpected joint order.")
    if not payload.get("keyframes"):
        raise ValueError(f"{path.name} does not contain keyframes.")
    return payload


def load_collection_motion_paths(motion_dir: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for manifest_path in sorted(motion_dir.rglob("manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if manifest.get("format") != "gf5_preset_motion_collection":
            continue
        if not bool(manifest.get("load_by_default", False)):
            continue
        motions = manifest.get("motions")
        if not isinstance(motions, list):
            continue
        for entry in motions:
            if not isinstance(entry, dict):
                continue
            file_value = entry.get("file")
            if not file_value:
                continue
            path = (manifest_path.parent / str(file_value)).resolve()
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            paths.append(path)
    return paths


def motion_paths_for_dir(motion_dir: Path) -> list[Path]:
    collection_paths = load_collection_motion_paths(motion_dir)
    if collection_paths:
        return collection_paths
    return sorted(motion_dir.rglob("*.motion.json"))


def payload_string(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key, default)
    if value is None or value == "":
        return default
    return str(value)


def normalized_motion_text(value: str) -> str:
    text = value.lower().replace("hy-motion:", " ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def motion_duplicate_keys(name: str, prompt: str) -> set[tuple[str, str]]:
    keys = {("name", normalized_motion_text(name))}
    prompt_key = normalized_motion_text(prompt)
    if prompt_key:
        keys.add(("prompt", prompt_key))
    return {key for key in keys if key[1]}


def existing_motion_duplicate_keys(sources: dict[str, MotionSource]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for source in sources.values():
        prompt = ""
        if isinstance(source.payload, dict):
            prompt = str(source.payload.get("source_prompt", ""))
            source_dict = source.payload.get("source")
            if not prompt and isinstance(source_dict, dict):
                prompt = str(source_dict.get("prompt", ""))
        keys.update(motion_duplicate_keys(source.label.removeprefix("Preset: ").removeprefix("Custom: "), prompt))
    return keys


def add_motions_from_dir(
    sources: dict[str, MotionSource],
    motion_dir: Path,
    *,
    label_prefix: str,
    kind: str,
) -> None:
    if not motion_dir.exists():
        return
    for path in motion_paths_for_dir(motion_dir):
        try:
            payload = load_saved_motion_payload(path)
        except Exception:
            continue
        if payload.get("library_visible") is False:
            continue
        name = str(payload.get("name", path.stem))
        label = f"{label_prefix}: {name}"
        suffix = 2
        while label in sources:
            label = f"{label_prefix}: {name} ({suffix})"
            suffix += 1
        prompt = str(payload.get("source_prompt", ""))
        source_dict = payload.get("source")
        if not prompt and isinstance(source_dict, dict):
            prompt = str(source_dict.get("prompt", ""))
        source_class = payload_string(payload, "source_class", "")
        if (
            kind == "custom"
            and source_class != "hy_motion_import"
            and motion_duplicate_keys(name, prompt) & existing_motion_duplicate_keys(sources)
        ):
            continue
        tags = payload.get("tags")
        if not isinstance(tags, list):
            tags = []
        category = payload_string(payload, "category", "other")
        category_label = payload_string(payload, "category_label", category.replace("_", " ").title())
        root_contract = payload_string(payload, "root_contract", "spot")
        default_root_mode = payload_string(
            payload,
            "default_root_mode",
            "native" if root_contract == "native_travel" else "path",
        )
        if default_root_mode not in {"path", "native"}:
            default_root_mode = "path"
        sources[label] = MotionSource(
            label=label,
            kind=kind,
            value=path,
            duration=max(0.001, float(payload.get("duration_sec", 4.0))),
            payload=payload,
            tags=[str(tag) for tag in tags],
            category=category,
            category_label=category_label,
            root_contract=root_contract,
            default_root_mode=default_root_mode,
            loopable=bool(payload.get("loopable", False)),
            library_visible=bool(payload.get("library_visible", True)),
        )


def discover_motion_library(preset_motion_dir: Path, motion_dir: Path) -> dict[str, MotionSource]:
    sources: dict[str, MotionSource] = {
        "Idle Breathing": MotionSource(
            label="Idle Breathing",
            kind="idle",
            value="idle_breathing",
            duration=3.0,
            tags=["idle", "procedural"],
            category="standing_gesture",
            category_label="Standing / Gesture",
            root_contract="spot",
            default_root_mode="path",
            loopable=True,
            library_visible=False,
        )
    }
    sources.update(
        {
            name: MotionSource(
                label=name,
                kind="built_in",
                value=name,
                duration=4.0,
                tags=[name.lower(), "built-in"],
                category="travel_loop" if name == "Walk" else "standing_gesture",
                category_label="Travel Loops" if name == "Walk" else "Standing / Gesture",
                root_contract="scene_path" if name == "Walk" else "spot",
                default_root_mode="path",
                loopable=name == "Walk",
                library_visible=False,
            )
            for name in CLIP_NAMES
        }
    )
    add_motions_from_dir(
        sources,
        preset_motion_dir,
        label_prefix="Preset",
        kind="preset",
    )
    add_motions_from_dir(
        sources,
        motion_dir,
        label_prefix="Custom",
        kind="custom",
    )
    return sources


def visible_motion_labels(motion_library: dict[str, MotionSource]) -> tuple[str, ...]:
    labels = tuple(label for label, source in motion_library.items() if source.library_visible)
    return labels or tuple(motion_library.keys())


def first_visible_motion_label(motion_library: dict[str, MotionSource]) -> str:
    labels = visible_motion_labels(motion_library)
    return labels[0] if labels else next(iter(motion_library))


def motion_dropdown_options(
    motion_library: dict[str, MotionSource],
    current_label: str | None = None,
) -> tuple[str, ...]:
    labels = list(visible_motion_labels(motion_library))
    if current_label and current_label in motion_library and current_label not in labels:
        labels.insert(0, current_label)
    return tuple(labels)


def preferred_asset_label(asset_sources: dict[str, Path]) -> str:
    if PREFERRED_PROXY_ASSET in asset_sources:
        return PREFERRED_PROXY_ASSET
    return next(iter(asset_sources), "Marigold")


def default_asset_labels(asset_sources: dict[str, Path]) -> tuple[str, ...]:
    labels = tuple(asset_sources.keys())
    if not labels:
        return ("Marigold",)
    if PREFERRED_PROXY_ASSET not in asset_sources:
        return labels
    return (PREFERRED_PROXY_ASSET,) + tuple(label for label in labels if label != PREFERRED_PROXY_ASSET)


def make_idle_pose_sample(sample_time: float) -> PoseSample:
    phase = math.sin(sample_time * 2.0 * math.pi / 3.0)
    slow_phase = math.sin(sample_time * 2.0 * math.pi / 5.0)
    local_rotations = [np.eye(3, dtype=np.float32) for _ in COURSE_BODY_24_PROFILE.joint_names]
    joint_index = {name: index for index, name in enumerate(COURSE_BODY_24_PROFILE.joint_names)}
    local_rotations[joint_index["spine1"]] = rotation_z(0.015 * slow_phase)
    local_rotations[joint_index["spine2"]] = rotation_z(-0.018 * slow_phase)
    local_rotations[joint_index["neck"]] = rotation_z(0.012 * slow_phase)
    local_rotations[joint_index["left_shoulder"]] = rotation_z(0.035 + 0.012 * phase)
    local_rotations[joint_index["right_shoulder"]] = rotation_z(-0.035 - 0.012 * phase)
    root_offset = np.asarray([0.0, 0.0, 0.006 * phase], dtype=np.float32)
    return PoseSample(COURSE_BODY_24_PROFILE.name, root_offset, local_rotations)


def deserialize_canonical_keyframe_pose(keyframe: dict[str, Any]) -> tuple[list[Mat3f], Vec3f]:
    return (
        [np.asarray(rotation, dtype=np.float32) for rotation in keyframe["local_rotation_matrices"]],
        np.asarray(keyframe["root_offset"], dtype=np.float32),
    )


def sample_keyframes_as_pose_sample(
    keyframes: list[dict[str, Any]],
    sample_time: float,
    *,
    loop_duration: float | None,
) -> PoseSample:
    ordered = sorted(keyframes, key=lambda item: float(item["time_sec"]))
    if loop_duration is not None and loop_duration > 0.0:
        sample_time = math.fmod(sample_time, loop_duration)
        if sample_time < 0.0:
            sample_time += loop_duration

    if len(ordered) == 1 or sample_time <= float(ordered[0]["time_sec"]):
        rotations, root = deserialize_canonical_keyframe_pose(ordered[0])
        return PoseSample(COURSE_BODY_24_PROFILE.name, root, rotations)

    if loop_duration is None and sample_time >= float(ordered[-1]["time_sec"]):
        rotations, root = deserialize_canonical_keyframe_pose(ordered[-1])
        return PoseSample(COURSE_BODY_24_PROFILE.name, root, rotations)

    for first, second in zip(ordered[:-1], ordered[1:]):
        t0 = float(first["time_sec"])
        t1 = float(second["time_sec"])
        if t0 <= sample_time <= t1:
            if abs(t1 - t0) < 1e-6:
                rotations, root = deserialize_canonical_keyframe_pose(second)
                return PoseSample(COURSE_BODY_24_PROFILE.name, root, rotations)
            alpha = (sample_time - t0) / (t1 - t0)
            rotations0, root0 = deserialize_canonical_keyframe_pose(first)
            rotations1, root1 = deserialize_canonical_keyframe_pose(second)
            root = ((1.0 - alpha) * root0 + alpha * root1).astype(np.float32)
            rotations = [
                quaternion_to_matrix(
                    quaternion_slerp(
                        matrix_to_quaternion(rotation0),
                        matrix_to_quaternion(rotation1),
                        alpha,
                    )
                )
                for rotation0, rotation1 in zip(rotations0, rotations1)
            ]
            return PoseSample(COURSE_BODY_24_PROFILE.name, root, rotations)

    rotations, root = deserialize_canonical_keyframe_pose(ordered[-1])
    return PoseSample(COURSE_BODY_24_PROFILE.name, root, rotations)


def sample_motion_source(source: MotionSource, sample_time: float) -> PoseSample:
    if source.kind == "idle":
        return make_idle_pose_sample(sample_time)
    if source.kind == "built_in":
        return sample_motion_clip(str(source.value), sample_time)
    assert source.payload is not None
    duration = max(0.001, float(source.payload.get("duration_sec", source.duration)))
    return sample_keyframes_as_pose_sample(
        source.payload["keyframes"],
        sample_time,
        loop_duration=duration if source.loopable else None,
    )


def make_default_scene(
    motion_library: dict[str, MotionSource],
    asset_sources: dict[str, Path],
) -> MotionScene:
    asset_labels = default_asset_labels(asset_sources)
    walk_label = "Preset: Walk cycle" if "Preset: Walk cycle" in motion_library else "Walk"
    if walk_label not in motion_library and motion_library:
        walk_label = next(iter(motion_library))
    wave_label = "Preset: Right-hand wave" if "Preset: Right-hand wave" in motion_library else "Wave"
    if wave_label not in motion_library:
        wave_label = walk_label
    saved_labels = [
        label for label, source in motion_library.items()
        if source.kind in {"preset", "custom"}
    ]
    preferred_action_labels = (
        "Preset: Start walking",
        "Preset: Idle stand",
        "Preset: Right-hand wave",
    )
    action_label = next(
        (label for label in preferred_action_labels if label in motion_library),
        saved_labels[0] if saved_labels else walk_label,
    )
    return MotionScene(
        duration=8.0,
        camera=SceneCamera(preset="slow_orbit", target=CAMERA_ORIGIN_TARGET, height=1.35),
        characters=[
            SceneCharacter(
                character_id="alice",
                label="Alice",
                proxy_asset=asset_labels[0],
                track=[
                    TrackClip(
                        clip=walk_label,
                        start=0.0,
                        duration=4.0,
                    ),
                    TrackClip(
                        clip=wave_label,
                        start=4.0,
                        duration=3.5,
                    ),
                ],
                root_keys=[
                    RootKey(
                        time=0.0,
                        position=np.asarray([-1.2, -0.35, 0.0], dtype=np.float32),
                        facing_degrees=90.0,
                    ),
                    RootKey(
                        time=4.0,
                        position=np.asarray([0.0, -0.35, 0.0], dtype=np.float32),
                        facing_degrees=90.0,
                    ),
                    RootKey(
                        time=8.0,
                        position=np.asarray([0.0, -0.35, 0.0], dtype=np.float32),
                        facing_degrees=75.0,
                    ),
                ],
            ),
            SceneCharacter(
                character_id="bob",
                label="Bob",
                proxy_asset=asset_labels[min(1, len(asset_labels) - 1)],
                track=[
                    TrackClip(
                        clip=action_label,
                        start=1.0,
                        duration=4.5,
                    )
                ],
                root_keys=[
                    RootKey(
                        time=0.0,
                        position=np.asarray([1.15, 0.35, 0.0], dtype=np.float32),
                        facing_degrees=-90.0,
                    ),
                    RootKey(
                        time=5.5,
                        position=np.asarray([0.35, 0.35, 0.0], dtype=np.float32),
                        facing_degrees=-90.0,
                    ),
                    RootKey(
                        time=8.0,
                        position=np.asarray([0.35, 0.35, 0.0], dtype=np.float32),
                        facing_degrees=-60.0,
                    ),
                ],
            ),
        ],
    )


def selected_character(state: EditorState) -> SceneCharacter | None:
    for character in state.scene.characters:
        if character.character_id == state.selected_character_id:
            return character
    return state.scene.characters[0] if state.scene.characters else None


def selected_clip(state: EditorState) -> TrackClip | None:
    character = selected_character(state)
    if character is None or not character.track:
        return None
    state.selected_clip_index = max(0, min(state.selected_clip_index, len(character.track) - 1))
    return character.track[state.selected_clip_index]


def selected_root_key(state: EditorState) -> RootKey | None:
    character = selected_character(state)
    if character is None:
        return None
    ensure_root_keys(character)
    state.selected_root_key_index = max(0, min(state.selected_root_key_index, len(character.root_keys) - 1))
    return character.root_keys[state.selected_root_key_index]


def rotation_z(angle: float) -> Mat3f:
    c = math.cos(angle)
    s = math.sin(angle)
    return np.asarray(
        [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def root_yaw_radians(rotation: Mat3f) -> float:
    forward = np.asarray(rotation, dtype=np.float32) @ np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
    return math.atan2(float(forward[0]), float(forward[1]))


def normalize_pose_for_path_root_mode(pose: PoseSample, reference_pose: PoseSample) -> PoseSample:
    root_offset = np.asarray(pose.root_offset, dtype=np.float32).copy()
    root_offset[:2] = 0.0
    local_rotations = [np.asarray(rotation, dtype=np.float32).copy() for rotation in pose.local_rotations]
    if local_rotations and reference_pose.local_rotations:
        local_rotations[0] = rotation_z(-root_yaw_radians(reference_pose.local_rotations[0])) @ local_rotations[0]
    return PoseSample(
        profile_name=pose.profile_name,
        root_offset=root_offset,
        local_rotations=local_rotations,
    )


def sample_track_clip(
    clip: TrackClip,
    source: MotionSource,
    scene_time: float,
) -> PoseSample:
    if clip.duration <= 1e-6:
        alpha = 0.0
    else:
        alpha = max(0.0, min(1.0, (scene_time - clip.start) / clip.duration))
    trim_end = source.duration if clip.trim_end is None else clip.trim_end
    trim_end = max(clip.trim_start + 1e-6, trim_end)
    source_time = clip.trim_start + alpha * (trim_end - clip.trim_start)
    pose = sample_motion_source(source, source_time)
    if clip.root_mode == "native":
        return pose
    return normalize_pose_for_path_root_mode(pose, sample_motion_source(source, clip.trim_start))


def clip_end_time(clip: TrackClip) -> float:
    return float(clip.start + clip.duration)


def default_clip_blend(clip: TrackClip) -> float:
    return min(DEFAULT_CLIP_BLEND_SECONDS, max(0.05, float(clip.duration) * 0.3))


def effective_clip_blend_in(clip: TrackClip) -> float:
    return max(0.0, min(float(clip.duration), float(clip.blend_in)))


def effective_clip_blend_out(clip: TrackClip) -> float:
    return max(0.0, min(float(clip.duration), float(clip.blend_out)))


def clip_transition_window(first: TrackClip, second: TrackClip) -> tuple[float, float] | None:
    first_end = clip_end_time(first)
    second_start = float(second.start)
    second_end = clip_end_time(second)
    blend_out = effective_clip_blend_out(first)
    blend_in = effective_clip_blend_in(second)
    overlap_start = second_start
    overlap_end = min(first_end, second_end)
    if overlap_end > overlap_start + 1e-6:
        return min(overlap_start, first_end - blend_out), max(overlap_end, second_start + blend_in)

    if second_start - first_end > MAX_TRANSITION_GAP_SECONDS:
        return None
    if blend_out <= 1e-6 and blend_in <= 1e-6:
        return None
    return first_end - blend_out, second_start + blend_in


def sample_track_clip_clamped(
    clip: TrackClip,
    source: MotionSource,
    scene_time: float,
) -> PoseSample:
    return sample_track_clip(clip, source, max(float(clip.start), min(clip_end_time(clip), scene_time)))


def sample_idle_transition(
    clip: TrackClip,
    source: MotionSource,
    idle_source: MotionSource,
    scene_time: float,
    previous_clip: TrackClip | None = None,
    next_clip: TrackClip | None = None,
) -> PoseSample | None:
    start = float(clip.start)
    end = clip_end_time(clip)
    blend_in = effective_clip_blend_in(clip)
    blend_out = effective_clip_blend_out(clip)
    if blend_in > 1e-6 and start - blend_in <= scene_time < start:
        if previous_clip is not None:
            previous_end = clip_end_time(previous_clip)
            if scene_time <= previous_end + 1e-6 or start - previous_end <= MAX_TRANSITION_GAP_SECONDS:
                return None
        alpha = (scene_time - (start - blend_in)) / blend_in
        idle_pose = sample_motion_source(idle_source, scene_time)
        clip_pose = sample_track_clip_clamped(clip, source, start)
        return blend_pose_samples(idle_pose, clip_pose, alpha)
    if blend_out > 1e-6 and end < scene_time <= end + blend_out:
        if next_clip is not None:
            next_start = float(next_clip.start)
            if scene_time >= next_start - 1e-6 or next_start - end <= MAX_TRANSITION_GAP_SECONDS:
                return None
        alpha = (scene_time - end) / blend_out
        clip_pose = sample_track_clip_clamped(clip, source, end)
        idle_pose = sample_motion_source(idle_source, scene_time)
        return blend_pose_samples(clip_pose, idle_pose, alpha)
    return None


def pose_samples_compatible(first: PoseSample, second: PoseSample) -> bool:
    return (
        first.profile_name == second.profile_name
        and len(first.local_rotations) == len(second.local_rotations)
    )


def blend_pose_samples(first: PoseSample, second: PoseSample, alpha: float) -> PoseSample:
    alpha = smoothstep(alpha)
    if not pose_samples_compatible(first, second):
        return second if alpha >= 0.5 else first

    root_offset = (
        (1.0 - alpha) * np.asarray(first.root_offset, dtype=np.float32)
        + alpha * np.asarray(second.root_offset, dtype=np.float32)
    ).astype(np.float32)
    local_rotations = [
        quaternion_to_matrix(
            quaternion_slerp(
                matrix_to_quaternion(np.asarray(rotation0, dtype=np.float32)),
                matrix_to_quaternion(np.asarray(rotation1, dtype=np.float32)),
                alpha,
            )
        )
        for rotation0, rotation1 in zip(first.local_rotations, second.local_rotations)
    ]
    return PoseSample(
        profile_name=first.profile_name,
        root_offset=root_offset,
        local_rotations=local_rotations,
    )


def smoothstep(alpha: float) -> float:
    alpha = max(0.0, min(1.0, float(alpha)))
    return alpha * alpha * (3.0 - 2.0 * alpha)


def interpolate_angle_degrees(start: float, end: float, alpha: float) -> float:
    delta = ((end - start + 180.0) % 360.0) - 180.0
    return start + alpha * delta


def segment_mode_for_pair(character: SceneCharacter, first: RootKey, second: RootKey) -> str:
    for segment in character.root_segments:
        if segment.from_id == first.key_id and segment.to_id == second.key_id:
            return segment.mode if segment.mode in {"linear", "curve", "hold"} else "linear"
    return "linear"


def catmull_rom_position(p0: Vec3f, p1: Vec3f, p2: Vec3f, p3: Vec3f, alpha: float) -> Vec3f:
    t2 = alpha * alpha
    t3 = t2 * alpha
    return (
        0.5
        * (
            2.0 * p1
            + (-p0 + p2) * alpha
            + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
            + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
        )
    ).astype(np.float32)


def sample_root_pose(character: SceneCharacter, scene_time: float) -> tuple[Vec3f, float]:
    ensure_root_keys(character)
    ordered = sorted(character.root_keys, key=lambda item: float(item.time))
    if scene_time <= ordered[0].time:
        return ordered[0].position.copy(), float(ordered[0].facing_degrees)
    if scene_time >= ordered[-1].time:
        return ordered[-1].position.copy(), float(ordered[-1].facing_degrees)
    for index, (first, second) in enumerate(zip(ordered[:-1], ordered[1:])):
        if first.time <= scene_time <= second.time:
            if abs(second.time - first.time) < 1e-6:
                return second.position.copy(), float(second.facing_degrees)
            alpha = (scene_time - first.time) / (second.time - first.time)
            mode = segment_mode_for_pair(character, first, second)
            if mode == "hold":
                position = second.position.copy() if alpha >= 1.0 else first.position.copy()
            elif mode == "curve":
                prev = ordered[max(0, index - 1)].position
                next_position = ordered[min(len(ordered) - 1, index + 2)].position
                position = catmull_rom_position(prev, first.position, second.position, next_position, alpha)
            else:
                position = ((1.0 - alpha) * first.position + alpha * second.position).astype(np.float32)
            facing = interpolate_angle_degrees(first.facing_degrees, second.facing_degrees, alpha)
            return position, facing
    return ordered[-1].position.copy(), float(ordered[-1].facing_degrees)


def sample_character_pose(
    character: SceneCharacter,
    scene_time: float,
    motion_library: dict[str, MotionSource],
) -> tuple[PoseSample, Vec3f, float] | None:
    stage_root, facing_degrees = sample_root_pose(character, scene_time)
    ordered = sorted(character.track, key=lambda item: float(item.start))
    for first, second in zip(ordered[:-1], ordered[1:]):
        first_source = motion_library.get(first.clip)
        second_source = motion_library.get(second.clip)
        if first_source is None or second_source is None:
            continue
        window = clip_transition_window(first, second)
        if window is None:
            continue
        window_start, window_end = window
        if window_end <= window_start + 1e-6:
            continue
        if window_start <= scene_time <= window_end:
            alpha = (scene_time - window_start) / (window_end - window_start)
            first_pose = sample_track_clip_clamped(first, first_source, scene_time)
            second_pose = sample_track_clip_clamped(second, second_source, scene_time)
            return blend_pose_samples(first_pose, second_pose, alpha), stage_root, facing_degrees

    idle_source = motion_library.get("Preset: Idle stand") or motion_library.get("Idle Breathing")
    if idle_source is not None:
        for index, clip in enumerate(ordered):
            source = motion_library.get(clip.clip)
            if source is None:
                continue
            pose = sample_idle_transition(
                clip,
                source,
                idle_source,
                scene_time,
                previous_clip=ordered[index - 1] if index > 0 else None,
                next_clip=ordered[index + 1] if index < len(ordered) - 1 else None,
            )
            if pose is not None:
                return pose, stage_root, facing_degrees

    for clip in ordered:
        if clip.clip not in motion_library:
            continue
        end = clip.start + clip.duration
        if clip.start <= scene_time <= end:
            return sample_track_clip(clip, motion_library[clip.clip], scene_time), stage_root, facing_degrees

    if idle_source is None:
        return None
    return sample_motion_source(idle_source, scene_time), stage_root, facing_degrees


def transform_world_pose(
    asset: AssetData,
    local_rotations: list[Mat3f],
    root_offset: Vec3f,
    stage_root: Vec3f,
    facing_degrees: float,
) -> tuple[np.ndarray, np.ndarray]:
    world_rotations, world_positions = forward_kinematics(
        asset.joints,
        local_rotations,
        root_offset,
        asset.topological_order,
    )
    # Scene facing follows the stage editor convention: 0 faces +Y, 90 faces +X.
    # Standard positive Z rotation would turn +Y toward -X, so invert the sign here.
    facing = rotation_z(math.radians(-facing_degrees))
    pivot = np.asarray(asset.joints[0].rest_position, dtype=np.float32)
    stage_origin = np.asarray(stage_root, dtype=np.float32) + pivot
    transformed_positions = ((world_positions - pivot) @ facing.T + stage_origin).astype(np.float32)
    transformed_rotations = np.asarray([facing @ rotation for rotation in world_rotations], dtype=np.float32)
    return transformed_rotations, transformed_positions


def make_path_points(character: SceneCharacter) -> np.ndarray:
    points: list[list[np.ndarray]] = []
    ensure_root_keys(character)
    for first, second in zip(character.root_keys[:-1], character.root_keys[1:]):
        start = np.asarray([first.position[0], first.position[1], 0.015], dtype=np.float32)
        end = np.asarray([second.position[0], second.position[1], 0.015], dtype=np.float32)
        points.append([start, end])
    if not points:
        return np.zeros((1, 2, 3), dtype=np.float32)
    return np.asarray(points, dtype=np.float32)


def create_character_runtime(
    server: viser.ViserServer,
    character: SceneCharacter,
    asset: AssetData,
) -> CharacterRuntime:
    prefix = f"/characters/{character.character_id}"
    part_handles = [
        server.scene.add_mesh_simple(
            f"{prefix}/parts/{part.name}",
            vertices=part.vertices,
            faces=part.faces,
            color=part.color,
            flat_shading=part.flat_shading,
            side=part.side,
        )
        for part in asset.parts
    ]
    skeleton_handle = server.scene.add_line_segments(
        f"{prefix}/skeleton",
        points=np.zeros((max(1, len(asset.bone_edges)), 2, 3), dtype=np.float32),
        colors=(35, 35, 35),
        line_width=3.0,
    )
    path_handle = server.scene.add_line_segments(
        f"{prefix}/path",
        points=make_path_points(character),
        colors=(45, 104, 196),
        line_width=4.0,
    )
    label_handle = server.scene.add_label(
        f"{prefix}/label",
        text=character.label,
        position=(0.0, 0.0, 1.35),
        font_size_mode="screen",
        font_screen_scale=1.0,
        depth_test=False,
        anchor="bottom-center",
    )
    return CharacterRuntime(
        character=character,
        asset=asset,
        part_handles=part_handles,
        skeleton_handle=skeleton_handle,
        path_handle=path_handle,
        label_handle=label_handle,
    )


def remove_character_runtime(runtime: CharacterRuntime) -> None:
    for handle in runtime.part_handles:
        handle.remove()
    if runtime.skeleton_handle is not None:
        runtime.skeleton_handle.remove()
    if runtime.path_handle is not None:
        runtime.path_handle.remove()
    if runtime.label_handle is not None:
        runtime.label_handle.remove()


def update_runtime_visibility(
    runtime: CharacterRuntime,
    *,
    show_blocky: bool,
    show_skeleton: bool,
    show_paths: bool,
) -> None:
    for handle in runtime.part_handles:
        handle.visible = show_blocky
    if runtime.skeleton_handle is not None:
        runtime.skeleton_handle.visible = show_skeleton
    if runtime.path_handle is not None:
        runtime.path_handle.visible = show_paths
    if runtime.label_handle is not None:
        runtime.label_handle.visible = True


def update_character_runtime_pose(
    runtime: CharacterRuntime,
    pose_sample: PoseSample,
    stage_root: Vec3f,
    facing_degrees: float,
    *,
    show_blocky: bool,
    show_skeleton: bool,
    show_paths: bool,
) -> None:
    asset = runtime.asset
    local_rotations = pose_sample_to_asset_local_rotations(asset, pose_sample)
    rotations, positions = transform_world_pose(
        asset,
        local_rotations,
        pose_sample.root_offset,
        stage_root,
        facing_degrees,
    )

    for part, handle in zip(asset.parts, runtime.part_handles):
        joint_index = part.joint_index
        handle.wxyz = matrix_to_quaternion(rotations[joint_index])
        handle.position = positions[joint_index]

    if runtime.skeleton_handle is not None:
        runtime.skeleton_handle.points = np.asarray(
            [[positions[child], positions[parent]] for parent, child in asset.bone_edges],
            dtype=np.float32,
        )
    if runtime.path_handle is not None:
        runtime.path_handle.points = make_path_points(runtime.character)
        runtime.path_handle.visible = show_paths and len(runtime.character.root_keys) > 1
    if runtime.label_handle is not None:
        head_index = asset.joint_lookup.get("head", 0)
        runtime.label_handle.text = runtime.character.label
        runtime.label_handle.position = positions[head_index] + np.asarray([0.0, 0.0, 0.18], dtype=np.float32)

    update_runtime_visibility(
        runtime,
        show_blocky=show_blocky,
        show_skeleton=show_skeleton,
        show_paths=show_paths,
    )


def update_all_character_poses(
    state: EditorState,
    motion_library: dict[str, MotionSource],
    *,
    show_blocky: bool,
    show_skeleton: bool,
    show_paths: bool,
) -> None:
    scene_time = max(0.0, min(float(state.preview_time), float(state.scene.duration)))
    for character in state.scene.characters:
        runtime = state.runtimes.get(character.character_id)
        if runtime is None:
            continue
        sample = sample_character_pose(character, scene_time, motion_library)
        if sample is None:
            identity_pose = PoseSample(
                profile_name=COURSE_BODY_24_PROFILE.name,
                root_offset=np.zeros(3, dtype=np.float32),
                local_rotations=[np.eye(3, dtype=np.float32) for _ in COURSE_BODY_24_PROFILE.joint_names],
            )
            stage_root = np.zeros(3, dtype=np.float32)
            facing_degrees = 0.0
        else:
            identity_pose, stage_root, facing_degrees = sample
        update_character_runtime_pose(
            runtime,
            identity_pose,
            stage_root,
            facing_degrees,
            show_blocky=show_blocky,
            show_skeleton=show_skeleton,
            show_paths=show_paths,
        )


def rebuild_runtimes(
    server: viser.ViserServer,
    state: EditorState,
    asset_sources: dict[str, Path],
) -> None:
    for runtime in list(state.runtimes.values()):
        remove_character_runtime(runtime)
    state.runtimes.clear()
    for character in state.scene.characters:
        if character.proxy_asset not in asset_sources:
            character.proxy_asset = preferred_asset_label(asset_sources)
        asset = load_asset(asset_sources[character.proxy_asset])
        state.runtimes[character.character_id] = create_character_runtime(server, character, asset)
    if state.scene.characters and state.selected_character_id not in state.runtimes:
        state.selected_character_id = state.scene.characters[0].character_id


def scene_root_positions(scene: MotionScene) -> np.ndarray:
    roots: list[np.ndarray] = []
    for character in scene.characters:
        ensure_root_keys(character)
        for root_key in character.root_keys:
            roots.append(np.asarray(root_key.position, dtype=np.float32))
    if not roots:
        return np.zeros((1, 3), dtype=np.float32)
    return np.asarray(roots, dtype=np.float32)


def scene_center_and_radius(scene: MotionScene) -> tuple[np.ndarray, float]:
    roots = scene_root_positions(scene)
    center = roots.mean(axis=0)
    center[2] = 0.8
    horizontal = roots[:, :2] - center[:2]
    radius = max(2.4, float(np.linalg.norm(horizontal, axis=1).max()) + 2.0)
    return center.astype(np.float32), radius


def character_root_at_time(
    scene: MotionScene,
    character_id: str,
    scene_time: float,
) -> np.ndarray | None:
    character = next((item for item in scene.characters if item.character_id == character_id), None)
    if character is None:
        return None
    root_position, _ = sample_root_pose(character, scene_time)
    return root_position


def camera_pose_for_scene(scene: MotionScene, scene_time: float) -> tuple[np.ndarray, np.ndarray]:
    center, radius = scene_center_and_radius(scene)
    height = max(0.4, float(scene.camera.height))
    preset = scene.camera.preset if scene.camera.preset in CAMERA_PRESETS else "slow_orbit"
    look_at = center.copy()
    look_at[2] = max(0.6, height * 0.72)
    target_look_at = camera_target_look_at(scene, scene_time, height)

    if preset == "front_stage":
        position = look_at + np.asarray([0.0, radius, height * 0.85], dtype=np.float32)
    elif preset == "slow_orbit":
        if target_look_at is not None:
            look_at = target_look_at
        duration = max(0.001, float(scene.duration))
        angle = 2.0 * math.pi * (scene_time / duration)
        position = look_at + np.asarray(
            [math.sin(angle) * radius, math.cos(angle) * radius, height * 0.9],
            dtype=np.float32,
        )
    elif preset == "follow_character":
        if target_look_at is not None:
            look_at = target_look_at
        position = look_at + np.asarray([0.0, -2.35, height * 0.55], dtype=np.float32)
    elif preset == "dolly_in":
        if target_look_at is not None:
            look_at = target_look_at
        duration = max(0.001, float(scene.duration))
        alpha = max(0.0, min(1.0, scene_time / duration))
        distance = radius * (1.55 - 0.45 * alpha)
        position = look_at + np.asarray([0.25 * radius, distance, height * 0.85], dtype=np.float32)
    elif preset == "top_down":
        position = center + np.asarray([0.0, 0.001, radius * 1.75], dtype=np.float32)
        look_at = center.copy()
        look_at[2] = 0.0
    else:
        position = look_at + np.asarray([0.45 * radius, 1.15 * radius, height * 0.95], dtype=np.float32)
    return position.astype(np.float32), look_at.astype(np.float32)


def camera_target_look_at(scene: MotionScene, scene_time: float, height: float) -> np.ndarray | None:
    if scene.camera.target == CAMERA_ORIGIN_TARGET:
        return np.asarray([0.0, 0.0, max(0.75, height * 0.72)], dtype=np.float32)
    target = character_root_at_time(scene, scene.camera.target, scene_time)
    if target is None:
        return None
    return target + np.asarray([0.0, 0.0, max(0.75, height * 0.72)], dtype=np.float32)


def apply_camera_preset(camera: viser.CameraHandle, scene: MotionScene, scene_time: float) -> None:
    position, look_at = camera_pose_for_scene(scene, scene_time)
    camera.position = tuple(float(value) for value in position)
    camera.look_at = tuple(float(value) for value in look_at)
    camera.up_direction = (0.0, 0.0, 1.0)
    camera.fov = math.radians(45.0 if scene.camera.preset != "top_down" else 38.0)


def apply_background(server: viser.ViserServer, scene: MotionScene) -> str:
    image = load_background_image(scene.background.image_path)
    if image is not None:
        server.scene.set_background_image(image)
        return f"Loaded {Path(scene.background.image_path).name}"
    server.scene.set_background_image(color_background_image(scene.background.color))
    if scene.background.image_path.strip():
        return "Image path not found; using color"
    return "Using plain color"


def scene_warnings(scene: MotionScene, motion_library: dict[str, MotionSource]) -> list[str]:
    warnings: list[str] = []
    for character in scene.characters:
        ordered = sorted(character.track, key=lambda item: float(item.start))
        for index, clip in enumerate(ordered):
            if clip.clip not in motion_library:
                warnings.append(f"{character.label}: missing clip '{clip.clip}'")
            if clip.start + clip.duration > scene.duration + 1e-6:
                warnings.append(f"{character.label}: clip '{clip.clip}' extends past scene duration")
            if index == 0:
                continue
            previous = ordered[index - 1]
            previous_end = previous.start + previous.duration
            if clip.start < previous_end - 1e-6:
                warnings.append(f"{character.label}: clips overlap near {clip.start:.2f}s")
        ensure_root_keys(character)
        if not character.root_keys:
            warnings.append(f"{character.label}: no root keys")
        for first, second in zip(character.root_keys[:-1], character.root_keys[1:]):
            jump = float(np.linalg.norm(second.position[:2] - first.position[:2]))
            duration = max(1e-6, second.time - first.time)
            if jump / duration > 2.2:
                warnings.append(f"{character.label}: fast root segment near {first.time:.1f}s")
    return warnings[:6]


def main() -> None:
    viewer_dir = Path(__file__).resolve().parent
    project_root = viewer_dir.parent

    parser = argparse.ArgumentParser(description="GF5 multi-character motion scene editor.")
    parser.add_argument(
        "--asset-dir",
        default=str(project_root / "assets" / "blocky"),
        help="Directory containing blocky *.asset.json proxy files.",
    )
    parser.add_argument(
        "--scene",
        default="",
        help="Optional .scene.json file to load at startup.",
    )
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Do not automatically open the local viewer page in a browser.",
    )
    parser.add_argument("--port", type=int, default=8091, help="Port for the local viser server.")
    args = parser.parse_args()

    asset_sources = discover_assets(Path(args.asset_dir).resolve())
    if not asset_sources:
        raise FileNotFoundError(f"No blocky assets found in {args.asset_dir}")
    preset_motion_dir = project_root / "libraries" / "motions"
    motion_library_dir = project_root / "libraries" / "motions" / "custom"
    scene_library_dir = project_root / "libraries" / "scenes"
    video_export_dir = project_root / "exports" / "scene_videos"
    motion_library = discover_motion_library(preset_motion_dir, motion_library_dir)
    default_asset = preferred_asset_label(asset_sources)

    if args.scene:
        initial_scene = scene_from_json(
            json.loads(Path(args.scene).read_text(encoding="utf-8")),
            default_asset,
        )
    else:
        initial_scene = make_default_scene(motion_library, asset_sources)
    state = EditorState(scene=initial_scene)
    if state.scene.characters:
        state.selected_character_id = state.scene.characters[0].character_id

    server = viser.ViserServer(port=args.port)
    server.scene.set_up_direction("+z")
    server.initial_camera.position = (1.4, 3.6, 1.7)
    server.initial_camera.look_at = (0.0, 0.0, 0.8)
    server.initial_camera.up = (0.0, 0.0, 1.0)
    server.initial_camera.fov = math.radians(45.0)
    if not args.no_open_browser:
        webbrowser.open(f"http://localhost:{server.get_port()}", new=2)

    grid_handle = server.scene.add_grid(
        "/stage/grid",
        width=8.0,
        height=8.0,
        plane="xy",
        cell_color=(205, 207, 210),
        section_color=(145, 150, 156),
        cell_size=0.25,
        section_size=1.0,
        plane_opacity=0.0,
    )
    floor_handle = server.scene.add_grid(
        "/stage/floor",
        width=8.0,
        height=8.0,
        plane="xy",
        cell_color=(246, 244, 238),
        section_color=(246, 244, 238),
        cell_thickness=0.0,
        section_thickness=0.0,
        plane_color=(246, 244, 238),
        plane_opacity=0.42,
    )
    background_status = apply_background(server, state.scene)
    rebuild_runtimes(server, state, asset_sources)
    root_key_transform_handle = server.scene.add_transform_controls(
        "/editor/selected_root_key",
        scale=0.28,
        disable_rotations=True,
        line_width=3.0,
        visible=False,
    )

    with server.gui.add_folder("Scene"):
        animate_checkbox = server.gui.add_checkbox("Animate", initial_value=True)
        time_slider = server.gui.add_slider(
            "Time",
            min=0.0,
            max=float(state.scene.duration),
            step=0.01,
            initial_value=0.0,
        )
        duration_number = server.gui.add_number(
            "Duration",
            initial_value=float(state.scene.duration),
            min=0.5,
            step=0.5,
        )
        show_blocky_checkbox = server.gui.add_checkbox("Show Blocky", initial_value=True)
        show_skeleton_checkbox = server.gui.add_checkbox("Show Skeleton", initial_value=True)
        show_paths_checkbox = server.gui.add_checkbox("Show Paths", initial_value=True)
        scene_status_text = server.gui.add_html(format_status_html("Scene", "Ready"))

    with server.gui.add_folder("Character Track"):
        character_dropdown = server.gui.add_dropdown(
            "Character",
            tuple(character.character_id for character in state.scene.characters),
            initial_value=state.selected_character_id,
        )
        character_label_text = server.gui.add_text("Label", initial_value=selected_character(state).label)
        proxy_dropdown = server.gui.add_dropdown(
            "Proxy",
            tuple(asset_sources.keys()),
            initial_value=selected_character(state).proxy_asset,
        )
        avatar_asset_text = server.gui.add_text("Final Avatar", initial_value=selected_character(state).avatar_asset)
        add_character_button = server.gui.add_button("Add Character")
        remove_character_button = server.gui.add_button("Remove Character")

    with server.gui.add_folder("Root Path"):
        root_key_dropdown = server.gui.add_dropdown("Root Key", ("0",), initial_value="0")
        root_key_time_number = server.gui.add_number("Time", initial_value=0.0, min=0.0, step=0.1)
        root_key_x_number = server.gui.add_number("X", initial_value=0.0, step=0.05)
        root_key_y_number = server.gui.add_number("Y", initial_value=0.0, step=0.05)
        root_key_z_number = server.gui.add_number("Z", initial_value=0.0, step=0.05)
        root_key_facing_number = server.gui.add_number("Facing", initial_value=0.0, step=5.0)
        add_root_key_button = server.gui.add_button("Add Root Key At Current Time")
        remove_root_key_button = server.gui.add_button("Remove Root Key")

    with server.gui.add_folder("Clip Sequence"):
        clip_block_dropdown = server.gui.add_dropdown("Block", ("0",), initial_value="0")
        clip_source_dropdown = server.gui.add_dropdown(
            "Clip",
            motion_dropdown_options(
                motion_library,
                selected_clip(state).clip if selected_clip(state) is not None else None,
            ),
            initial_value=(
                selected_clip(state).clip
                if selected_clip(state) is not None
                else first_visible_motion_label(motion_library)
            ),
        )
        clip_start_number = server.gui.add_number("Start", initial_value=0.0, min=0.0, step=0.1)
        clip_duration_number = server.gui.add_number("Duration", initial_value=4.0, min=0.1, step=0.1)
        trim_start_number = server.gui.add_number("Trim Start", initial_value=0.0, min=0.0, step=0.1)
        trim_end_number = server.gui.add_number("Trim End", initial_value=0.0, min=0.0, step=0.1)
        root_mode_dropdown = server.gui.add_dropdown(
            "Root Mode",
            ("path", "native"),
            initial_value="path",
        )
        add_clip_button = server.gui.add_button("Append Clip")
        insert_clip_button = server.gui.add_button("Insert After")
        duplicate_clip_button = server.gui.add_button("Duplicate Clip")
        move_clip_earlier_button = server.gui.add_button("Move Earlier")
        move_clip_later_button = server.gui.add_button("Move Later")
        remove_clip_button = server.gui.add_button("Remove Clip")

    with server.gui.add_folder("Camera And Background"):
        camera_preset_dropdown = server.gui.add_dropdown(
            "Camera",
            CAMERA_PRESETS,
            initial_value=state.scene.camera.preset,
        )
        camera_target_dropdown = server.gui.add_dropdown(
            "Follow Target",
            (CAMERA_ORIGIN_TARGET,) + tuple(character.character_id for character in state.scene.characters),
            initial_value=state.scene.camera.target or CAMERA_ORIGIN_TARGET,
        )
        camera_height_number = server.gui.add_number(
            "Camera Height",
            initial_value=float(state.scene.camera.height),
            min=0.4,
            step=0.1,
        )
        background_color_text = server.gui.add_text("Background Color", initial_value=state.scene.background.color)
        background_image_text = server.gui.add_text("Background Image", initial_value=state.scene.background.image_path)
        show_grid_checkbox = server.gui.add_checkbox("Show Grid", initial_value=state.scene.background.show_grid)
        show_floor_checkbox = server.gui.add_checkbox("Show Floor", initial_value=state.scene.background.show_floor)
        background_status_text = server.gui.add_html(format_status_html("Background", background_status))

    with server.gui.add_folder("Save And Export"):
        scene_name_text = server.gui.add_text("Scene Name", initial_value=DEFAULT_SCENE_STEM)
        save_scene_button = server.gui.add_button("Save Scene")
        scene_library_dropdown = server.gui.add_dropdown(
            "Saved Scenes",
            tuple(discover_scene_library(scene_library_dir).keys()) or ("None",),
            initial_value=(next(iter(discover_scene_library(scene_library_dir))) if discover_scene_library(scene_library_dir) else "None"),
        )
        load_scene_button = server.gui.add_button("Load Scene")
        export_fps_number = server.gui.add_number("FPS", initial_value=state.scene.export.fps, min=1, max=EXPORT_MAX_FPS, step=1)
        export_width_number = server.gui.add_number("Width", initial_value=state.scene.export.width, min=2, max=EXPORT_MAX_WIDTH, step=2)
        export_height_number = server.gui.add_number("Height", initial_value=state.scene.export.height, min=2, max=EXPORT_MAX_HEIGHT, step=2)
        export_video_button = server.gui.add_button("Export Scene Video")
        export_status_text = server.gui.add_html(format_status_html("Export", "No export yet"))

    def set_scene_status(message: str) -> None:
        warnings = scene_warnings(state.scene, motion_library)
        if warnings:
            message = f"{message} | " + " ; ".join(warnings)
        scene_status_text.content = format_status_html("Scene", message)

    def refresh_character_dropdowns() -> None:
        character_options = tuple(character.character_id for character in state.scene.characters) or ("None",)
        camera_options = (CAMERA_ORIGIN_TARGET,) + tuple(
            character.character_id for character in state.scene.characters
        )
        character_dropdown.options = character_options
        camera_target_dropdown.options = camera_options
        if state.selected_character_id not in character_options:
            state.selected_character_id = character_options[0]
        character_dropdown.value = state.selected_character_id
        if state.scene.camera.target not in camera_options:
            state.scene.camera.target = CAMERA_ORIGIN_TARGET
        camera_target_dropdown.value = state.scene.camera.target

    def refresh_scene_library_dropdown() -> None:
        scenes = discover_scene_library(scene_library_dir)
        scene_library_dropdown.options = tuple(scenes.keys()) or ("None",)
        scene_library_dropdown.value = next(iter(scenes)) if scenes else "None"

    def refresh_clip_dropdown() -> None:
        character = selected_character(state)
        if character is None or not character.track:
            clip_block_dropdown.options = ("None",)
            clip_block_dropdown.value = "None"
            remove_clip_button.disabled = True
            return
        character.track.sort(key=lambda item: float(item.start))
        options = tuple(
            f"{index}: {clip.clip} @ {clip.start:.1f}s"
            for index, clip in enumerate(character.track)
        )
        state.selected_clip_index = max(0, min(state.selected_clip_index, len(options) - 1))
        clip_block_dropdown.options = options
        clip_block_dropdown.value = options[state.selected_clip_index]
        remove_clip_button.disabled = False

    def refresh_root_key_dropdown() -> None:
        character = selected_character(state)
        if character is None:
            root_key_dropdown.options = ("None",)
            root_key_dropdown.value = "None"
            remove_root_key_button.disabled = True
            root_key_transform_handle.visible = False
            return
        ensure_root_keys(character)
        options = tuple(
            f"{index}: t={root_key.time:.1f}s ({root_key.position[0]:.2f}, {root_key.position[1]:.2f})"
            for index, root_key in enumerate(character.root_keys)
        )
        state.selected_root_key_index = max(0, min(state.selected_root_key_index, len(options) - 1))
        root_key_dropdown.options = options
        root_key_dropdown.value = options[state.selected_root_key_index]
        remove_root_key_button.disabled = len(character.root_keys) <= 1

    def sync_controls_from_state() -> None:
        state.suppress_callbacks = True
        try:
            duration_number.value = float(state.scene.duration)
            time_slider.max = float(state.scene.duration)
            time_slider.value = max(0.0, min(float(state.preview_time), float(state.scene.duration)))
            show_grid_checkbox.value = bool(state.scene.background.show_grid)
            show_floor_checkbox.value = bool(state.scene.background.show_floor)
            camera_preset_dropdown.value = state.scene.camera.preset
            camera_height_number.value = float(state.scene.camera.height)
            export_fps_number.value = int(state.scene.export.fps)
            export_width_number.value = int(state.scene.export.width)
            export_height_number.value = int(state.scene.export.height)
            background_color_text.value = state.scene.background.color
            background_image_text.value = state.scene.background.image_path
            grid_handle.visible = state.scene.background.show_grid
            floor_handle.visible = state.scene.background.show_floor

            refresh_character_dropdowns()
            character = selected_character(state)
            if character is not None:
                ensure_root_keys(character)
                character_label_text.value = character.label
                proxy_dropdown.value = character.proxy_asset
                avatar_asset_text.value = character.avatar_asset

            refresh_root_key_dropdown()
            root_key = selected_root_key(state)
            if root_key is not None:
                root_key_time_number.value = float(root_key.time)
                root_key_x_number.value = float(root_key.position[0])
                root_key_y_number.value = float(root_key.position[1])
                root_key_z_number.value = float(root_key.position[2])
                root_key_facing_number.value = float(root_key.facing_degrees)
                root_key_transform_handle.visible = True
                root_key_transform_handle.position = root_key.position
            else:
                root_key_transform_handle.visible = False

            refresh_clip_dropdown()
            clip = selected_clip(state)
            if clip is not None:
                clip_source_dropdown.options = motion_dropdown_options(motion_library, clip.clip)
                clip_source_dropdown.value = (
                    clip.clip if clip.clip in motion_library else first_visible_motion_label(motion_library)
                )
                clip_start_number.value = float(clip.start)
                clip_duration_number.value = float(clip.duration)
                trim_start_number.value = float(clip.trim_start)
                trim_end_number.value = float(clip.trim_end or 0.0)
                root_mode_dropdown.value = clip.root_mode if clip.root_mode in ("path", "native") else "path"
        finally:
            state.suppress_callbacks = False

    def redraw_scene(message: str = "Updated") -> None:
        update_all_character_poses(
            state,
            motion_library,
            show_blocky=show_blocky_checkbox.value,
            show_skeleton=show_skeleton_checkbox.value,
            show_paths=show_paths_checkbox.value,
        )
        set_scene_status(message)

    def update_selected_clip_from_controls() -> None:
        if state.suppress_callbacks:
            return
        clip = selected_clip(state)
        if clip is None:
            return
        clip.clip = str(clip_source_dropdown.value)
        clip.start = max(0.0, float(clip_start_number.value))
        clip.duration = max(0.1, float(clip_duration_number.value))
        clip.trim_start = max(0.0, float(trim_start_number.value))
        trim_end = max(0.0, float(trim_end_number.value))
        clip.trim_end = None if trim_end <= 0.0 else trim_end
        clip.root_mode = str(root_mode_dropdown.value)
        character = selected_character(state)
        if character is not None:
            character.track.sort(key=lambda item: float(item.start))
            for index, candidate in enumerate(character.track):
                if candidate is clip:
                    state.selected_clip_index = index
                    break
        refresh_clip_dropdown()
        redraw_scene("Clip updated")

    def update_selected_root_key_from_controls() -> None:
        if state.suppress_callbacks:
            return
        root_key = selected_root_key(state)
        if root_key is None:
            return
        root_key.time = max(0.0, min(float(state.scene.duration), float(root_key_time_number.value)))
        root_key.position = np.asarray(
            [
                float(root_key_x_number.value),
                float(root_key_y_number.value),
                float(root_key_z_number.value),
            ],
            dtype=np.float32,
        )
        root_key.facing_degrees = float(root_key_facing_number.value)
        character = selected_character(state)
        if character is not None:
            character.root_keys.sort(key=lambda item: float(item.time))
            for index, candidate in enumerate(character.root_keys):
                if candidate is root_key:
                    state.selected_root_key_index = index
                    break
        root_key_transform_handle.position = root_key.position
        refresh_root_key_dropdown()
        redraw_scene("Root key updated")

    @time_slider.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        state.preview_time = float(time_slider.value)
        redraw_scene("Preview updated")

    @duration_number.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        state.scene.duration = max(0.5, float(duration_number.value))
        sync_controls_from_state()
        redraw_scene("Duration updated")

    @show_blocky_checkbox.on_update
    @show_skeleton_checkbox.on_update
    @show_paths_checkbox.on_update
    def _(_) -> None:
        redraw_scene("Visibility updated")

    @character_dropdown.on_update
    def _(_) -> None:
        if state.suppress_callbacks or character_dropdown.value == "None":
            return
        state.selected_character_id = str(character_dropdown.value)
        state.selected_clip_index = 0
        state.selected_root_key_index = 0
        sync_controls_from_state()
        redraw_scene("Character selected")

    @character_label_text.on_update
    @avatar_asset_text.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        character = selected_character(state)
        if character is None:
            return
        character.label = str(character_label_text.value)
        character.avatar_asset = str(avatar_asset_text.value)
        redraw_scene("Character updated")

    @proxy_dropdown.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        character = selected_character(state)
        if character is None:
            return
        character.proxy_asset = str(proxy_dropdown.value)
        rebuild_runtimes(server, state, asset_sources)
        redraw_scene("Proxy changed")

    @add_character_button.on_click
    def _(_) -> None:
        new_id = unique_character_id(state.scene, f"character_{len(state.scene.characters) + 1}")
        default_clip = first_visible_motion_label(motion_library)
        default_source = motion_library[default_clip]
        state.scene.characters.append(
            SceneCharacter(
                character_id=new_id,
                label=new_id.replace("_", " ").title(),
                proxy_asset=preferred_asset_label(asset_sources),
                track=[
                    TrackClip(
                        clip=default_clip,
                        start=0.0,
                        duration=min(4.0, float(state.scene.duration)),
                        root_mode=default_source.default_root_mode,
                    )
                ],
                root_keys=[
                    RootKey(time=0.0, position=np.zeros(3, dtype=np.float32)),
                    RootKey(
                        time=float(state.scene.duration),
                        position=np.zeros(3, dtype=np.float32),
                    ),
                ],
            )
        )
        state.selected_character_id = new_id
        state.selected_clip_index = 0
        state.selected_root_key_index = 0
        rebuild_runtimes(server, state, asset_sources)
        sync_controls_from_state()
        redraw_scene("Character added")

    @remove_character_button.on_click
    def _(_) -> None:
        if len(state.scene.characters) <= 1:
            set_scene_status("Keep at least one character")
            return
        character = selected_character(state)
        if character is None:
            return
        state.scene.characters = [
            item for item in state.scene.characters if item.character_id != character.character_id
        ]
        state.selected_character_id = state.scene.characters[0].character_id
        state.selected_clip_index = 0
        state.selected_root_key_index = 0
        rebuild_runtimes(server, state, asset_sources)
        sync_controls_from_state()
        redraw_scene("Character removed")

    @root_key_dropdown.on_update
    def _(_) -> None:
        if state.suppress_callbacks or root_key_dropdown.value == "None":
            return
        state.selected_root_key_index = int(str(root_key_dropdown.value).split(":", 1)[0])
        sync_controls_from_state()
        redraw_scene("Root key selected")

    @root_key_time_number.on_update
    @root_key_x_number.on_update
    @root_key_y_number.on_update
    @root_key_z_number.on_update
    @root_key_facing_number.on_update
    def _(_) -> None:
        update_selected_root_key_from_controls()

    @add_root_key_button.on_click
    def _(_) -> None:
        character = selected_character(state)
        if character is None:
            return
        root_position, facing = sample_root_pose(character, float(state.preview_time))
        character.root_keys.append(
            RootKey(
                time=float(state.preview_time),
                position=root_position.copy(),
                facing_degrees=facing,
            )
        )
        character.root_keys.sort(key=lambda item: float(item.time))
        state.selected_root_key_index = min(
            range(len(character.root_keys)),
            key=lambda index: abs(character.root_keys[index].time - state.preview_time),
        )
        sync_controls_from_state()
        redraw_scene("Root key added")

    @remove_root_key_button.on_click
    def _(_) -> None:
        character = selected_character(state)
        if character is None:
            return
        ensure_root_keys(character)
        if len(character.root_keys) <= 1:
            set_scene_status("Keep at least one root key")
            return
        character.root_keys.pop(state.selected_root_key_index)
        state.selected_root_key_index = max(0, state.selected_root_key_index - 1)
        sync_controls_from_state()
        redraw_scene("Root key removed")

    @root_key_transform_handle.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        root_key = selected_root_key(state)
        if root_key is None:
            return
        root_key.position = np.asarray(root_key_transform_handle.position, dtype=np.float32)
        state.suppress_callbacks = True
        try:
            root_key_x_number.value = float(root_key.position[0])
            root_key_y_number.value = float(root_key.position[1])
            root_key_z_number.value = float(root_key.position[2])
            refresh_root_key_dropdown()
        finally:
            state.suppress_callbacks = False
        redraw_scene("Root key dragged")

    @clip_block_dropdown.on_update
    def _(_) -> None:
        if state.suppress_callbacks or clip_block_dropdown.value == "None":
            return
        state.selected_clip_index = int(str(clip_block_dropdown.value).split(":", 1)[0])
        sync_controls_from_state()
        redraw_scene("Clip selected")

    @clip_source_dropdown.on_update
    @clip_start_number.on_update
    @clip_duration_number.on_update
    @trim_start_number.on_update
    @trim_end_number.on_update
    @root_mode_dropdown.on_update
    def _(_) -> None:
        update_selected_clip_from_controls()

    @add_clip_button.on_click
    def _(_) -> None:
        character = selected_character(state)
        if character is None:
            return
        clip_label = str(clip_source_dropdown.value)
        if character.track:
            previous = max(character.track, key=lambda item: item.start + item.duration)
            start = min(float(state.scene.duration), previous.start + previous.duration)
        else:
            start = 0.0
        character.track.append(
            TrackClip(
                clip=clip_label,
                start=start,
                duration=min(4.0, max(0.5, float(state.scene.duration) - start)),
                root_mode=motion_library[clip_label].default_root_mode,
            )
        )
        state.selected_clip_index = len(character.track) - 1
        sync_controls_from_state()
        redraw_scene("Clip added")

    @insert_clip_button.on_click
    def _(_) -> None:
        character = selected_character(state)
        current = selected_clip(state)
        if character is None:
            return
        if current is None:
            insert_start = 0.0
        else:
            insert_start = min(float(state.scene.duration), current.start + current.duration)
        character.track.append(
            TrackClip(
                clip=str(clip_source_dropdown.value),
                start=insert_start,
                duration=min(4.0, max(0.5, float(state.scene.duration) - insert_start)),
                root_mode=motion_library[str(clip_source_dropdown.value)].default_root_mode,
            )
        )
        character.track.sort(key=lambda item: float(item.start))
        state.selected_clip_index = min(
            range(len(character.track)),
            key=lambda index: abs(character.track[index].start - insert_start),
        )
        sync_controls_from_state()
        redraw_scene("Clip inserted")

    @duplicate_clip_button.on_click
    def _(_) -> None:
        character = selected_character(state)
        clip = selected_clip(state)
        if character is None or clip is None:
            return
        duplicate = TrackClip(
            clip=clip.clip,
            start=min(float(state.scene.duration), clip.start + clip.duration),
            duration=clip.duration,
            trim_start=clip.trim_start,
            trim_end=clip.trim_end,
            root_mode=clip.root_mode,
            blend_in=clip.blend_in,
            blend_out=clip.blend_out,
        )
        character.track.append(duplicate)
        character.track.sort(key=lambda item: float(item.start))
        state.selected_clip_index = next(
            index for index, candidate in enumerate(character.track) if candidate is duplicate
        )
        sync_controls_from_state()
        redraw_scene("Clip duplicated")

    @move_clip_earlier_button.on_click
    def _(_) -> None:
        clip = selected_clip(state)
        if clip is None:
            return
        clip.start = max(0.0, clip.start - 0.5)
        sync_controls_from_state()
        redraw_scene("Clip moved earlier")

    @move_clip_later_button.on_click
    def _(_) -> None:
        clip = selected_clip(state)
        if clip is None:
            return
        clip.start = min(float(state.scene.duration), clip.start + 0.5)
        sync_controls_from_state()
        redraw_scene("Clip moved later")

    @remove_clip_button.on_click
    def _(_) -> None:
        character = selected_character(state)
        if character is None or not character.track:
            return
        character.track.pop(state.selected_clip_index)
        state.selected_clip_index = max(0, state.selected_clip_index - 1)
        sync_controls_from_state()
        redraw_scene("Clip removed")

    @camera_preset_dropdown.on_update
    @camera_target_dropdown.on_update
    @camera_height_number.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        state.scene.camera.preset = str(camera_preset_dropdown.value)
        state.scene.camera.target = str(camera_target_dropdown.value)
        state.scene.camera.height = float(camera_height_number.value)
        redraw_scene("Camera updated")

    @background_color_text.on_update
    @background_image_text.on_update
    @show_grid_checkbox.on_update
    @show_floor_checkbox.on_update
    def _(_) -> None:
        if state.suppress_callbacks:
            return
        state.scene.background.color = str(background_color_text.value)
        state.scene.background.image_path = str(background_image_text.value)
        state.scene.background.show_grid = bool(show_grid_checkbox.value)
        state.scene.background.show_floor = bool(show_floor_checkbox.value)
        grid_handle.visible = state.scene.background.show_grid
        floor_handle.visible = state.scene.background.show_floor
        background_status_text.content = format_status_html("Background", apply_background(server, state.scene))
        redraw_scene("Background updated")

    @save_scene_button.on_click
    def _(_) -> None:
        scene_library_dir.mkdir(parents=True, exist_ok=True)
        stem = sanitize_id(str(scene_name_text.value), DEFAULT_SCENE_STEM)
        path = scene_library_dir / f"{stem}.scene.json"
        suffix = 2
        while path.exists():
            path = scene_library_dir / f"{stem}_{suffix}.scene.json"
            suffix += 1
        path.write_text(json.dumps(scene_to_json(state.scene), indent=2), encoding="utf-8")
        refresh_scene_library_dropdown()
        export_status_text.content = format_status_html("Save", f"Saved {path.name}")

    @load_scene_button.on_click
    def _(_) -> None:
        scenes = discover_scene_library(scene_library_dir)
        if scene_library_dropdown.value not in scenes:
            export_status_text.content = format_status_html("Load", "No saved scene selected")
            return
        try:
            state.scene = scene_from_json(
                json.loads(scenes[str(scene_library_dropdown.value)].read_text(encoding="utf-8")),
                default_asset,
            )
            state.selected_character_id = state.scene.characters[0].character_id
            state.selected_clip_index = 0
            state.selected_root_key_index = 0
            background_status_text.content = format_status_html("Background", apply_background(server, state.scene))
            rebuild_runtimes(server, state, asset_sources)
            sync_controls_from_state()
            redraw_scene("Scene loaded")
        except Exception as exc:
            export_status_text.content = format_status_html("Load", f"Failed: {exc}")
            traceback.print_exc()

    @export_video_button.on_click
    def _(event: Any) -> None:
        if state.is_exporting:
            return
        if event.client is None:
            export_status_text.content = format_status_html("Export", "Run export from an open browser client")
            return
        fps = max(1, int(round(float(export_fps_number.value))))
        requested_width = int(round(float(export_width_number.value)))
        requested_height = int(round(float(export_height_number.value)))
        state.scene.export = normalize_export_settings(
            {"fps": fps, "width": requested_width, "height": requested_height}
        )
        fps = state.scene.export.fps
        requested_width = state.scene.export.width
        requested_height = state.scene.export.height
        max_width = int(getattr(event.client.camera, "image_width", requested_width))
        max_height = int(getattr(event.client.camera, "image_height", requested_height))
        width, height = normalize_video_size(
            min(requested_width, max_width),
            min(requested_height, max_height),
        )
        frame_count = max(2, int(round(float(state.scene.duration) * fps)) + 1)
        frame_times = np.linspace(0.0, float(state.scene.duration), frame_count, endpoint=True)
        state.is_exporting = True
        export_video_button.disabled = True
        previous_time = state.preview_time
        previous_camera = (
            tuple(event.client.camera.position),
            tuple(event.client.camera.look_at),
            tuple(event.client.camera.up_direction),
            float(event.client.camera.fov),
        )
        try:
            frames: list[np.ndarray] = []
            for frame_index, frame_time in enumerate(frame_times):
                state.preview_time = float(frame_time)
                update_all_character_poses(
                    state,
                    motion_library,
                    show_blocky=show_blocky_checkbox.value,
                    show_skeleton=show_skeleton_checkbox.value,
                    show_paths=show_paths_checkbox.value,
                )
                apply_camera_preset(event.client.camera, state.scene, float(frame_time))
                event.client.flush()
                export_status_text.content = format_status_html(
                    "Export",
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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = video_export_dir / f"motion_scene_{timestamp}.mp4"
            export_status_text.content = format_status_html("Export", "Encoding MP4")
            write_mp4_with_ffmpeg(frames, path, fps)
            export_status_text.content = format_status_html("Export", f"Saved {path.name}")
        except Exception as exc:
            export_status_text.content = format_status_html("Export", f"Failed: {exc}")
            traceback.print_exc()
        finally:
            state.preview_time = previous_time
            time_slider.value = max(0.0, min(previous_time, float(state.scene.duration)))
            update_all_character_poses(
                state,
                motion_library,
                show_blocky=show_blocky_checkbox.value,
                show_skeleton=show_skeleton_checkbox.value,
                show_paths=show_paths_checkbox.value,
            )
            (
                event.client.camera.position,
                event.client.camera.look_at,
                event.client.camera.up_direction,
                event.client.camera.fov,
            ) = previous_camera
            state.is_exporting = False
            export_video_button.disabled = False

    sync_controls_from_state()
    redraw_scene("Ready")

    last_wall_time = time.time()
    while True:
        now = time.time()
        dt = now - last_wall_time
        last_wall_time = now
        if animate_checkbox.value and not state.is_exporting:
            state.preview_time = math.fmod(state.preview_time + dt, max(0.001, float(state.scene.duration)))
            state.suppress_callbacks = True
            time_slider.value = state.preview_time
            state.suppress_callbacks = False
            update_all_character_poses(
                state,
                motion_library,
                show_blocky=show_blocky_checkbox.value,
                show_skeleton=show_skeleton_checkbox.value,
                show_paths=show_paths_checkbox.value,
            )
        time.sleep(1.0 / 30.0)


if __name__ == "__main__":
    main()
