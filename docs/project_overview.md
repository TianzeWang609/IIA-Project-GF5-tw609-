# GF5: Animating 3D Characters

## What This Project Is About

This project studies a simple version of the character-animation pipeline:

1. represent a character as a skeleton and a mesh
2. pose the skeleton with forward kinematics
3. attach a surface to that skeleton with skinning weights
4. turn a sequence of poses into a short animation

The emphasis is on understanding the mechanics of animation, not on learning a
large authoring package.

## Instructor

[Elliott (Shangzhe) Wu](https://www.elliottwu.com/)

## Assumed Background

You are expected to be comfortable with:

- basic Python
- vectors and matrices
- reading and modifying small codebases

You are not expected to have prior experience with:

- 3D graphics
- rigging
- animation software
- SMPL or human-body models

Before running the viewer, create the Python environment from the shipped
`env.yml` file.

## Why The Project Starts With A Block Character

The early parts use a blocky articulated character rather than a realistic
human mesh.

That is deliberate. A block character makes the hierarchy easy to see:

- each body part is rigid
- each joint is easy to identify
- FK bugs are visually obvious

Once the skeleton logic is clear, we switch to SMPL and study mesh deformation.

## Project Parts

### Part 1

Focus:

- joint hierarchies
- local versus world transforms
- forward kinematics
- key poses and timeline-based motion authoring

See [Part 1](part1.md) for the exact coding tasks, required outputs, and the
part-1 material that must be prepared for the interim report.

### Part 2

Focus:

- rest pose
- skinning weights
- one-hot skinning
- comparison with linear blend skinning (LBS)
- motion reuse on SMPL

See [Part 2](part2.md) for the exact coding tasks and implementation
requirements.

### Part 3

Focus:

- later group character-animation work building on the same FK and skinning
  pipeline
- final brief and deliverables to be released after the interim checkpoint

The Part 3 brief is not part of the current Parts 1 and 2 release. Use the
[Part 3 placeholder](part3_placeholder.md) for release status.

## Interim Checkpoint

At the end of Part 2, you should have enough material for an interim report.

The exact required content, figures, videos, code submission, and report
structure are defined in the relevant handouts:

- [Part 1](part1.md) for the part-1 material you must carry forward
- [Part 2](part2.md) for the skinning tasks and evidence you need to collect
- [Interim Report](interim.md) for the complete report and submission
  requirements

## Use Of AI Tools

For this project, you should not use AI tools to generate the work that you
submit.

In particular, do not use AI tools to:

- write or substantially rewrite your code
- derive the core math for you
- write sections of your report
- generate fake results, figures, citations, or explanations

The point of the project is for you to implement, test, and explain the
animation pipeline yourself.

If you use AI tools at all, keep it to minor support only, for example:

- asking for clarification of a concept or notation you are struggling with
- spelling or grammar checks on text you wrote yourself
- help with software setup or environment issues

The interim report should include a short `AI Use Statement` saying either:

- `No AI tools used`, or
- what limited non-substantive use, if any, you made of AI tools

## Main Files

The core teaching code lives in:

- `viewer/asset_viewer.py`
- `viewer/motion_sequences.py`
- `viewer/skeleton_profiles.py`
- `viewer/smpl_support.py`

The viewer is used throughout Parts 1 and 2 for:

- skeleton inspection
- pose editing
- timeline authoring
- skinning-weight visualisation
- video export

It also provides the starting point for Part 3 motion preview and evidence
export where appropriate after the later brief is released.
