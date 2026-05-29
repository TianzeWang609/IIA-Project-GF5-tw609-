# GF5: Animating 3D Characters

[![Project Page](https://img.shields.io/badge/Project%20Page-GitHub%20Pages-0969da)](https://cambridgecvcourses.github.io/IIA-Project-GF5/)

This repository contains the codebase for the IIA Project GF5: Animating 3D Characters. Start with the [project page](https://cambridgecvcourses.github.io/IIA-Project-GF5/) for the brief, instructions, and
reports, then use this repo to run the viewer and complete the coding
tasks.

The project is organised into three parts:

- Part 1: forward kinematics on a rigid block character
- Part 2: skinning weights and linear blend skinning using SMPL
- Part 3: group character animation and final video

## Project Handouts

- [Project Overview](https://cambridgecvcourses.github.io/IIA-Project-GF5/)
- [Part 1: Forward Kinematics](https://cambridgecvcourses.github.io/IIA-Project-GF5/part1.html)
- [Part 2: Skinning and LBS](https://cambridgecvcourses.github.io/IIA-Project-GF5/part2.html)
- [Interim Report](https://cambridgecvcourses.github.io/IIA-Project-GF5/interim.html)
- [Part 3: Group Character Animation Project](https://cambridgecvcourses.github.io/IIA-Project-GF5/part3.html)
- [Scene Editor Manual](https://cambridgecvcourses.github.io/IIA-Project-GF5/scene_editor.html)
- [Part 3 Showcase](https://cambridgecvcourses.github.io/IIA-Project-GF5/showcase.html)
- [Final Report](https://cambridgecvcourses.github.io/IIA-Project-GF5/final_report.html)
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

## Running the Viewer

Use [docs/setup.md](docs/setup.md) as the source of truth for creating the
`gf5` environment, starting the viewer, remote/headless sessions, SMPL model
files, and local output folders.

In short: create the environment from `env.yml`, activate `gf5`, and run
`python viewer/asset_viewer.py` from the repository root.

## Repository Layout

- `docs/`: handout source documents
- `viewer/`: the animation viewer, scene tools, and implementation stubs
- `assets/blocky/`: the block character assets
- `assets/smpl/`: local SMPL model files, if installed
- `libraries/`: Part 3 motion/avatar libraries plus local saved poses and scenes
- `exports/`: local rendered videos
