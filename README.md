# GF5: Animating 3D Characters

[![Project Page](https://img.shields.io/badge/Project%20Page-GitHub%20Pages-0969da)](https://cambridgecvcourses.github.io/IIA-Project-GF5/)

This repository contains the codebase for the IIA Project GF5: Animating 3D
Characters. Start with the
[project page](https://cambridgecvcourses.github.io/IIA-Project-GF5/) for the
brief, setup instructions, calendar, report requirements, and slides. Use this
repo to run the tools, complete the coding tasks, and produce the Part 3
animation scene.

The project is organised into three technical parts, two reports, and a short
final presentation:

- Part 1: forward kinematics on a rigid block character
- Part 2: skinning weights and linear blend skinning using SMPL
- Part 3: group character animation using motion clips, avatars, and scene
  editing
- Reports: interim report after Part 2, final report after Part 3
- Final presentation: a light technical showcase of the Part 3 result

All materials are released together. Use the calendar and assessment table on
the project page for the intended pacing.

## Materials

- [Project Overview](https://cambridgecvcourses.github.io/IIA-Project-GF5/)
- [Setup](https://cambridgecvcourses.github.io/IIA-Project-GF5/setup.html)
- [Part 1: Forward Kinematics](https://cambridgecvcourses.github.io/IIA-Project-GF5/part1.html)
- [Part 2: Skinning and LBS](https://cambridgecvcourses.github.io/IIA-Project-GF5/part2.html)
- [Interim Report](https://cambridgecvcourses.github.io/IIA-Project-GF5/interim.html)
- [Part 3: Group Character Animation Project](https://cambridgecvcourses.github.io/IIA-Project-GF5/part3.html)
- [Scene Editor Manual](https://cambridgecvcourses.github.io/IIA-Project-GF5/scene_editor.html)
- [Part 3 Showcase](https://cambridgecvcourses.github.io/IIA-Project-GF5/showcase.html)
- [Final Report](https://cambridgecvcourses.github.io/IIA-Project-GF5/final_report.html)
- [FAQ](https://cambridgecvcourses.github.io/IIA-Project-GF5/faq.html)
- [References](https://cambridgecvcourses.github.io/IIA-Project-GF5/references.html)
- [Parts 1&2 Slides](https://cambridgecvcourses.github.io/IIA-Project-GF5/parts12-slides.html)
- [Part 3 Slides](https://cambridgecvcourses.github.io/IIA-Project-GF5/part3-slides.html)

## Slides

For quick viewing, open the [online Parts 1&2 slides](https://cambridgecvcourses.github.io/IIA-Project-GF5/parts12-slides.html)
or [Part 3 slides](https://cambridgecvcourses.github.io/IIA-Project-GF5/part3-slides.html).
The Notes panel works there too; notes are cached in the browser on that
device.

To open the same HTML locally without project-folder note saving, run:

```bash
python3 docs/build_site.py
python3 slides/build_slides.py
python3 slides/build_slides.py --source slides/part3.md --output site/part3-slides.html
```

Then open `site/parts12-slides.html` or `site/part3-slides.html` in a browser.

To save your own slide notes as a Markdown file in the project folder, run this
from the repository root:

```bash
python3 slides/serve.py
```

Then open `http://127.0.0.1:8095/parts12-slides.html`. Notes are saved per
deck under `slides/student_notes/`, for example `parts12_notes.md`. The same
server also builds and serves `part3-slides.html`.

## Running The Tools

Use [docs/setup.md](docs/setup.md) as the source of truth for creating the
`gf5` environment, remote/headless sessions, SMPL model files, and local output
folders.

Use the Asset Viewer for Parts 1 and 2:

```bash
python viewer/asset_viewer.py
```

Use the Scene Editor for Part 3:

```bash
python viewer/scene_web_server.py --port 8093
```

Run both commands from the repository root after activating the `gf5`
environment.

## Repository Layout

- `docs/`: handout source documents
- `slides/`: Markdown slide decks and slide-building tools
- `viewer/`: the Asset Viewer, Scene Editor, rendering code, and student
  implementation stubs
- `assets/blocky/`: the block character assets
- `assets/smpl/`: local SMPL model files, if installed
- `libraries/motions/preset/`: bundled Part 3 motion clips
- `libraries/motions/custom/`: local generated or hand-authored motion clips
- `libraries/avatars/`: local extracted custom avatar packages
- `libraries/scenes/`: local Scene Editor drafts
- `exports/`: local rendered videos

Local custom motions, avatars, poses, scenes, and rendered videos are ignored by
git. Submit the files requested on the report pages, but do not treat these
local output folders as source code.
