#!/usr/bin/env python3
"""Serve GF5 slide decks locally and save notes into the project folder."""

from __future__ import annotations

import argparse
import json
import re
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DOCS_ROOT = PROJECT_ROOT / "docs"
SITE_ROOT = PROJECT_ROOT / "site"
DEFAULT_NOTES_DIR = ROOT / "student_notes"

sys.path.insert(0, str(DOCS_ROOT))

from build_site import SLIDE_DECKS, build_site
from build_slides import DEFAULT_SOURCE, build_slides


def clean_text_mapping(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if index < 1:
            continue
        cleaned[str(index)] = str(value)
    return dict(sorted(cleaned.items(), key=lambda item: int(item[0])))


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def clean_deck_id(raw: str | None) -> str:
    if not raw:
        return "parts12"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", raw.strip()).strip("-").lower()
    return cleaned or "parts12"


def notes_paths(notes_dir: Path, deck_id: str) -> tuple[Path, Path]:
    deck_id = clean_deck_id(deck_id)
    return notes_dir / f"{deck_id}_notes.json", notes_dir / f"{deck_id}_notes.md"


def load_notes(notes_dir: Path, deck_id: str) -> dict[str, Any]:
    path, markdown_path = notes_paths(notes_dir, deck_id)
    if not path.exists():
        return {"notes": {}, "titles": {}, "path": relative_to_project(markdown_path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"notes": {}, "titles": {}, "path": relative_to_project(markdown_path)}
    return {
        "notes": clean_text_mapping(payload.get("notes")),
        "titles": clean_text_mapping(payload.get("titles")),
        "path": relative_to_project(markdown_path),
    }


def render_notes_markdown(deck_id: str, notes: dict[str, str], titles: dict[str, str]) -> str:
    deck_title = clean_deck_id(deck_id).replace("-", " ").replace("_", " ").title()
    lines = [
        f"# GF5 {deck_title} Slide Notes",
        "",
        "Saved by `python3 slides/serve.py`.",
        "",
    ]
    wrote_any = False
    for slide_id, note in notes.items():
        if not note.strip():
            continue
        title = titles.get(slide_id, f"Slide {slide_id}")
        lines.extend([f"## Slide {slide_id}: {title}", "", note.rstrip(), ""])
        wrote_any = True
    if not wrote_any:
        lines.extend(["No notes yet.", ""])
    return "\n".join(lines)


def save_notes(notes_dir: Path, deck_id: str, notes: dict[str, str], titles: dict[str, str]) -> Path:
    json_path, markdown_path = notes_paths(notes_dir, deck_id)
    payload = {
        "notes": notes,
        "titles": titles,
        "markdown": markdown_path.name,
    }
    write_atomic(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_atomic(markdown_path, render_notes_markdown(deck_id, notes, titles))
    return markdown_path


def relative_to_project(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def known_deck_output(source: Path, site_root: Path) -> Path | None:
    source = source.resolve()
    for deck in SLIDE_DECKS:
        deck_source = (DOCS_ROOT / deck.source).resolve()
        if deck_source == source:
            return site_root / deck.output
    return None


def build_decks(source: Path, site_root: Path) -> Path:
    build_site(site_root)
    for deck in SLIDE_DECKS:
        deck_source = (DOCS_ROOT / deck.source).resolve()
        build_slides(deck_source, site_root / deck.output)

    selected_output = known_deck_output(source, site_root)
    if selected_output is not None:
        return selected_output

    custom_output = site_root / "parts12-slides.html"
    build_slides(source.resolve(), custom_output)
    return custom_output


def make_handler(
    site_root: Path,
    notes_dir: Path,
    *,
    default_path: str,
) -> type[SimpleHTTPRequestHandler]:
    class SlideDeckHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(site_root), **kwargs)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", f"/{default_path}")
                self.end_headers()
                return
            if path == "/api/slide-notes" or path.startswith("/api/slide-notes/"):
                deck_id = path.rsplit("/", 1)[-1] if path.startswith("/api/slide-notes/") else "parts12"
                self.send_json(load_notes(notes_dir, deck_id))
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/api/slide-notes" and not path.startswith("/api/slide-notes/"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            deck_id = path.rsplit("/", 1)[-1] if path.startswith("/api/slide-notes/") else "parts12"

            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(HTTPStatus.BAD_REQUEST, "Expected JSON notes payload")
                return

            notes = clean_text_mapping(payload.get("notes"))
            titles = clean_text_mapping(payload.get("titles"))
            markdown_path = save_notes(notes_dir, deck_id, notes, titles)
            self.send_json(
                {
                    "ok": True,
                    "path": relative_to_project(markdown_path),
                }
            )

        def send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SlideDeckHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8095, help="Port to serve the deck on.")
    parser.add_argument(
        "--notes-dir",
        type=Path,
        default=DEFAULT_NOTES_DIR,
        help="Directory where per-student slide notes are saved.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Markdown slide source to open first after building.",
    )
    parser.add_argument(
        "--site-root",
        type=Path,
        default=None,
        help="Generated site directory to serve. Defaults to site/.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Serve the existing generated slide HTML without rebuilding first.",
    )
    args = parser.parse_args()

    site_root = (args.site_root or SITE_ROOT).resolve()
    selected_output = site_root / "parts12-slides.html"
    if not args.no_build:
        selected_output = build_decks(args.source, site_root)
    elif known_output := known_deck_output(args.source, site_root):
        selected_output = known_output

    notes_dir = args.notes_dir.resolve()
    selected_name = selected_output.resolve().relative_to(site_root).as_posix()
    handler = make_handler(site_root, notes_dir, default_path=selected_name)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/{selected_name}"
    print(f"Serving GF5 slides: {url}")
    print(f"Saving notes to: {relative_to_project(notes_dir)}/*_notes.md")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped slide server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
