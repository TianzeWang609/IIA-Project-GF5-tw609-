#!/usr/bin/env python3
"""Serve the GF5 intro deck locally and save notes into the project folder."""

from __future__ import annotations

import argparse
import json
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
NOTES_JSON = "intro_notes.json"
NOTES_MARKDOWN = "intro_notes.md"

sys.path.insert(0, str(DOCS_ROOT))

from build_site import build_site
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


def load_notes(notes_dir: Path) -> dict[str, Any]:
    path = notes_dir / NOTES_JSON
    if not path.exists():
        return {"notes": {}, "titles": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"notes": {}, "titles": {}}
    return {
        "notes": clean_text_mapping(payload.get("notes")),
        "titles": clean_text_mapping(payload.get("titles")),
    }


def render_notes_markdown(notes: dict[str, str], titles: dict[str, str]) -> str:
    lines = [
        "# GF5 Intro Session Notes",
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


def save_notes(notes_dir: Path, notes: dict[str, str], titles: dict[str, str]) -> None:
    payload = {
        "notes": notes,
        "titles": titles,
        "markdown": NOTES_MARKDOWN,
    }
    write_atomic(notes_dir / NOTES_JSON, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_atomic(notes_dir / NOTES_MARKDOWN, render_notes_markdown(notes, titles))


def relative_to_project(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def make_handler(site_root: Path, notes_dir: Path) -> type[SimpleHTTPRequestHandler]:
    class IntroDeckHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(site_root), **kwargs)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/intro.html")
                self.end_headers()
                return
            if path == "/api/intro-notes":
                self.send_json(
                    {
                        **load_notes(notes_dir),
                        "path": relative_to_project(notes_dir / NOTES_MARKDOWN),
                    }
                )
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/api/intro-notes":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

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
            save_notes(notes_dir, notes, titles)
            self.send_json(
                {
                    "ok": True,
                    "path": relative_to_project(notes_dir / NOTES_MARKDOWN),
                }
            )

        def send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return IntroDeckHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8095, help="Port to serve the deck on.")
    parser.add_argument(
        "--notes-dir",
        type=Path,
        default=DEFAULT_NOTES_DIR,
        help="Directory where per-student intro notes are saved.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Markdown slide source to build before serving.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Serve the existing site/intro.html without rebuilding first.",
    )
    args = parser.parse_args()

    if not args.no_build:
        build_site(SITE_ROOT)
        build_slides(args.source.resolve(), SITE_ROOT / "intro.html")

    notes_dir = args.notes_dir.resolve()
    handler = make_handler(SITE_ROOT.resolve(), notes_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/intro.html"
    print(f"Serving intro deck: {url}")
    print(f"Saving notes to: {relative_to_project(notes_dir / NOTES_MARKDOWN)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped intro deck server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
