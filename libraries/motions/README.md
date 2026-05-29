# Motion Library

The motion scene editor loads Part 3 GF5 `*.motion.json` files from this
library.

Current collections:

- `preset/`: default student-facing Part 3 library, grouped by
  root-use contract: standing gestures, travel loops, travel transitions,
  turns, and special actions.
- `staff_generated/`: optional local additions created by teaching staff.
- `custom/`: user-authored or manually imported clips. This folder is local and is
  ignored by git.

Legacy flat HY-Motion-1.0 inspection exports are staff-side scratch data. If
needed, regenerate them under `staff_tools/motion_generation/`, not under
`libraries/`.

If one or more collection manifests set `load_by_default: true`, the scene
editor loads those manifest-listed files for presets. Custom motions from the
viewer should go under `libraries/motions/custom/`.
