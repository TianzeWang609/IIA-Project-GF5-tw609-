# GF5: Animating 3D Characters

[![Project Page](https://img.shields.io/badge/Project%20Page-GitHub%20Pages-0969da)](https://cambridgecvcourses.github.io/IIA-Project-GF5/)

This repository contains the codebase for the IIA Project GF5: Animating 3D Characters. Start with the [project page](https://cambridgecvcourses.github.io/IIA-Project-GF5/) for the brief, instructions, and
interim report, then use this repo to run the viewer and complete the coding
tasks.

The project is organised into three parts:

- Part 1: forward kinematics on a rigid block character
- Part 2: skinning weights and linear blend skinning using SMPL
- Part 3: later group character-animation brief

## Project Handouts

- [Project Overview](https://cambridgecvcourses.github.io/IIA-Project-GF5/)
- [Part 1: Forward Kinematics](https://cambridgecvcourses.github.io/IIA-Project-GF5/part1.html)
- [Part 2: Skinning and LBS](https://cambridgecvcourses.github.io/IIA-Project-GF5/part2.html)
- [Interim Report](https://cambridgecvcourses.github.io/IIA-Project-GF5/interim.html)
- [Part 3: Coming Soon](https://cambridgecvcourses.github.io/IIA-Project-GF5/part3.html)
- [References](https://cambridgecvcourses.github.io/IIA-Project-GF5/references.html)
- [Intro Slides](https://cambridgecvcourses.github.io/IIA-Project-GF5/intro.html)

## Intro Slides

For quick viewing, open the [online intro slides](https://cambridgecvcourses.github.io/IIA-Project-GF5/intro.html).
To open the same HTML locally without project-folder note saving, run:

```bash
python3 docs/build_site.py
python3 slides/build_slides.py
```

Then open `site/intro.html` in a browser.

To save your own slide notes locally, run this from the repository root:

```bash
python3 slides/serve.py
```

Then open `http://127.0.0.1:8095/intro.html`. Notes are saved in
`slides/student_notes/intro_notes.md`.

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
- `libraries/`: local pose and motion libraries created in the viewer
- `exports/`: local rendered videos
