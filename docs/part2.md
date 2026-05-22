# Part 2: Skinning Weights, One-Hot Binding, and SMPL

## Why This Part Matters

In Part 1, each block was attached rigidly to one joint. That was useful for
learning FK, but it is not how real character surfaces behave.

A deformable mesh bends because vertices near a joint are influenced by more
than one bone. Part 2 studies that idea directly using SMPL, a standard human
body model with a realistic mesh and skinning weights.

The key question for this part is:

How much of the final animation comes from the skeleton pose, and how much
comes from the way the mesh is attached to that skeleton?

## Learning Goals

By the end of Part 2, you should be able to:

- explain what a skinning weight means
- derive one-hot skinning from a full weight matrix
- explain why one-hot attachment creates artifacts near elbows, shoulders, hips,
  and knees
- compare one-hot binding against linear blend skinning (LBS)
- reuse the same motion on both the toy character and SMPL

## Minimal Technical Background

### Rest Pose

The rest pose is the default unposed mesh and skeleton.

Skinning starts with:

- a rest-pose mesh
- a skeleton
- a set of per-vertex weights

### Skinning Weights

For each vertex `v_i`, the model stores weights `w_ij` telling us how strongly
joint `j` influences that vertex.

The weights are usually non-negative and sum to `1`.

### One-Hot Skinning

One-hot skinning is the simplest baseline:

- find the joint with the largest weight for each vertex
- set that joint's weight to `1`
- set all other weights to `0`

This creates rigid piecewise motion. It is easy to implement and easy to
interpret, which is why it is a good first baseline.

### Linear Blend Skinning

In LBS, a posed vertex is a weighted sum of the transforms from several joints:

```text
v'_i = sum_j w_ij T_j v_i
```

You do not need to derive the full production form of LBS in this part, but you
do need to understand the idea: vertices near joints are shared across
influences instead of being assigned to a single bone.

### SMPL

SMPL is a standard articulated human body model used widely in graphics and
vision. In this project it gives us:

- a human mesh
- a standard skeleton
- a realistic set of skinning weights

That makes it a good bridge from the simple Part-1 rig to a more realistic
animation pipeline.

## SMPL Model Setup

SMPL model files are not included in the repository. To use the SMPL character
in Part 2, download the standard SMPL body model from the
[SMPL website](https://smpl.is.tue.mpg.de/index.html):

1. register or sign in, and accept the SMPL model licence
2. open the `Downloads` page
3. choose `Download version 1.1.0 for Python 2.7 (female/male/neutral, 300 shape PCs)`
4. unzip the archive
5. copy or move the extracted `smpl/` folder into `assets/`

The final layout should be:

```text
assets/smpl/
assets/smpl/models/
```

You do not need SMPL-X, SMPL+H, MANO, or the Blender/Unreal/Maya plugin
downloads for this coursework. You also do not need to run Python 2.7; this is
just the official SMPL download label for the `.pkl` model files we use.

The neutral model is enough for GF5; the male and female `.pkl` files are
optional.

## Code Map

The main files for this part are:

- `viewer/asset_viewer.py`
- `viewer/smpl_support.py`
- `viewer/student_submission/part2_skinning.py`
- `viewer/skeleton_profiles.py`

The viewer already supports:

- loading SMPL
- visualising one-hot and LBS results
- visualising skinning weights
- exporting videos
- reusing saved motion clips from Part 1

## Part 2 Tasks

### Task 1: Load SMPL and Reuse Your Part-1 Motion

Take the motion you created in Part 1 and run it on:

- one block character
- SMPL

This is important: the motion should stay the same. What changes now is the
character model and the mesh attachment.

### Task 2: Implement SMPL One-Hot Skinning

Implement the one-hot version of skinning for SMPL.

Requirements:

- start from the provided SMPL weight matrix
- assign each vertex to the single joint with the maximum weight
- do not hardcode a precomputed one-hot mesh file

This task should produce a deliberately limited baseline that is useful for
comparison.

### Task 3: Implement SMPL Linear Blend Skinning

Implement linear blend skinning for SMPL using the provided weight matrix and
posed joint transforms.

Requirements:

- use the provided SMPL weights directly
- compute the posed vertex positions from the weighted combination of joint
  transforms
- do not use a hidden pre-written skinning helper in the student version

You are not being asked to rebuild the full SMPL model. The task is the
skinning stage only.

### Task 4: Compare One-Hot Against LBS

Use the viewer to compare:

- one-hot SMPL
- LBS SMPL

Use the same motion on both.

You should examine at least two stress regions, for example:

- elbow
- shoulder
- knee
- hip

You should also inspect skinning-weight visualisations for at least two joints.

### Task 5: Produce Evidence, Not Just Code

By the end of Part 2, you should have concrete results, not just an
implementation.

At minimum, collect:

- one short video of your custom motion on the toy rig
- one short video showing the same motion on SMPL
- side-by-side comparisons of one-hot and LBS on at least two challenging poses
- at least two weight visualisations for selected joints

The interim checkpoint is specified separately in the
[Interim Report](interim.md) handout.

## Self-Check Questions

These questions are for your own understanding and revision. They are not
required report questions.

If you can answer them clearly, you are probably on the right track:

- Why is one-hot attachment a useful baseline even though it looks worse?
- Why do artifacts appear mainly near joints rather than in the middle of a
  limb segment?
- Why can the same motion look acceptable on the toy rig but poor on one-hot
  SMPL?
- Why are skinning weights properties of the character model, not of the motion
  clip?

## What To Bring To Help Sessions

Bring one specific artifact or failure case, not just a general complaint.

Good examples:

- "the elbow collapses in one-hot mode but looks smoother with LBS"
- "my one-hot assignment seems to use the wrong dominant joint near the shoulder"
- "the motion transfers correctly, but the deformation near the knee looks too rigid"

Those are much easier to diagnose than "SMPL looks wrong".
