# Bring A Character To Life

## GF5: Animating 3D Characters

Skeletons, skinning, motion, and a final human-avatar scene.

![Animation viewer preview](assets/gf5-rig-preview.svg)

???
Open with the aspiration rather than the implementation. Students should feel
that the block character, FK recurrence, and skinning code are stepping stones
toward controllable animated avatars.

---

# Motivation

## The trick behind a moving character

- a surface that looks like a person or creature
- an internal skeleton that gives it structure
- motion data that says how the body changes over time
- rendering choices that make the result readable

???
Keep this intuitive. The project is not about learning a full authoring
package; it is about understanding the moving pieces underneath one.

---

# Immersive Virtual Characters

{{youtube: WU0gvPcc3jQ | The Matrix Awakens: An Unreal Engine 5 Experience | Digital humans, real-time staging, cinematic lighting, and interactive 3D.}}

???
Show this one. It is a strong way to set ambition without pretending students
will reproduce this exact production. Point out the same chain they will study:
motion, skeletons, surfaces, staging, and rendering.

---

# Meshcapade

{{website-shot: assets/meshcapade.jpg | https://meshcapade.com/ | Meshcapade | Markerless motion capture, motion generation, and human-understanding tooling.}}

???
Use this before MetaHuman because it is closer to the technical substrate of
the project: body models, motion capture, and SMPL-style digital humans. Note
that this is a reference point rather than a required coursework tool.

---

# MetaHuman

{{website-shot: assets/metahuman-site-screenshot.png | https://www.metahuman.com/?lang=en-US | MetaHuman | High-fidelity digital humans made easy.}}

???
Use this as the professional toolchain reference: a web-facing product built
around rigged, animatable digital humans. It is a website link rather than an
iframe because product sites often block being loaded inside another page.

---

# AI Rigging & Neural Layer

{{youtube: dMrSRhwSkTQ | Introducing AI Rigging and Neural Layer - Autodesk Flow Studio | AI-assisted rigging, video-driven animation, and neural rendering as a near-future workflow.}}

???
Use this as the "where is the field going?" moment. Keep it inspirational, then
bring the room back to why FK, skinning, and controllable scenes are still the
technical foundations: rigging, motion, controllability, and rendering choices.

---

# Four-Week Timeline

{{timeline: ../docs/project_overview.md#Four-Week Shape}}

???
This is the roadmap. Emphasize individual work first, then pairs in the second
half. Parts 1 and 2 build the mechanics; Parts 3 and 4 use those mechanics to
make a scene.

---

# Assessment

{{assessment-table: ../docs/project_overview.md#Assessment}}

???
Use exact dates: Friday 29 May 2026 at 4pm for interim items, Tuesday 9 June
2026 from 11am to 1pm for the final presentation, and Friday 12 June 2026 at
4pm for final submissions.

---

# Calendar

{{schedule-calendar: project}}

???
Use this as the logistics pass: green pins are mandatory sessions, blue pins
are optional help, red pins are report or result deadlines, and gold is the
final presentation.

---

# The Project In One Sentence

Build a small character-animation pipeline, then use it to create an animated
human-avatar scene.

???
This replaces the old "one sentence" slide that immediately became a list. The
list comes next as the pipeline.

---

# The Pipeline

{{include: ../docs/project_overview.md#What This Project Is About}}

???
Treat the four numbered steps as the conceptual spine of the course. The
student-facing handout stores the canonical wording.

---

# Materials

- `docs/`: handouts, report requirements, and setup instructions
- `viewer/`: interactive viewer and scene tools
- `viewer/student_submission/`: files students edit
- `assets/`: block characters, motions, and SMPL assets
- `slides/`: browser presentation decks and local notes support

???
This is the transition from motivation into the actual codebase. Do not spend
long on every file; just give students a map.

---

# Week 1: Forward Kinematics

## From skeleton hierarchy to motion

???
Use this as the section break before the technical material starts. The goal is
to make the room feel a shift from project overview into the first working
session.

---

# Why We Start With Blocks

{{include: ../docs/project_overview.md#Why The Project Starts With A Block Character}}

???
Emphasize that the block character is a diagnostic tool, not a toy example to
rush past. FK mistakes are much easier to see when every body part is rigid.

---

# What Rigging Gives Us

{{youtube: 3RSwjZLClRc | 3D Rigging is Beautiful, Here's How It Works! | A visual explanation of skeletons, controls, and why animation starts with a rig.}}

???
Show a short excerpt before Part 1. Use it to explain that the Week 1 code is a
small, explicit version of the same idea: a hierarchy of joints drives visible
body parts.

---

# Part 1: Forward Kinematics

{{bullets: ../docs/part1.md#Learning Goals}}

Output: one custom motion clip with at least `10` keyframes.

???
This is a good place to draw the parent-child idea on the board. Keep the
recurrence high level unless the audience asks for the matrix detail.

---

# Demo: Show The Viewer

- skeleton overlay
- joint selection
- shoulder or hip rotation
- timeline keyframes
- exported motion video

[Open local viewer](http://localhost:8090)

???
Show the demo here.

Suggested setup before the session:

- `cd /home/mifs/sw2181/teaching/GF5/GF5`
- `python viewer/asset_viewer.py --port 8090 --no-open-browser`

In the browser, show a built-in motion first, then edit one visible joint and
capture a keyframe so students understand what they will produce.

---

# Viewer Controls

- `Motion`: choose a built-in or saved motion clip.
- `Animate`: play or pause the selected motion.
- `Show Skeleton`, `Show Mesh`, `Show Skinning Weights`: toggle visual layers.
- `Selected Joint` and `Joint Editor`: inspect and edit one joint.
- `Timeline`: capture keyframes for a custom sequence.
- `Export Motion Video`: render evidence from the current browser camera view.

???
Do not read every control. Point out the controls that support the Part 1 and
Part 2 evidence: skeleton, mesh, skinning weights, selected joint, timeline,
and video export.

---

# Part 2: Skinning And SMPL

{{bullets: ../docs/part2.md#Learning Goals}}

Same motion, different character surface.

???
Keep returning to the contrast: the skeleton pose may be identical, while the
surface behavior changes because the mesh is attached differently.

---

# One-Hot Skinning

{{include: ../docs/part2.md#One-Hot Skinning}}

???
Use this as the deliberately simple baseline: each vertex chooses one dominant
joint, so the result is easy to reason about but limited near bending joints.

---

# Linear Blend Skinning

{{include: ../docs/part2.md#Linear Blend Skinning}}

???
This is the conceptual bridge to realistic deformation. Students do not need
every SMPL detail yet; they need to understand that nearby bones can share a
vertex instead of forcing a single rigid owner.

---

# Interim Checkpoint

{{bullets: ../docs/interim.md#What To Submit}}

???
Make this feel practical. The report is not separate from the coding work:
screenshots, videos, and comparisons should be collected while they debug.

---

# Parts 3 And 4

Work in groups of two to create a coherent 30-second animated human-avatar
scene.

- explore human motion sequences using a human body model
- understand how SMPL-compatible motions can drive a skinned character
- connect a reconstructed character mesh to the same 24-joint body skeleton
- choose, combine, and refine motion clips for a short scene
- produce a 30-second final animation video
- explain the strengths and limitations of your character-animation pipeline

???
This slide can be shortened verbally if Part 3 has not been released to
students yet. The purpose is to show why the FK and skinning work matters.

---

# Preview: Scene Composition

- preset human motion clips
- multiple character tracks
- root placement and facing
- draft preview before final export
- saved `.scene.json` files

???
Use this only as a teaser if the session is mainly for Parts 1 and 2. The
public Part 3 tooling and brief will be introduced later.

---

# How Students Should Work

- implement a small piece
- test it visually in the viewer
- save evidence immediately
- compare failure cases, not just final results
- ask for help with a specific screenshot or clip

???
This is lecture framing rather than duplicated handout text. It gives students
the working rhythm you want them to adopt.

---

# AI Use Policy

- Parts 1 and 2: no AI-generated code, math derivations, or results.
- Parts 3 and 4: AI tools may support creative/production work.
- Final focus: a realistic, controllable 3D avatar rendering scene.
- Reports: no wholesale AI-written content; grammar help is allowed.
- Every report needs an `AI Use Statement`.

???
Use the distinction: no AI-generated code/results for Parts 1 and 2; more
freedom in Parts 3 and 4 for production/creative tools; reports must not be
wholesale AI-generated and must include declarations.

---

# Where To Go Next

- [Setup](setup.html)
- [Part 1](part1.html)
- [Part 2](part2.html)
- [Interim report](interim.html)
- [References](references.html)
- [Project repository](https://github.com/CambridgeCVCourses/IIA-Project-GF5)

???
End by sending students to setup and Part 1, then leave time for viewer setup
questions.
