# GF5: Animating 3D Characters

## Motivation

Animated characters look magical, but the core ideas are concrete:

- a surface that looks like a person or creature
- an internal skeleton that gives it structure
- motion data that says how the body changes over time
- rendering choices that make the result readable

The project studies those pieces directly, starting with a block character
where the hierarchy is visible before moving toward human-avatar scenes.

### Immersive Virtual Characters

{{youtube: WU0gvPcc3jQ | The Matrix Awakens: An Unreal Engine 5 Experience | Digital humans, real-time staging, cinematic lighting, and interactive 3D.}}

### AI Rigging & Neural Layer

{{youtube: dMrSRhwSkTQ | Introducing AI Rigging and Neural Layer - Autodesk Flow Studio | AI-assisted rigging, video-driven animation, and neural rendering as a near-future workflow.}}

## What This Project Is About

Build a small character-animation pipeline, then use it to create an animated
human-avatar scene.

This project studies a simple version of the character-animation pipeline:

1. represent a character as a skeleton and a mesh
2. pose the skeleton with forward kinematics
3. attach a surface to that skeleton with skinning weights
4. turn a sequence of poses into a short animation

The emphasis is on understanding the mechanics of animation, not on learning a
large authoring package.

## Four-Week Shape

| Week | Mode | Focus |
| --- | --- | --- |
| Week 1 | Individual | Implement and debug forward kinematics on a simple block character. |
| Week 2 | Individual | Implement and compare one-hot skinning and linear blend skinning on SMPL. |
| Week 3 | Pairs | Explore human motion clips and reconstruct group-member characters. |
| Week 4 | Pairs | Refine the group animation scene and export the final video. |

## Assessment

| Coursework | Due date | Marks | Mode |
| --- | --- | --- | --- |
| Interim report | Friday 29 May 2026 (4pm) | 20 | Individual |
| Interim animation results | Friday 29 May 2026 (4pm) | 5 | Individual |
| Final presentation | Tuesday 9 June 2026 (11-1) | 10 | Group |
| Final report | Friday 12 June 2026 (4pm) | 30 | 50% individual, 50% group |
| Final animation results | Friday 12 June 2026 (4pm) | 15 | Group |

## Calendar

{{schedule-calendar: project}}

For the BE454 help sessions, a booking system will be set up later so that too
many people do not arrive at the same time. You can still drop by the office.

## Intro Slides

Use the [intro slides](../slides/intro.md) for the first session.

For quick viewing, open the slides from the project website. To open the same
HTML locally without project-folder note saving, run
`python3 docs/build_site.py`, then `python3 slides/build_slides.py`, and open
`site/intro.html` in a browser.

To keep your own notes in the project folder, run this from the repository
root:

```bash
python3 slides/serve.py
```

Then open `http://127.0.0.1:8095/intro.html`. Your notes are saved to
`slides/student_notes/intro_notes.md`.

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

For Parts 1 and 2, do not use AI tools to generate your submitted code, derive
the core math for you, or generate your results.

For Parts 3 and 4, you may use AI tools as part of the creative or production
workflow. The focus is still to create a realistic, controllable 3D avatar
rendering scene and to explain how your group produced it.

For both reports, do not use AI tools to generate the report content wholesale.
Minor grammar, wording, or formatting help is allowed, but the explanation,
figures, results, and interpretation must be yours.

Every report must include an `AI Use Statement` saying either `No AI tools
used`, or describing the limited use you made of AI tools.

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
