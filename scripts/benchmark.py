"""Frame-evaluation cost of the muscle layer vs. a clean Rigify setup.

    python scripts/benchmark.py [--voxels 0.012,0.008,0.006] [--frames 96]

For each mannequin density it times (min of 3 runs, ms per frame, headless,
no drawing) the same 96-frame arm animation with:
  clean   - Rigify rig + mesh, no muscle system at all
  bones   - + muscle bones, masks and drivers, deformers disabled
  bulge   - + bulge modifier
  jiggle  - + bulge + jiggle simulation
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))

import bpy  # noqa: E402

import demo_scene  # noqa: E402
from _runner import run  # noqa: E402


def keyframe(rig):
    from math import radians
    from mathutils import Quaternion
    for side in (".L", ".R"):
        demo_scene.set_fk(rig, side)
        ua = rig.pose.bones[f"upper_arm_fk{side}"]
        fa = rig.pose.bones[f"forearm_fk{side}"]
        ua.rotation_mode, fa.rotation_mode = 'QUATERNION', 'XYZ'
        for frame, abduct, elbow in ((1, 0, 0), (24, 60, 110), (48, 10, 20), (72, 70, 90), (96, 0, 0)):
            ua.rotation_quaternion = Quaternion((0, 0, 1), radians(abduct if side == ".L" else -abduct))
            fa.rotation_euler = (radians(elbow), 0, 0)
            ua.keyframe_insert("rotation_quaternion", frame=frame)
            fa.keyframe_insert("rotation_euler", frame=frame)


def timeit(frames, reps=3):
    scene = bpy.context.scene
    best = float("inf")
    for _ in range(reps):
        scene.frame_set(1)
        t = time.perf_counter()
        for f in range(1, frames + 1):
            scene.frame_set(f)
        best = min(best, (time.perf_counter() - t) / frames * 1000.0)
    return best


def scene_for(voxel, muscles):
    demo_scene.reset()
    meta, rig = demo_scene.make_rig()
    body = demo_scene.make_body(meta, rig, voxel=voxel)
    if muscles:
        from muscle_rig import api
        api.apply(rig, ("arm", "chest", "hand"), meshes=[body])
    keyframe(rig)
    return rig, body


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    voxels = [float(v) for v in (argv[argv.index("--voxels") + 1] if "--voxels" in argv
                                 else "0.012,0.008,0.006").split(",")]
    frames = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 96
    print(f"Blender {bpy.app.version_string}, {os.cpu_count()} CPUs")
    print("| verts | clean Rigify | + muscle bones | + bulge | + bulge + jiggle |")
    print("|---:|---:|---:|---:|---:|")
    for voxel in voxels:
        rig, body = scene_for(voxel, muscles=False)
        bpy.context.scene.frame_end = frames
        clean = timeit(frames)
        rig, body = scene_for(voxel, muscles=True)
        bpy.context.scene.frame_end = frames
        res = {}
        for label, bulge, jig in (("bones", False, False), ("bulge", True, False), ("jiggle", True, True)):
            demo_scene.set_muscles_enabled(body, bulge, jiggle=jig)
            res[label] = timeit(frames)
        n = len(body.data.vertices)
        print(f"| {n:,} | {clean:.1f} ms | {res['bones']:.1f} ms | {res['bulge']:.1f} ms | {res['jiggle']:.1f} ms |")


if __name__ == "__main__":
    run(main)
