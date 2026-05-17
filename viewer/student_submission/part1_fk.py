from __future__ import annotations

import numpy as np


def forward_kinematics(
    joints: list[object],
    local_rotations: list[np.ndarray],
    root_offset: np.ndarray,
    topological_order: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Student part-1 implementation.

    Expected inputs:
    - joints: each joint has `.parent` and `.translation`
    - local_rotations: one 3x3 local rotation matrix per joint
    - root_offset: global translation applied to the root
    - topological_order: optional parent-before-child traversal order

    Expected outputs:
    - world_rotations: shape (J, 3, 3)
    - world_positions: shape (J, 3)
    """
    joint_count = len(joints)
    world_rotations = np.tile(
        np.eye(3, dtype=np.float32)[None, :, :],
        (joint_count, 1, 1),
    )
    world_positions = np.zeros((joint_count, 3), dtype=np.float32)
    if topological_order is not None: # this is to decide the processing order, make sure parent first and then child
        order = list(topological_order)
    else:
        
        children = [[] for _ in range(joint_count)] # code to test: order = list(range(joint_count))
        # children[i] is to store all the children of joint i, roots is to store all the root joints with parent=-1
        roots = []         
        for i, joint in enumerate(joints):
            parent = joint.parent
            if parent is None or parent <0:
                roots.append(i)
            else:
                children[parent].append(i)
        order = []
        queue = list(roots) # this is to store the processing order
        while queue:
            i = queue.pop(0)
            order.append(i)
            queue.extend(children[i]) #this part is to deal with roots first, then add the children of the roots, then deal with the childeren and then grandchildren
            
    for i in order:
        joint = joints[i]
        parent = joint.parent
        R_local = local_rotations[i] # this is the rotation of this joint relative to its parent
        t_local = np.array(joint.translation, dtype=np.float32) # tjis is the translation of the joint ralative to its parent
        # judge if the joint is root or not (parent=-1 is root)
        if parent is None or parent <0:
            world_rotations[i] =R_local
            world_positions[i] = t_local + root_offset
        else:
            # for a non-root joint,the formula isR_world(i) = R_world(p(i)) R_local(i)
            #p_world(i) = p_world(p(i)) + R_world(p(i)) t_local(i)
            world_rotations[i] = world_rotations[parent] @ R_local
            world_positions[i] = world_positions[parent] + world_rotations[parent] @ t_local


    return world_rotations, world_positions
