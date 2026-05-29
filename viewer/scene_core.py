from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCENE_FORMAT = "gf5_motion_scene"
SCENE_VERSION = 3
DEFAULT_SCENE_STEM = "group_greeting_scene"
PREFERRED_PROXY_ASSET = "SMPL-24 Proxy"
DEFAULT_CLIP_BLEND_SECONDS = 0.45
CAMERA_ORIGIN_TARGET = "__origin__"
EXPORT_MAX_FPS = 24
EXPORT_MAX_WIDTH = 1280
EXPORT_MAX_HEIGHT = 720
CHARACTER_COLOR_PRESETS = (
    "#2f7f7b",
    "#3f7db8",
    "#4e68b8",
    "#2f91c2",
    "#d6a72f",
    "#a86438",
    "#d88c2d",
    "#c04848",
    "#7d6aa8",
    "#5d8749",
    "#2f9b72",
    "#b85b71",
    "#56656f",
)
BUILT_IN_MOTIONS = {
    "Idle Breathing": {
        "label": "Idle Breathing",
        "kind": "idle",
        "duration": 3.0,
        "tags": ["idle", "procedural"],
        "category": "standing_gesture",
        "category_label": "Standing / Gesture",
        "root_contract": "spot",
        "default_root_mode": "path",
        "loopable": True,
        "library_visible": False,
    },
    "Walk": {
        "label": "Walk",
        "kind": "built_in",
        "duration": 4.0,
        "tags": ["walk", "built-in"],
        "category": "travel_loop",
        "category_label": "Travel Loops",
        "root_contract": "scene_path",
        "default_root_mode": "path",
        "loopable": True,
        "library_visible": False,
    },
    "Wave": {
        "label": "Wave",
        "kind": "built_in",
        "duration": 4.0,
        "tags": ["wave", "built-in"],
        "category": "standing_gesture",
        "category_label": "Standing / Gesture",
        "root_contract": "spot",
        "default_root_mode": "path",
        "loopable": False,
        "library_visible": False,
    },
}


def sanitize_id(value: str, default: str = "item") -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or default


def safe_scene_stem(value: str) -> str:
    return sanitize_id(value, DEFAULT_SCENE_STEM)


def default_proxy_asset(proxy_assets: list[str]) -> str:
    if PREFERRED_PROXY_ASSET in proxy_assets:
        return PREFERRED_PROXY_ASSET
    return proxy_assets[0] if proxy_assets else PREFERRED_PROXY_ASSET


def normalize_character_color(value: Any, index: int) -> str:
    text = str(value or "").strip().lower()
    for color in CHARACTER_COLOR_PRESETS:
        if text == color.lower():
            return color
    return CHARACTER_COLOR_PRESETS[index % len(CHARACTER_COLOR_PRESETS)]


def project_root_from_viewer_file(file_path: str | Path) -> Path:
    return Path(file_path).resolve().parent.parent


def discover_proxy_assets(asset_dir: Path) -> list[str]:
    assets: list[str] = []
    for path in sorted(asset_dir.glob("*.asset.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("asset_format") == "gf5_rigid_character":
            assets.append(str(raw.get("name", path.stem)))
    return [default_proxy_asset(assets)]


def load_proxy_asset_previews(asset_dir: Path) -> dict[str, dict[str, Any]]:
    previews: dict[str, dict[str, Any]] = {}
    for path in sorted(asset_dir.glob("*.asset.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("asset_format") != "gf5_rigid_character":
            continue
        name = str(raw.get("name", path.stem))
        skeleton = raw.get("skeleton", {})
        joints = skeleton.get("joints", []) if isinstance(skeleton, dict) else []
        parts = raw.get("rigid_parts", [])
        if not isinstance(joints, list) or not isinstance(parts, list):
            continue
        previews[name] = {
            "joints": [
                {
                    "name": str(joint.get("name", "")),
                    "parent": int(joint.get("parent", -1)),
                    "translation": joint.get("translation", [0.0, 0.0, 0.0]),
                }
                for joint in joints
                if isinstance(joint, dict)
            ],
            "parts": [
                {
                    "name": str(part.get("name", "")),
                    "joint": str(part.get("joint", "")),
                    "vertices": part.get("vertices", []),
                    "faces": part.get("faces", []),
                    "color": part.get("color", [180, 180, 180]),
                }
                for part in parts
                if isinstance(part, dict)
            ],
        }
    return previews


def valid_avatar_root(path: Path) -> bool:
    output_dir = path / "outputs"
    animation_mesh = output_dir / "animation_lowres.obj"
    weights = output_dir / "animation_lowres_skinning_weights.npz"
    smplx_mesh = output_dir / "smplx_mesh.obj"
    return output_dir.is_dir() and animation_mesh.exists() and weights.exists() and smplx_mesh.exists()


def infer_avatar_label(path: Path) -> str:
    name = path.name
    if name == "output" and path.parent.name:
        name = path.parent.name
    if name == "outputs" and path.parent.name:
        name = path.parent.name
    return name.replace("_", " ").replace("-", " ").strip() or "Custom avatar"


def infer_smpl_avatar_label(model_path: Path) -> str:
    stem = model_path.stem.lower()
    if "neutral" in stem:
        return "SMPL: Neutral"
    if "_f_" in stem or "female" in stem:
        return "SMPL: Female"
    if "_m_" in stem or "male" in stem:
        return "SMPL: Male"
    return f"SMPL: {model_path.stem}"


def natural_sort_key(text: str) -> tuple[Any, ...]:
    parts: list[Any] = []
    for part in re.split(r"(\d+)", text.casefold()):
        if not part:
            continue
        parts.append((0, int(part)) if part.isdigit() else (1, part))
    return tuple(parts)


def iter_avatar_roots(search_dir: Path) -> list[Path]:
    if not search_dir.exists():
        return []
    candidates = [search_dir]
    if search_dir.is_dir():
        candidates.extend(path.parent for path in sorted(search_dir.rglob("outputs")) if path.is_dir())
        candidates.extend(path / "output" for path in sorted(search_dir.iterdir()) if path.is_dir())
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not valid_avatar_root(resolved):
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def discover_avatar_assets(project_root: Path) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    labels: set[str] = set()

    def add_asset(label: str, path: Path, kind: str) -> None:
        display_label = label
        base = display_label
        suffix = 2
        while display_label in labels:
            display_label = f"{base} ({suffix})"
            suffix += 1
        labels.add(display_label)
        assets.append({"label": display_label, "path": str(path), "kind": kind})

    for path in sorted((project_root / "assets" / "blocky").glob("*.asset.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("asset_format") != "gf5_rigid_character":
            continue
        add_asset(f"Blocky: {raw.get('name', path.stem)}", path, "blocky")

    for path in sorted((project_root / "assets" / "smpl" / "models").glob("*.pkl")):
        if "basicmodel" not in path.stem.lower() and "smpl" not in path.stem.lower():
            continue
        add_asset(infer_smpl_avatar_label(path), path, "smpl")

    search_dirs = [
        project_root / ".viewer_imports" / "avatars",
        project_root / "libraries" / "avatars",
    ]
    for search_dir in search_dirs:
        for root in iter_avatar_roots(search_dir):
            add_asset(f"UP2You: {infer_avatar_label(root)}", root, "up2you")
    return sorted(assets, key=lambda item: (natural_sort_key(item["label"]), item["path"]))


def load_motion_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if raw.get("format") != "gf5_keyframed_motion":
        return None
    keyframes = raw.get("keyframes")
    if not isinstance(keyframes, list) or not keyframes:
        return None
    return raw


def motion_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_name": str(payload.get("profile_name", "")),
        "joint_order": payload.get("joint_order", []),
        "duration": max(0.001, float(payload.get("duration_sec", 4.0))),
        "keyframes": [
            {
                "time_sec": float(keyframe.get("time_sec", 0.0)),
                "root_offset": keyframe.get("root_offset", [0.0, 0.0, 0.0]),
                "local_rotation_matrices": keyframe.get("local_rotation_matrices", []),
            }
            for keyframe in payload.get("keyframes", [])
            if isinstance(keyframe, dict)
        ],
    }


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


def existing_motion_duplicate_keys(motions: dict[str, dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for motion in motions.values():
        keys.update(
            motion_duplicate_keys(
                str(motion.get("name") or motion.get("label") or ""),
                str(motion.get("prompt") or ""),
            )
        )
    return keys


def add_motion_dir(
    motions: dict[str, dict[str, Any]],
    motion_dir: Path,
    *,
    label_prefix: str,
    kind: str,
) -> None:
    if not motion_dir.exists():
        return
    for path in motion_paths_for_dir(motion_dir):
        payload = load_motion_payload(path)
        if payload is None:
            continue
        if payload.get("library_visible") is False:
            continue
        name = str(payload.get("name", path.stem))
        label = f"{label_prefix}: {name}"
        suffix = 2
        while label in motions:
            label = f"{label_prefix}: {name} ({suffix})"
            suffix += 1
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        prompt = str(payload.get("source_prompt", ""))
        if not prompt and isinstance(source, dict):
            prompt = str(source.get("prompt", ""))
        source_class = payload_string(payload, "source_class", "")
        if (
            kind == "custom"
            and source_class != "hy_motion_import"
            and motion_duplicate_keys(name, prompt) & existing_motion_duplicate_keys(motions)
        ):
            continue
        tags = payload.get("tags")
        if not isinstance(tags, list):
            tags = infer_motion_tags(name, prompt)
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
        motions[label] = {
            "label": label,
            "kind": kind,
            "duration": max(0.001, float(payload.get("duration_sec", 4.0))),
            "path": str(path),
            "name": name,
            "prompt": prompt,
            "tags": [str(tag) for tag in tags],
            "category": category,
            "category_label": category_label,
            "root_contract": root_contract,
            "default_root_mode": default_root_mode,
            "loopable": bool(payload.get("loopable", False)),
            "source": payload_string(payload, "source", ""),
            "source_class": source_class,
            "library_visible": bool(payload.get("library_visible", True)),
            "preview": motion_preview_payload(payload),
        }


def discover_motion_library(project_root: Path) -> list[dict[str, Any]]:
    motions: dict[str, dict[str, Any]] = {key: value.copy() for key, value in BUILT_IN_MOTIONS.items()}
    motion_root = project_root / "libraries" / "motions"
    add_motion_dir(
        motions,
        motion_root,
        label_prefix="Preset",
        kind="preset",
    )
    add_motion_dir(
        motions,
        motion_root / "custom",
        label_prefix="Custom",
        kind="custom",
    )
    return list(motions.values())


def infer_motion_tags(name: str, prompt: str) -> list[str]:
    text = f"{name} {prompt}".lower()
    tags: list[str] = []
    for tag in (
        "walk",
        "wave",
        "turn",
        "jump",
        "dance",
        "idle",
        "point",
        "clap",
        "bow",
        "stretch",
        "jog",
        "march",
        "pose",
    ):
        if tag in text:
            tags.append(tag)
    return tags or ["motion"]


def motion_labels(motions: list[dict[str, Any]]) -> list[str]:
    return [str(motion["label"]) for motion in motions]


def default_scene(motions: list[dict[str, Any]], proxy_assets: list[str]) -> dict[str, Any]:
    labels = motion_labels(motions)
    motion_by_label = {str(motion["label"]): motion for motion in motions}

    def choose_motion(*preferred: str) -> str:
        for label in preferred:
            if label in motion_by_label:
                return label
        return labels[0] if labels else "Idle Breathing"

    scene_duration = 12.0
    idle = choose_motion("Preset: Idle stand", "Idle Breathing")
    start_walk = choose_motion("Preset: Start walking", "Preset: Walk cycle", "Walk")
    walk = choose_motion("Preset: Walk cycle", "Walk")
    stop_walk = choose_motion("Preset: Stop walking", "Preset: Walk cycle", "Walk")
    wave = choose_motion("Preset: Right-hand wave", "Preset: Two-hand wave", "Wave")
    present = choose_motion("Preset: Present to side", "Preset: Point forward", wave)
    look = choose_motion("Preset: Look around", idle)
    clap = choose_motion("Preset: Clap twice", wave)
    bow = choose_motion("Preset: Bow", clap)
    celebrate = choose_motion("Preset: Celebrate", "Preset: Two-hand wave", wave)
    proxy_asset = default_proxy_asset(proxy_assets)

    def clip(label: str, start: float, duration: float, root_mode: str | None = None) -> dict[str, Any]:
        motion = motion_by_label.get(label, {})
        default_root_mode = root_mode or str(motion.get("default_root_mode", "path"))
        if default_root_mode not in {"path", "native"}:
            default_root_mode = "path"
        duration = min(max(0.1, duration), max(0.1, scene_duration - start))
        default_blend = min(DEFAULT_CLIP_BLEND_SECONDS, max(0.05, duration * 0.3))
        return {
            "clip": label,
            "start": round(start, 3),
            "duration": round(duration, 3),
            "trim_start": 0.0,
            "root_mode": default_root_mode,
            "blend_in": round(default_blend, 3),
            "blend_out": round(default_blend, 3),
        }

    scene = {
        "format": SCENE_FORMAT,
        "version": SCENE_VERSION,
        "duration": scene_duration,
        "background": {
            "color": "#f4f1ea",
            "image_path": "",
            "show_grid": True,
            "show_floor": True,
        },
        "camera": {
            "preset": "slow_orbit",
            "target": CAMERA_ORIGIN_TARGET,
            "height": 1.45,
        },
        "export": {
            "fps": 24,
            "width": 960,
            "height": 540,
        },
        "characters": [
            {
                "id": "host",
                "label": "Host",
                "color": CHARACTER_COLOR_PRESETS[0],
                "proxy_asset": proxy_asset,
                "avatar_asset": "",
                "track": [
                    clip(idle, 0.0, 1.0),
                    clip(start_walk, 1.0, 1.2),
                    clip(walk, 2.2, 2.7),
                    clip(stop_walk, 4.9, 1.2),
                    clip(present, 6.3, 2.0),
                    clip(wave, 8.8, 2.2),
                ],
                "root_keys": [
                    {"id": "k0", "time": 0.0, "position": [-2.0, -0.45, 0.0], "facing_degrees": 76.0},
                    {"id": "k1", "time": 2.2, "position": [-1.25, -0.38, 0.0], "facing_degrees": 78.0},
                    {"id": "k2", "time": 5.8, "position": [-0.35, -0.22, 0.0], "facing_degrees": 64.0},
                    {"id": "k3", "time": 12.0, "position": [-0.35, -0.22, 0.0], "facing_degrees": 36.0},
                ],
                "root_segments": [
                    {"from": "k0", "to": "k1", "mode": "linear", "facing": "manual"},
                    {"from": "k1", "to": "k2", "mode": "curve", "facing": "manual"},
                    {"from": "k2", "to": "k3", "mode": "hold", "facing": "manual"},
                ],
            },
            {
                "id": "guest",
                "label": "Guest",
                "color": CHARACTER_COLOR_PRESETS[1],
                "proxy_asset": proxy_asset,
                "avatar_asset": "",
                "track": [
                    clip(idle, 0.0, 1.4),
                    clip(start_walk, 1.4, 1.2),
                    clip(walk, 2.6, 2.4),
                    clip(stop_walk, 5.0, 1.2),
                    clip(clap, 7.0, 1.8),
                    clip(bow, 9.2, 2.0),
                ],
                "root_keys": [
                    {"id": "k0", "time": 0.0, "position": [2.0, 0.55, 0.0], "facing_degrees": -112.0},
                    {"id": "k1", "time": 2.6, "position": [1.25, 0.36, 0.0], "facing_degrees": -112.0},
                    {"id": "k2", "time": 5.8, "position": [0.55, 0.06, 0.0], "facing_degrees": -128.0},
                    {"id": "k3", "time": 12.0, "position": [0.55, 0.06, 0.0], "facing_degrees": -54.0},
                ],
                "root_segments": [
                    {"from": "k0", "to": "k1", "mode": "linear", "facing": "manual"},
                    {"from": "k1", "to": "k2", "mode": "curve", "facing": "manual"},
                    {"from": "k2", "to": "k3", "mode": "hold", "facing": "manual"},
                ],
            },
            {
                "id": "observer",
                "label": "Observer",
                "color": CHARACTER_COLOR_PRESETS[4],
                "proxy_asset": proxy_asset,
                "avatar_asset": "",
                "track": [
                    clip(idle, 0.0, 1.8),
                    clip(look, 1.8, 3.0),
                    clip(clap, 5.4, 1.8),
                    clip(celebrate, 8.0, 2.4),
                ],
                "root_keys": [
                    {"id": "k0", "time": 0.0, "position": [-0.15, 1.05, 0.0], "facing_degrees": 178.0},
                    {"id": "k1", "time": 4.5, "position": [-0.15, 1.05, 0.0], "facing_degrees": 154.0},
                    {"id": "k2", "time": 8.0, "position": [-0.05, 0.96, 0.0], "facing_degrees": 145.0},
                    {"id": "k3", "time": 12.0, "position": [0.05, 0.92, 0.0], "facing_degrees": 142.0},
                ],
                "root_segments": [
                    {"from": "k0", "to": "k1", "mode": "hold", "facing": "manual"},
                    {"from": "k1", "to": "k2", "mode": "linear", "facing": "manual"},
                    {"from": "k2", "to": "k3", "mode": "hold", "facing": "manual"},
                ],
            },
        ],
    }
    return normalize_scene(scene, motions, proxy_assets)


def normalize_scene(
    raw_scene: dict[str, Any],
    motions: list[dict[str, Any]],
    proxy_assets: list[str],
) -> dict[str, Any]:
    valid_motion_labels = set(motion_labels(motions))
    default_motion = next(iter(valid_motion_labels), "Idle Breathing")
    default_asset = default_proxy_asset(proxy_assets)
    scene = {
        "format": SCENE_FORMAT,
        "version": SCENE_VERSION,
        "duration": max(0.5, float(raw_scene.get("duration", 8.0))),
        "background": normalize_background(raw_scene.get("background", {})),
        "camera": normalize_camera(raw_scene.get("camera", {})),
        "export": normalize_export(raw_scene.get("export", {})),
        "characters": [],
    }
    for index, raw_character in enumerate(raw_scene.get("characters", [])):
        if not isinstance(raw_character, dict):
            continue
        character = normalize_character(
            raw_character,
            default_asset=default_asset,
            default_motion=default_motion,
            valid_motion_labels=valid_motion_labels,
            scene_duration=scene["duration"],
            index=index,
        )
        scene["characters"].append(character)
    if not scene["characters"]:
        return default_scene(motions, proxy_assets)
    character_ids = {str(character["id"]) for character in scene["characters"]}
    if scene["camera"].get("target") not in character_ids and scene["camera"].get("target") != CAMERA_ORIGIN_TARGET:
        scene["camera"]["target"] = CAMERA_ORIGIN_TARGET
    return scene


def normalize_background(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    color = str(raw.get("color", "#f4f1ea"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#f4f1ea"
    return {
        "color": color,
        "image_path": str(raw.get("image_path", "")),
        "show_grid": bool(raw.get("show_grid", True)),
        "show_floor": bool(raw.get("show_floor", True)),
    }


def normalize_camera(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    preset = str(raw.get("preset", "slow_orbit"))
    if preset not in {"wide_static", "front_stage", "slow_orbit", "follow_character", "dolly_in", "top_down"}:
        preset = "slow_orbit"
    return {
        "preset": preset,
        "target": str(raw.get("target", "")),
        "height": max(0.4, float(raw.get("height", 1.35))),
    }


def normalize_export(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    fps = int(round(float(raw.get("fps", 24))))
    width = int(round(float(raw.get("width", 960))))
    height = int(round(float(raw.get("height", 540))))
    return {
        "fps": max(1, min(EXPORT_MAX_FPS, fps)),
        "width": max(320, min(EXPORT_MAX_WIDTH, width + (width % 2))),
        "height": max(180, min(EXPORT_MAX_HEIGHT, height + (height % 2))),
    }


def normalize_character(
    raw: dict[str, Any],
    *,
    default_asset: str,
    default_motion: str,
    valid_motion_labels: set[str],
    scene_duration: float,
    index: int,
) -> dict[str, Any]:
    character_id = sanitize_id(str(raw.get("id", raw.get("character_id", f"character_{index + 1}"))), f"character_{index + 1}")
    raw_track = raw.get("track", raw.get("clips", []))
    track = normalize_track(raw_track, default_motion, valid_motion_labels, scene_duration)
    root_keys = normalize_root_keys(raw.get("root_keys", []), raw_track, scene_duration)
    return {
        "id": character_id,
        "label": str(raw.get("label", character_id.replace("_", " ").title())),
        "color": normalize_character_color(raw.get("color"), index),
        "proxy_asset": default_asset,
        "avatar_asset": str(raw.get("avatar_asset", raw.get("asset", ""))),
        "track": track,
        "root_keys": root_keys,
        "root_segments": normalize_root_segments(raw.get("root_segments", []), root_keys),
    }


def normalize_track(
    raw_track: Any,
    default_motion: str,
    valid_motion_labels: set[str],
    scene_duration: float,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    items = raw_track if isinstance(raw_track, list) else []
    for raw_clip in items:
        if not isinstance(raw_clip, dict):
            continue
        clip_label = str(raw_clip.get("clip", default_motion))
        if clip_label not in valid_motion_labels:
            clip_label = default_motion
        start = max(0.0, float(raw_clip.get("start", 0.0)))
        duration = max(0.1, float(raw_clip.get("duration", 3.0)))
        duration = min(duration, max(0.1, scene_duration - start)) if start < scene_duration else duration
        default_blend = min(DEFAULT_CLIP_BLEND_SECONDS, max(0.05, duration * 0.3))
        blend_in = normalize_clip_blend(raw_clip, "blend_in", duration, default_blend)
        blend_out = normalize_clip_blend(raw_clip, "blend_out", duration, default_blend)
        result.append(
            {
                "clip": clip_label,
                "start": round(start, 6),
                "duration": round(duration, 6),
                "trim_start": max(0.0, float(raw_clip.get("trim_start", 0.0))),
                "trim_end": normalize_optional_float(raw_clip.get("trim_end")),
                "root_mode": str(raw_clip.get("root_mode", "path")) if str(raw_clip.get("root_mode", "path")) in {"path", "native"} else "path",
                "blend_in": round(blend_in, 6),
                "blend_out": round(blend_out, 6),
                "_legacy_root_start": raw_clip.get("root_start"),
                "_legacy_root_end": raw_clip.get("root_end"),
                "_legacy_facing": raw_clip.get("facing_degrees"),
            }
        )
    result.sort(key=lambda item: (float(item["start"]), str(item["clip"])))
    for item in result:
        item.pop("_legacy_root_start", None)
        item.pop("_legacy_root_end", None)
        item.pop("_legacy_facing", None)
    return result


def normalize_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return max(0.0, float(value))


def normalize_clip_blend(raw_clip: dict[str, Any], key: str, duration: float, default_blend: float) -> float:
    value = raw_clip.get(key, default_blend)
    if value is None or value == "":
        value = default_blend
    return max(0.0, min(duration, float(value)))


def normalize_root_keys(raw_keys: Any, raw_track: Any, scene_duration: float) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    if isinstance(raw_keys, list):
        for index, raw_key in enumerate(raw_keys):
            if not isinstance(raw_key, dict):
                continue
            keys.append(
                {
                    "id": str(raw_key.get("id", f"k{index}")),
                    "time": max(0.0, min(scene_duration, float(raw_key.get("time", 0.0)))),
                    "position": normalize_vec3(raw_key.get("position", [0.0, 0.0, 0.0])),
                    "facing_degrees": float(raw_key.get("facing_degrees", 0.0)),
                }
            )
    if not keys and isinstance(raw_track, list):
        for raw_clip in raw_track:
            if not isinstance(raw_clip, dict):
                continue
            if "root_start" not in raw_clip and "root_end" not in raw_clip:
                continue
            start = max(0.0, min(scene_duration, float(raw_clip.get("start", 0.0))))
            end = max(0.0, min(scene_duration, start + float(raw_clip.get("duration", 0.0))))
            facing = float(raw_clip.get("facing_degrees", 0.0))
            keys.append(
                {
                    "id": f"k{len(keys)}",
                    "time": start,
                    "position": normalize_vec3(raw_clip.get("root_start", [0.0, 0.0, 0.0])),
                    "facing_degrees": facing,
                }
            )
            keys.append(
                {
                    "id": f"k{len(keys)}",
                    "time": end,
                    "position": normalize_vec3(raw_clip.get("root_end", raw_clip.get("root_start", [0.0, 0.0, 0.0]))),
                    "facing_degrees": facing,
                }
            )
    if not keys:
        keys = [
            {"id": "k0", "time": 0.0, "position": [0.0, 0.0, 0.0], "facing_degrees": 0.0},
            {"id": "k1", "time": scene_duration, "position": [0.0, 0.0, 0.0], "facing_degrees": 0.0},
        ]
    keys.sort(key=lambda item: (float(item["time"]), str(item["id"])))
    seen: set[str] = set()
    for index, key in enumerate(keys):
        key_id = sanitize_id(str(key["id"]), f"k{index}")
        if key_id in seen:
            key_id = f"k{index}"
        seen.add(key_id)
        key["id"] = key_id
    return keys


def normalize_vec3(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return [0.0, 0.0, 0.0]
    values = [float(value[index]) if index < len(value) else 0.0 for index in range(3)]
    return values


def normalize_root_segments(raw_segments: Any, root_keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key_ids = [str(key["id"]) for key in root_keys]
    valid_key_ids = set(key_ids)
    segment_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    if isinstance(raw_segments, list):
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                continue
            from_id = str(raw_segment.get("from", ""))
            to_id = str(raw_segment.get("to", ""))
            if from_id not in valid_key_ids or to_id not in valid_key_ids:
                continue
            mode = str(raw_segment.get("mode", "linear"))
            if mode not in {"linear", "curve", "hold"}:
                mode = "linear"
            segment_by_pair[(from_id, to_id)] = {
                "from": from_id,
                "to": to_id,
                "mode": mode,
                "facing": str(raw_segment.get("facing", "manual")),
            }
    segments: list[dict[str, Any]] = []
    for first, second in zip(key_ids[:-1], key_ids[1:]):
        segments.append(segment_by_pair.get((first, second), {"from": first, "to": second, "mode": "linear", "facing": "manual"}))
    return segments


def scene_warnings(scene: dict[str, Any], motions: list[dict[str, Any]]) -> list[str]:
    labels = set(motion_labels(motions))
    warnings: list[str] = []
    duration = float(scene.get("duration", 0.0))
    for character in scene.get("characters", []):
        label = str(character.get("label", character.get("id", "Character")))
        track = sorted(character.get("track", []), key=lambda clip: float(clip.get("start", 0.0)))
        for index, clip in enumerate(track):
            if clip.get("clip") not in labels:
                warnings.append(f"{label}: missing clip '{clip.get('clip')}'")
            end = float(clip.get("start", 0.0)) + float(clip.get("duration", 0.0))
            if end > duration + 1e-6:
                warnings.append(f"{label}: clip extends past scene")
            if index > 0:
                previous = track[index - 1]
                previous_end = float(previous.get("start", 0.0)) + float(previous.get("duration", 0.0))
                if float(clip.get("start", 0.0)) < previous_end - 1e-6:
                    warnings.append(f"{label}: clips overlap near {float(clip.get('start', 0.0)):.1f}s")
        root_keys = sorted(character.get("root_keys", []), key=lambda key: float(key.get("time", 0.0)))
        for first, second in zip(root_keys[:-1], root_keys[1:]):
            dt = max(1e-6, float(second["time"]) - float(first["time"]))
            dx = float(second["position"][0]) - float(first["position"][0])
            dy = float(second["position"][1]) - float(first["position"][1])
            if ((dx * dx + dy * dy) ** 0.5) / dt > 2.2:
                warnings.append(f"{label}: fast path segment near {float(first['time']):.1f}s")
    return warnings[:8]


def scene_library(scene_dir: Path) -> list[dict[str, str]]:
    if not scene_dir.exists():
        return []
    scenes: list[dict[str, str]] = []
    for path in sorted(scene_dir.glob("*.scene.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("format") == SCENE_FORMAT:
            scenes.append({"name": path.stem.removesuffix(".scene"), "path": str(path)})
    return scenes


def load_scene_file(path: Path, motions: list[dict[str, Any]], proxy_assets: list[str]) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("format") != SCENE_FORMAT:
        raise ValueError(f"{path.name} is not a GF5 motion scene.")
    return normalize_scene(raw, motions, proxy_assets)


def save_scene_file(scene_dir: Path, name: str, scene: dict[str, Any]) -> Path:
    scene_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_scene_stem(name)
    path = scene_dir / f"{stem}.scene.json"
    path.write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return path
