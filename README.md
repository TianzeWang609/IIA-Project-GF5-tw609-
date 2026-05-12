# GF5: Animating 3D Characters

[![Project Page](https://img.shields.io/badge/Project%20Page-GitHub%20Pages-0969da)](https://cambridgecvcourses.github.io/IIA-Project-GF5/)

This repository contains the teaching assets and student handouts for an
undergraduate project on 3D character animation.

The material is being written in Markdown first so it can evolve alongside the
code and assets. The project is organised into three parts:

- Part 1: forward kinematics on a rigid block character
- Part 2: skinning weights and linear blend skinning using SMPL
- Part 3: later group character-animation brief

## Reading Order

- [Project Overview](docs/project_overview.md)
- [Part 1: Forward Kinematics](docs/part1.md)
- [Part 2: Skinning and LBS](docs/part2.md)
- [Interim Report](docs/interim.md)
- [Part 3: Coming Soon](docs/part3_placeholder.md)

The published project page is the main student-facing version of the Parts 1
and 2 handouts. The website is generated from the Markdown files in `docs/`.
To preview local changes, run:

```bash
python docs/build_site.py
```

Then open `site/index.html`.

On GitHub, `.github/workflows/build-docs-site.yml` publishes generated HTML to
the `gh-pages` branch. Configure GitHub Pages to deploy from the `gh-pages`
branch root.

## Repository Layout

- `docs/`: student-facing handouts and project notes
- `viewer/`: the runnable animation viewer and implementation stubs
- `assets/blocky/`: the block character assets
- `assets/smpl/`: local SMPL model files, if installed
- `libraries/`: local pose and motion libraries created in the viewer
- `exports/`: local rendered videos

## Running the Viewer

Create the Python environment from the shipped environment file:

```bash
mamba env create -f env.yml
mamba activate gf5
```

From the repository root:

```bash
python viewer/asset_viewer.py
```

This opens the local viewer page in your browser automatically.
To use a different port, for example when another viewer is already running:

```bash
python viewer/asset_viewer.py --port 8090
```

## Current Approach

- Keep the runnable code stable under `viewer/`
- Put teaching documents under `docs/`
- Use the same viewer framework to bridge FK, skinning, motion preview, and
  final-project evidence export
