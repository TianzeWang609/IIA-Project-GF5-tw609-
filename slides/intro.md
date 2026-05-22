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
Use exact dates: Friday 29 May 2026 at 2pm for interim items, Tuesday 9 June
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

# Week 2: Skinning And SMPL

## From skeleton motion to deforming surfaces

???
Use this as the section break before the Part 2 technical material. Remind
students that the same joint motion now has to drive a continuous surface, not
separate rigid blocks.

---

# Calendar Updates

{{schedule-calendar: project | updates}}

???
Pause on the highlighted items: Friday 29 May help is now 9-10, interim report
and required results are due at 2pm, and Friday 12 June has no help or
mandatory session.

---

# FAQ

[Open the FAQ](faq.html)

- setup and Git questions we expect more than once
- short answers collected in one student-facing page
- updated as recurring questions come up

???
Use this as a low-friction support pointer before the technical material.
Students should know there is one place to check before asking repeated setup
or Git workflow questions.

---

# Current FAQ Items

- `conda` can be used in place of `mamba`
- use two Git remotes if you want to keep custom code in your own repository
- pull course updates from the teaching repo; push your work to your repo
- SMPL model download details are in the Part 2 notes
- Windows SMPL loading issue: see FAQ and GitHub issue `#1`

???
Keep this brief. The FAQ page has the concrete commands, so the slide should
only give the mental model and point students to the page.

---

# Why Skinning Changes The Problem

- same FK poses from Part 1
- a human mesh that bends around joints
- weights decide how much each bone moves each vertex
- one-hot binding is the useful baseline; LBS is the smoother version

???
Keep this as the Part 2 equivalent of the block-character motivation slide.
The point is not to introduce new motion yet; it is to change how the visible
surface follows the motion they already made.

---

# Skinning

{{youtube: https://youtu.be/3RSwjZLClRc?t=227 | 3D Rigging is Beautiful, Here's How It Works! | A second pass focused on skinning: how the surface follows a rig instead of moving as separate rigid parts.}}

???
Show a short excerpt starting at the skinning/deformation portion. Connect it
directly to the coding contrast students will implement: one-hot attachment
versus linear blend skinning on the same skeleton motion.

---

# Part 2: Skinning And SMPL

{{bullets: ../docs/part2.md#Learning Goals}}

Same motion, different character surface.

???
Keep returning to the contrast: the skeleton pose may be identical, while the
surface behavior changes because the mesh is attached differently.

---

# Inputs To Skinning

- `model_data.rest_vertices`: mesh vertices in the default pose, shape `(V, 3)`
- `model_data.rest_joints`: joint centres in the default pose, shape `(J, 3)`
- `model_data.ground_translation`: shift that puts the rest body on the floor
- `world_rotations`: posed joint rotations from FK, shape `(J, 3, 3)`
- `world_positions`: posed joint centres from FK, shape `(J, 3)`
- `model_data.skinning_weights`: vertex-to-joint weights, shape `(V, J)`

???
Use this slide to demystify the function signature before showing any formula.
The important split is that `model_data` describes the unanimated character,
while `world_rotations` and `world_positions` describe the current animation
pose.

---

# Local Coordinates

Local coordinates are measured in a moving parent frame.

- `joint.translation`: offset from parent joint to child joint
- `local_rotations[j]`: how joint `j` rotates relative to its parent
- if the parent turns, the child's local axes turn with it

???
Use a physical gesture here: your forearm direction is local to the upper arm.
When the shoulder turns, the elbow and forearm coordinate frame move with it.
The local numbers can stay the same while the world-space result changes.

---

# World Coordinates

World coordinates are measured in the fixed viewer scene.

- one shared origin and axis system for the whole character
- `world_positions[j]`: final scene position of joint `j`
- `world_rotations[j]`: final scene orientation of joint `j`
- the renderer draws points after they are in world coordinates

???
Contrast this with local coordinates. World coordinates answer "where is this
point on the screen/in the scene now?" Local coordinates answer "where is this
point relative to the parent frame?"

---

# FK Converts Local To World

For a child joint `j` with parent `p`:

```text
world_rotations[j] = world_rotations[p] @ local_rotations[j]
world_positions[j] = world_positions[p]
                     + world_rotations[p] @ joint.translation
```

???
This is the Part 1 recurrence in compact form. The parent rotation matters in
the position line because the child offset is written in the parent's local
coordinate frame.

---

# Why Skinning Uses World Transforms

Local rotations are the controls; world transforms are the result.

- a hand vertex is affected by shoulder, elbow, and wrist motion
- the wrist's local rotation alone does not include its parent joints
- after FK, each joint has a final world position and orientation
- skinning uses that final joint frame to move nearby vertices

???
This is the key distinction. Students should not try to skin directly with
`local_rotations[j]`, because that would ignore the accumulated motion of the
parent chain. Local rotations are still important: FK turns them into the
world-space joint frames used by skinning.

---

# Rest Vertices And Rest Joints

The rest pose is the character before animation.

- `rest_vertices[i]`: where mesh vertex `i` starts in rest pose
- `rest_joints[j]`: where joint `j` starts in rest pose
- add `ground_translation` so both are in viewer world coordinates
- `rest_vertices[i] - rest_joints[j]`: vertex `i` as seen from joint `j`

???
This is the conceptual step students often miss. A joint does not rotate an
absolute scene point directly; it rotates the offset from that joint to the
vertex, then places the result back at the posed joint location.

---

# World Positions And Rotations

Forward kinematics has already accumulated the hierarchy.

- `world_positions[j]`: where joint `j` is in the current pose
- `world_rotations[j]`: how joint `j` is oriented in the current pose
- these are the posed world-space transforms from Part 1 FK

???
Tie this back to Part 1. Their FK code already converted local rotations into
world rotations and world positions. Part 2 consumes those results rather than
recomputing the skeleton hierarchy.

---

# The Skinning Transform

Each joint gives vertex `i` one possible posed location.

- start from the vertex's rest-pose offset from that joint
- rotate that offset using the joint's posed world rotation
- place the rotated offset at the joint's posed world position
- combine the joint proposals using the skinning weights

???
Keep this conceptual. Do not write the final array expression on the slide:
students should still decide how to combine `rest_vertices`, `rest_joints`,
`world_rotations`, `world_positions`, and the weights in their implementation.
One-hot skinning keeps the proposal from the most important joint. LBS takes
the weighted average of all joint proposals.

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

Deadline: Friday 29 May 2026, 2pm.

{{bullets: ../docs/interim.md#What To Submit}}

[Submit on Moodle](https://www.vle.cam.ac.uk/mod/assign/view.php?id=19560071)

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
- use the [Git starter](https://rogerdudler.github.io/git-guide/) if Git
  commands are new

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
- [FAQ](faq.html)
- [References](references.html)
- [Project repository](https://github.com/CambridgeCVCourses/IIA-Project-GF5)

???
End by sending students to setup and Part 1, then leave time for viewer setup
questions.
