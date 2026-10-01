"""Headless demo scene: Rigify human rig + a procedural mannequin skin.

Used by the tests and the render script, and handy as a sandbox:

    blender -b -P scripts/demo_scene.py -- --out demo.blend
    python scripts/demo_scene.py --out demo.blend   # with the `bpy` pip module

The mannequin is a metaball torso/head/hands plus smooth tapered tubes for the
limbs, fused by a voxel remesh, plus separate finger tubes. Skin weights are
a simple inverse-distance fit to the DEF bones: deterministic and good enough
to test the muscle layer; a real character would use its own painted weights.
"""

import os
import re
import sys

import bpy
import numpy as np
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MB_SURFACE = 0.575  # metaball surface radius / element radius (threshold 0.6)

# Limb chains as (bones, radius profile [(fraction of chain length, radius)]).
CHAINS = {
    "arm": (("upper_arm", "forearm"),
            ((0.0, 0.050), (0.12, 0.050), (0.33, 0.045), (0.50, 0.037), (0.60, 0.041),
             (0.80, 0.033), (1.0, 0.026))),
    "leg": (("thigh", "shin"),
            ((0.0, 0.085), (0.30, 0.074), (0.52, 0.050), (0.62, 0.056), (0.85, 0.042),
             (1.0, 0.035))),
}
# metarig bone -> (surface radius at head, at tail), metaball capsules
BLOBS = {
    "shoulder": (0.045, 0.050),
    "hand": (0.026, 0.024),
    "foot": (0.036, 0.030),
    "toe": (0.026, 0.020),
    "thumb.01": (0.017, 0.013),
}
PALM = (0.014, 0.012)
FINGER = {"thumb": 0.011, "f_index": 0.0085, "f_middle": 0.0088, "f_ring": 0.0082, "f_pinky": 0.0072}
THUMB_IN = (20.0, 0.0, 40.0)  # degrees XYZ on thumb.01 at amount 1 (thenar ~1.15)
BODY_DEF = re.compile(r"^DEF-(spine|shoulder|upper_arm|forearm|hand|palm|thumb|f_|thigh|shin|foot|toe)")


def reset():
    import addon_utils
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("rigify", default_set=True)
    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, 72
    return scene


def make_rig():
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.active_object
    meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
    bpy.ops.pose.rigify_generate()
    rig = meta.data.rigify_target_rig
    meta.hide_set(True)
    return meta, rig


def _capsule(mb, a, b, r):
    a, b = Vector(a), Vector(b)
    d = b - a
    el = mb.elements.new(type='CAPSULE')
    el.co = (a + b) / 2
    el.radius = r / MB_SURFACE
    el.size_x = d.length / 2
    el.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())
    el.stiffness = 2.0


def _tapered(mb, a, b, r0, r1, steps=3):
    a, b = Vector(a), Vector(b)
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        _capsule(mb, a.lerp(b, t0), a.lerp(b, t1), r0 + (r1 - r0) * (t0 + t1) / 2)


def _body_metaball(meta):
    bones = meta.data.bones
    mb = bpy.data.metaballs.new("MannequinMB")
    mb.resolution = mb.render_resolution = 0.012
    mb.threshold = 0.6

    def hl(n):
        return bones[n].head_local

    def tl(n):
        return bones[n].tail_local

    # Torso: spine chain plus wide horizontal capsules for hips/waist/chest.
    _tapered(mb, hl("spine"), tl("spine.003"), 0.10, 0.11, steps=4)
    for z, half, r, y in ((1.02, 0.08, 0.11, 0.03), (1.20, 0.07, 0.10, 0.01),
                          (1.38, 0.08, 0.115, -0.005), (1.52, 0.10, 0.11, 0.0)):
        _capsule(mb, (-half, y, z), (half, y, z), r)
    _tapered(mb, hl("spine.004"), tl("spine.005"), 0.055, 0.05, steps=2)
    _capsule(mb, hl("spine.006") + Vector((0, -0.01, 0.07)), tl("spine.006") - Vector((0, 0, 0.08)), 0.095)

    for side in (".L", ".R"):
        for name, (r0, r1) in BLOBS.items():
            _tapered(mb, hl(name + side), tl(name + side), r0, r1)
        for i in range(1, 5):
            n = f"palm.0{i}{side}"
            _capsule(mb, hl(n), tl(n), PALM[0] if i < 4 else PALM[1])
    return mb


def _tube(verts, faces, a, b, r0, r1, rings=8, segs=10):
    """Closed tube from a to b (radius r0 -> r1) appended to verts/faces."""
    axis = (b - a).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    w = axis.cross(u)
    base = len(verts)
    for i in range(rings + 1):
        t = i / rings
        c = a.lerp(b, t)
        r = r0 + (r1 - r0) * t
        for j in range(segs):
            ang = 2 * np.pi * j / segs
            verts.append(c + (u * np.cos(ang) + w * np.sin(ang)) * r)
    for i in range(rings):
        for j in range(segs):
            k0 = base + i * segs + j
            k1 = base + i * segs + (j + 1) % segs
            faces.append((k0, k1, k1 + segs, k0 + segs))
    for end, ring, flip in ((a - axis * r0 * 0.6, 0, True), (b + axis * r1 * 0.6, rings, False)):
        verts.append(end)
        ci = len(verts) - 1
        for j in range(segs):
            k0 = base + ring * segs + j
            k1 = base + ring * segs + (j + 1) % segs
            faces.append((ci, k1, k0) if flip else (ci, k0, k1))


def _chain_tube(verts, faces, points, profile, segs=28, spacing=0.008):
    """Smooth closed tube along a polyline with an interpolated radius."""
    pts = [Vector(p) for p in points]
    seg_len = [(b - a).length for a, b in zip(pts, pts[1:])]
    total = sum(seg_len)
    n = max(2, int(total / spacing))
    ts, rs = zip(*profile)
    rings = []
    for i in range(n + 1):
        d = total * i / n
        k = 0
        while k < len(seg_len) - 1 and d > seg_len[k]:
            d -= seg_len[k]
            k += 1
        f = min(d / seg_len[k], 1.0)
        c = pts[k].lerp(pts[k + 1], f)
        axis = (pts[k + 1] - pts[k]).normalized()
        rings.append((c, axis, float(np.interp(i / n, ts, rs))))
    base = len(verts)
    for c, axis, r in rings:
        ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
        u = axis.cross(ref).normalized()
        w = axis.cross(u)
        for j in range(segs):
            ang = 2 * np.pi * j / segs
            verts.append(c + (u * np.cos(ang) + w * np.sin(ang)) * r)
    for i in range(n):
        for j in range(segs):
            k0 = base + i * segs + j
            k1 = base + i * segs + (j + 1) % segs
            faces.append((k0, k1, k1 + segs, k0 + segs))
    for (c, axis, r), ring, flip in ((rings[0], 0, True), (rings[-1], n, False)):
        verts.append(c + axis * (r * 0.5 if not flip else -r * 0.5))
        ci = len(verts) - 1
        for j in range(segs):
            k0 = base + ring * segs + j
            k1 = base + ring * segs + (j + 1) % segs
            faces.append((ci, k1, k0) if flip else (ci, k0, k1))


def _limb_mesh(meta):
    bones = meta.data.bones
    verts, faces = [], []
    for side in (".L", ".R"):
        for chain, profile in CHAINS.values():
            pts = [bones[chain[0] + side].head_local] + [bones[b + side].tail_local for b in chain]
            _chain_tube(verts, faces, pts, profile)
    me = bpy.data.meshes.new("Limbs")
    me.from_pydata([v[:] for v in verts], [], faces)
    me.update()
    return me


def _finger_mesh(meta):
    """One tube per finger chain (separate islands from the body)."""
    bones = meta.data.bones
    verts, faces = [], []
    for side in (".L", ".R"):
        for finger, r in FINGER.items():
            first = 2 if finger == "thumb" else 1  # thumb.01 is a metaball blob
            a = bones[f"{finger}.0{first}{side}"].head_local
            b = bones[f"{finger}.03{side}"].tail_local
            _tube(verts, faces, a, b, r, r * 0.85)
    me = bpy.data.meshes.new("Fingers")
    me.from_pydata([v[:] for v in verts], [], faces)
    me.update()
    return me


def make_body(meta, rig, voxel=0.008):
    scene = bpy.context.scene
    mb = _body_metaball(meta)
    mb_obj = bpy.data.objects.new("MannequinMB", mb)
    scene.collection.objects.link(mb_obj)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(mb_obj.evaluated_get(dg))
    bpy.data.objects.remove(mb_obj)
    bpy.data.metaballs.remove(mb)

    import bmesh
    limbs = _limb_mesh(meta)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.from_mesh(limbs)
    bm.to_mesh(me)
    bm.free()
    bpy.data.meshes.remove(limbs)

    body = bpy.data.objects.new("Mannequin", me)
    scene.collection.objects.link(body)
    rm = body.modifiers.new("Remesh", 'REMESH')
    rm.mode, rm.voxel_size, rm.adaptivity = 'VOXEL', voxel, 0.0
    sm = body.modifiers.new("Smooth", 'SMOOTH')
    sm.factor, sm.iterations = 0.5, 6
    dg = bpy.context.evaluated_depsgraph_get()
    remeshed = bpy.data.meshes.new_from_object(body.evaluated_get(dg))
    body.modifiers.clear()
    body.data = remeshed
    bpy.data.meshes.remove(me)

    fingers = _finger_mesh(meta)
    n_body = len(remeshed.vertices)
    bm = bmesh.new()
    bm.from_mesh(remeshed)
    bm.from_mesh(fingers)
    bm.to_mesh(remeshed)
    bm.free()
    bpy.data.meshes.remove(fingers)
    for p in remeshed.polygons:
        p.use_smooth = True

    _fit_weights(body, rig, finger_start=n_body)
    body.parent = rig
    mod = body.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    return body


def _segment_distance(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + np.outer(t, ab)), axis=1)


def _fit_weights(body, rig, finger_start, power=6.0, keep=3):
    me = body.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    bones = [b for b in rig.data.bones if b.use_deform and BODY_DEF.match(b.name)]
    names = [b.name for b in bones]
    D = np.stack([_segment_distance(co, np.array(b.head_local), np.array(b.tail_local)) for b in bones], axis=1)

    # Finger islands only listen to their own chain (+ hand) so neighbours
    # do not pull on them.
    finger_cols = [i for i, n in enumerate(names) if re.match(r"DEF-(thumb|f_)", n)]
    is_finger = np.arange(len(co)) >= finger_start
    nearest_finger = np.array(finger_cols)[D[:, finger_cols].argmin(axis=1)]
    for v in np.nonzero(is_finger)[0]:
        chain = names[nearest_finger[v]].split(".")[0]  # e.g. DEF-f_index
        side = names[nearest_finger[v]][-2:]
        allowed = [i for i, n in enumerate(names) if n.startswith(chain) and n.endswith(side)]
        mask = np.full(len(names), np.inf)
        mask[allowed] = D[v, allowed]
        D[v] = mask
    # The body keeps DEF-thumb.01 (the thumb base is part of the palm blob).
    body_excluded = [i for i in finger_cols if not names[i].startswith("DEF-thumb.01")]
    D[np.ix_(~is_finger, body_excluded)] = np.inf

    W = 1.0 / np.maximum(D, 1e-4) ** power
    order = np.argsort(-W, axis=1)
    W2 = np.zeros_like(W)
    rows = np.arange(len(co))[:, None]
    W2[rows, order[:, :keep]] = W[rows, order[:, :keep]]
    W2 /= W2.sum(axis=1, keepdims=True)
    for j, name in enumerate(names):
        idx = np.nonzero(W2[:, j] > 1e-3)[0]
        if len(idx) == 0:
            continue
        vg = body.vertex_groups.new(name=name)
        for i in idx:
            vg.add([int(i)], float(W2[i, j]), 'REPLACE')


def make_material(body, color=(0.75, 0.58, 0.48, 1.0)):
    mat = bpy.data.materials.new("Skin")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.55
    body.data.materials.append(mat)


def build(with_muscles=True, sets=("arm", "chest", "hand")):
    reset()
    meta, rig = make_rig()
    body = make_body(meta, rig)
    make_material(body)
    built = stats = None
    if with_muscles:
        from muscle_rig import api
        built, stats = api.apply(rig, sets, meshes=[body])
    return meta, rig, body, built, stats


def set_fk(rig, side=".L"):
    pb = rig.pose.bones.get(f"upper_arm_parent{side}")
    if pb is not None and "IK_FK" in pb:
        pb["IK_FK"] = 1.0


def pose_arm(rig, side=".L", abduct=0.0, twist=0.0, swing=0.0, elbow=0.0, wrist=0.0):
    """FK arm pose in degrees on the stock metarig axes.

    abduct: raise sideways (+ = up), twist: roll the upper arm (- = external),
    swing: forward (+) / back (-), elbow: flexion, wrist: flexion toward palm.
    """
    from math import radians
    from mathutils import Quaternion
    if side.endswith("R"):  # Blender mirrors poses by negating Y/Z rotation
        abduct, twist = -abduct, -twist
    set_fk(rig, side)
    pb = rig.pose.bones
    ua = pb[f"upper_arm_fk{side}"]
    ua.rotation_mode = 'QUATERNION'
    ua.rotation_quaternion = (Quaternion((1, 0, 0), radians(swing))
                              @ Quaternion((0, 0, 1), radians(abduct))
                              @ Quaternion((0, 1, 0), radians(twist)))
    fa = pb[f"forearm_fk{side}"]
    fa.rotation_mode = 'XYZ'
    fa.rotation_euler = (radians(elbow), 0, 0)
    hd = pb[f"hand_fk{side}"]
    hd.rotation_mode = 'XYZ'
    hd.rotation_euler = (radians(wrist), 0, 0)


def pose_thumb(rig, side=".L", amount=0.0):
    """Swing the thumb across the palm (0 = rest, 1 = fully in)."""
    from math import radians
    pb = rig.pose.bones.get(f"thumb.01{side}")
    if pb is None:
        return
    pb.rotation_mode = 'XYZ'
    sign = -1.0 if side.endswith("R") else 1.0
    pb.rotation_euler = (radians(THUMB_IN[0] * amount), radians(THUMB_IN[1] * amount * sign),
                         radians(THUMB_IN[2] * amount * sign))


def set_muscles_enabled(body, enabled, jiggle=None):
    """Toggle the bulge (and optionally jiggle) modifiers: off == plain Rigify."""
    for name, on in (("MUS Bulge", enabled), ("MUS Jiggle", enabled if jiggle is None else jiggle)):
        mod = body.modifiers.get(name)
        if mod is not None:
            mod.show_viewport = mod.show_render = on


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ROOT, "demo.blend")
    meta, rig, body, built, stats = build()
    set_fk(rig, ".L")
    set_fk(rig, ".R")
    print("verts", len(body.data.vertices), "muscles", len(built), stats)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("saved", out)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _runner import run
    run(main)
