# Setup and Viewer Guide

This is the canonical student setup guide for running the GF5 viewer.

## Create The Environment

From the repository root, create the course environment once:

```bash
mamba env create -f env.yml
```

Then activate it whenever you work on the project:

```bash
mamba activate gf5
```

If the environment already exists and the project has been updated, refresh it:

```bash
mamba env update -f env.yml --prune
```

## Run The Viewer

Start the local viewer from the repository root:

```bash
python viewer/asset_viewer.py
```

This opens the viewer page in your browser automatically.

If the default port is already in use, choose another port:

```bash
python viewer/asset_viewer.py --port 8090
```

For a remote or headless session, suppress automatic browser opening:

```bash
python viewer/asset_viewer.py --no-open-browser
```

Then open the printed `localhost` URL in a browser or forward the printed port
from the remote machine.

## Files You Will Edit

For Part 1, implement forward kinematics in:

```text
viewer/student_submission/part1_fk.py
```

For Part 2, implement one-hot and LBS skinning in:

```text
viewer/student_submission/part2_skinning.py
```

Useful viewer files to read when following data flow:

- `viewer/asset_viewer.py`
- `viewer/motion_sequences.py`
- `viewer/smpl_support.py`
- `viewer/skeleton_profiles.py`

## Main Viewer Controls

- `Motion` and `Animate`: choose and play a built-in or custom motion clip.
- `Show Skeleton` and `Show Mesh`: inspect the rig and visible character
  surface.
- `Selected Joint` and `Joint Editor`: rotate individual joints and debug the
  hierarchy.
- `Timeline`: capture keyframes for the custom Part 1 motion.
- `Export Motion Video`: render evidence videos for the interim submission.

## Local Files And Outputs

The viewer may create local working folders while you experiment:

- `libraries/poses/` and `libraries/motions/custom/`: local poses and custom motions from the viewer
- `exports/`: rendered videos
- `.viewer_imports/`: uploaded character packages

These folders are local outputs, not files you need to submit as source code.

## Git Starter

If Git commands are new to you, use the
[Git starter guide](https://rogerdudler.github.io/git-guide/) as a quick
reference for cloning, committing, pulling, and pushing.

## SMPL Model Files

SMPL is needed for Part 2. The detailed download instructions are in
[Part 2](part2.md#smpl-model-setup). The expected local folder layout is:

```text
assets/smpl/
assets/smpl/models/
```

You can also start the viewer with an explicit model path:

```bash
python viewer/asset_viewer.py --smpl-model /path/to/smpl/model.pkl
```

## Troubleshooting

Run viewer commands from the repository root, the directory containing
`env.yml` and `viewer/`. Running the command from the wrong directory is the
most common cause of `viewer/asset_viewer.py` not being found.

If video export fails, check that `ffmpeg` is installed and available on
`PATH`.

For more setup notes, see the [FAQ](faq.md).

## Next Step

Once the viewer runs, continue to [Part 1](part1.md).
