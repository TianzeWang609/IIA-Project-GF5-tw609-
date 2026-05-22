# Interim Report

The interim report is the main checkpoint after Part 2.

The goal is not to reward code volume. The goal is to show that you understand
the pipeline and can produce and interpret results from your own code.

Deadline: Friday 29 May 2026, 2pm.

Submit the interim report and required results on Moodle:
[https://www.vle.cam.ac.uk/mod/assign/view.php?id=19560071](https://www.vle.cam.ac.uk/mod/assign/view.php?id=19560071)

## Recommended Length

- up to `5` pages of main report content
- use `11 pt` main text
- use single line spacing
- figures and tables included in that limit
- references are not included in that limit
- short appendix only if necessary

## What To Submit

- your code
- your saved custom motion clip
- a short video of the toy-rig motion
- a short video of the same motion on SMPL
- one-hot versus LBS comparison figures
- the interim report PDF

Code and videos are required parts of the interim submission, not optional
supporting material.

## Report Structure

Use these section headings in your report:

1. `Skeleton and Hierarchy`
   Explain what information is stored for each joint and how the parent-child
   relationships are represented.

2. `Forward Kinematics`
   State the FK recurrence you implemented using equations, and explain how
   your code handles the joint hierarchy.

3. `Custom Motion`
   Describe your motion, state how many keyframes you used, and explain why it
   is a useful test case for skinning.

4. `One-Hot Skinning`
   Explain exactly how you converted the SMPL weight matrix into one-hot
   weights, and write down the mathematical rule you used.

5. `Comparison with LBS`
   Compare one-hot SMPL against LBS using the same motion, discuss the main
   visual differences, and write down the LBS equation used for a posed vertex.

6. `Weight Visualisation`
   Interpret at least two selected-joint weight visualisations.

7. `Debugging Notes`
   Include at least one Part-1 debugging note and one Part-2 debugging note.

8. `AI Use Statement`
   State either `No AI tools used`, or describe any limited non-substantive use
   such as spelling checks or environment/setup help.

## Required Figures and Media

Your submission should include all of the following evidence:

- your code
- one short video of your custom motion on the toy rig
- one short video of the same motion on SMPL
- in the PDF: one screenshot of the rigid skeleton or kinematic chain
- in the PDF: at least two one-hot versus LBS comparison images
- in the PDF: at least two selected-joint weight visualisations

The videos should be submitted as separate files. The PDF should use still
figures only where they help explain the method or compare deformation
artifacts.
