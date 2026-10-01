"""Headless tests for the muscle rig.

Run with either:

    python tests/test_muscle_rig.py            # `pip install bpy` module
    blender -b --factory-startup -P tests/test_muscle_rig.py

No pytest needed (Blender's bundled Python does not ship it). Exit code is the
number of failed tests. ``--perf`` also prints frame timings.
"""

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import demo_scene  # noqa: E402
from _runner import run  # noqa: E402
from muscle_rig import api, build, bulge, jiggle, weights  # noqa: E402
from muscle_rig.library import SETS  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


class Scene:
    """The default demo scene, built once and shared by the read-only tests."""

    def __init__(self, sets=("arm", "chest", "hand")):
        t = time.perf_counter()
        self.meta, self.rig, self.body, self.built, painted = demo_scene.build(sets=sets)
        self.painted = painted[self.body.name]
        self.build_seconds = time.perf_counter() - t
        for side in (".L", ".R"):
            demo_scene.set_fk(self.rig, side)
        self.rest_pose()

    def rest_pose(self):
        for side in (".L", ".R"):
            demo_scene.pose_arm(self.rig, side)
        for pb in self.rig.pose.bones:
            for k in pb.keys():
                if k.startswith(build.FLEX_PREFIX):
                    pb[k] = 0.0

    def coords(self, muscles=True, jiggle_on=False):
        demo_scene.set_muscles_enabled(self.body, muscles, jiggle=jiggle_on)
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        ev = self.body.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        nor = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("normal", nor)
        ev.to_mesh_clear()
        return co.reshape(-1, 3), nor.reshape(-1, 3)

    def mask(self, name, threshold=0.5):
        vg = self.body.vertex_groups[name]
        return np.array([v.index for v in self.body.data.vertices
                         if any(g.group == vg.index and g.weight > threshold for g in v.groups)])

    def activation(self, muscle, side=".L"):
        bpy.context.view_layer.update()
        return self.rig.pose.bones[f"MCH-MUS-{muscle}{side}"].matrix.to_scale().x


def push(scene, mask_name, **pose):
    """Signed push of the muscle's masked skin along its normals (metres)."""
    for side in (".L", ".R"):
        demo_scene.pose_arm(scene.rig, side, **pose)
    off, nor = scene.coords(muscles=False)
    on, _ = scene.coords(muscles=True)
    idx = scene.mask(mask_name)
    d = on[idx] - off[idx]
    scene.rest_pose()
    return np.einsum("ij,ij->i", d, nor[idx]), np.linalg.norm(on - off, axis=1)


# --------------------------------------------------------------------------
# Structure


@test
def test_bones_built(s):
    n = sum(len(SETS[k].muscles) for k in ("arm", "chest", "hand")) * 2
    assert len(s.built) == n, (len(s.built), n)
    mus = [b for b in s.rig.data.bones if b.name.startswith("MCH-MUS-")]
    assert len(mus) == 2 * n, len(mus)
    assert not any(b.use_deform for b in mus), "muscle bones must not deform"
    coll = s.rig.data.collections_all[build.COLL_MCH]
    assert not coll.is_visible


@test
def test_modifier_order(s):
    names = [m.name for m in s.body.modifiers]
    assert names[:3] == ["Armature", bulge.MODIFIER_NAME, jiggle.MODIFIER_NAME], names


@test
def test_masks_painted_both_sides(s):
    for spec, side in s.built:
        assert spec.mask_name(side) in s.painted, spec.mask_name(side)
    for spec in SETS["arm"].muscles:
        nl = s.painted[spec.mask_name(".L")][0]
        nr = s.painted[spec.mask_name(".R")][0]
        assert abs(nl - nr) <= max(3, 0.02 * nl), (spec.name, nl, nr)


@test
def test_skin_weights_untouched(s):
    """The rig's own DEF weights must be identical with and without muscles."""
    base = weights.deform_group_names(s.body, s.rig)
    before = weights._read_weights(s.body, base)
    api.apply(s.rig, ("arm", "chest", "hand"), meshes=[s.body])
    after = weights._read_weights(s.body, base)
    assert np.array_equal(before, after)
    assert not any(vg.name.startswith("DEF-MUS-") for vg in s.body.vertex_groups)


# --------------------------------------------------------------------------
# Behaviour


@test
def test_rest_pose_unchanged(s):
    off, _ = s.coords(muscles=False)
    on, _ = s.coords(muscles=True)
    assert np.abs(on - off).max() < 1e-5, np.abs(on - off).max()


@test
def test_elbow_flex_contracts_biceps_stretches_triceps(s):
    demo_scene.pose_arm(s.rig, ".L", elbow=115)
    bi, tri = s.activation("biceps"), s.activation("triceps")
    br = s.activation("brachioradialis")
    s.rest_pose()
    assert bi > 1.15, bi
    assert br > 1.15, br
    assert tri < 0.99, tri


@test
def test_shoulder_raise_contracts_deltoid(s):
    demo_scene.pose_arm(s.rig, ".L", abduct=60)
    mid = s.activation("deltoid_mid")
    s.rest_pose()
    assert mid > 1.15, mid


@test
def test_wrist_curl_contracts_flexors(s):
    demo_scene.pose_arm(s.rig, ".L", wrist=70)
    fl, ex = s.activation("forearm_flexors"), s.activation("forearm_extensors")
    s.rest_pose()
    assert fl > 1.05, fl
    assert fl > ex, (fl, ex)


@test
def test_biceps_pushes_skin_outward(s):
    signed, _ = push(s, "MUS-biceps.L", elbow=115)
    assert signed.mean() > 0.005, signed.mean()
    assert signed.min() > -1e-4, signed.min()


@test
def test_triceps_flattens_when_stretched(s):
    signed, _ = push(s, "MUS-triceps.L", elbow=115)
    assert signed.mean() < -0.0005, signed.mean()


@test
def test_twist_alone_does_not_bulge_arm(s):
    """Rigify spreads twist over B-Bone segments; the bulge must not care."""
    _, dist = push(s, "MUS-biceps.L", twist=-90)
    for name in ("MUS-biceps.L", "MUS-triceps.L", "MUS-brachioradialis.L"):
        idx = s.mask(name)
        assert dist[idx].max() < 0.001, (name, dist[idx].max())


@test
def test_bulge_same_with_and_without_twist(s):
    a, _ = push(s, "MUS-biceps.L", abduct=35, twist=-90, elbow=115)
    b, _ = push(s, "MUS-biceps.L", abduct=35, twist=0, elbow=115)
    assert abs(a.mean() - b.mean()) < 0.001, (a.mean(), b.mean())


@test
def test_driver_matches_bone_scale(s):
    demo_scene.pose_arm(s.rig, ".L", elbow=115)
    bpy.context.evaluated_depsgraph_get().update()
    mod = s.body.modifiers[bulge.MODIFIER_NAME]
    value = mod[bulge.input_identifier(mod.node_group, "MUS-biceps.L")]
    amp = s.painted["MUS-biceps.L"][1]
    expected = (s.activation("biceps") - 1.0) * amp
    s.rest_pose()
    assert abs(value - expected) < 1e-5, (value, expected)


@test
def test_flex_slider_bulges_at_rest(s):
    s.rig.pose.bones["upper_arm_parent.L"][build.flex_prop_name("arm", ".L")] = 1.0
    off, nor = s.coords(muscles=False)
    on, _ = s.coords(muscles=True)
    s.rest_pose()
    idx = s.mask("MUS-biceps.L", 0.9)
    signed = np.einsum("ij,ij->i", on[idx] - off[idx], nor[idx])
    spec = next(m for m in SETS["arm"].muscles if m.name == "biceps")
    expected = spec.flex_gain * s.painted["MUS-biceps.L"][1]
    assert signed.max() > 0.8 * expected, (signed.max(), expected)


@test
def test_mirror_symmetry(s):
    for side in (".L", ".R"):
        demo_scene.pose_arm(s.rig, side, abduct=30, elbow=100, wrist=30)
    bpy.context.view_layer.update()
    for spec in SETS["arm"].muscles + SETS["chest"].muscles:
        l, r = s.activation(spec.name, ".L"), s.activation(spec.name, ".R")
        assert abs(l - r) < 1e-3, (spec.name, l, r)
    s.rest_pose()


@test
def test_face_smile_and_jaw(s):
    """Experimental face set: direction of activation only (no face mesh)."""
    from mathutils import Matrix, Vector
    api.apply(s.rig, ("arm", "chest", "hand", "face"), meshes=[s.body])
    pb = s.rig.pose.bones["lips.L"]
    rest = pb.matrix.copy()
    pb.matrix = Matrix.Translation(Vector((0.012, 0.004, 0.012))) @ rest  # corner up + back
    smile = s.activation("zygomaticus")
    pb.matrix = rest
    jaw = s.rig.pose.bones["jaw_master"]
    jaw.rotation_mode = 'XYZ'
    acts = []
    for deg in (-20.0, 20.0):
        jaw.rotation_euler = (np.radians(deg), 0.0, 0.0)
        bpy.context.view_layer.update()
        chin_z = (s.rig.pose.bones["jaw_master"].tail).z
        acts.append((chin_z, s.activation("masseter")))
    jaw.rotation_euler = (0.0, 0.0, 0.0)
    api.apply(s.rig, ("arm", "chest", "hand"), meshes=[s.body])
    print(f"  zygomaticus on smile: {smile:.3f}; masseter (chin z, activation): {acts}")
    assert smile > 1.03, smile
    opened = min(acts)[1]  # the rotation that drops the chin opens the mouth
    assert opened < 0.99, acts


# --------------------------------------------------------------------------
# Jiggle


def _keyframe_swing(rig, side=".L"):
    """Arm snaps up over 5 frames then holds still."""
    from math import radians
    from mathutils import Quaternion
    pb = rig.pose.bones[f"upper_arm_fk{side}"]
    pb.rotation_mode = 'QUATERNION'
    for frame, angle in ((1, 0), (6, 70), (60, 70)):
        pb.rotation_quaternion = Quaternion((0, 0, 1), radians(angle))
        pb.keyframe_insert("rotation_quaternion", frame=frame)


@test
def test_jiggle_lags_then_settles(s):
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 60
    _keyframe_swing(s.rig)
    jig = s.body.vertex_groups[weights.JIGGLE_GROUP]
    jidx = np.array([v.index for v in s.body.data.vertices
                     if any(g.group == jig.index and g.weight > 0.5 for g in v.groups)])
    in_group = {v.index for v in s.body.data.vertices if any(g.group == jig.index for g in v.groups)}
    free = np.array([i for i in range(len(s.body.data.vertices)) if i not in in_group])

    lag = {}
    for frame in range(1, 61):
        scene.frame_set(frame)
        a, _ = s.coords(muscles=True, jiggle_on=False)
        b, _ = s.coords(muscles=True, jiggle_on=True)
        d = np.linalg.norm(b - a, axis=1)
        assert np.isfinite(b).all()
        assert d[free].max() < 1e-6, ("unmasked vertex moved", frame, d[free].max())
        lag[frame] = d[jidx].max()
    s.rig.animation_data_clear()
    scene.frame_set(1)
    s.rest_pose()
    peak = max(lag[f] for f in range(4, 16))
    assert peak > 0.003, ("no visible lag", lag)
    assert lag[60] < 0.25 * peak, ("did not settle", lag[60], peak)
    cap = s.body.modifiers[jiggle.MODIFIER_NAME][jiggle.input_identifier(
        s.body.modifiers[jiggle.MODIFIER_NAME].node_group, "Max Offset")]
    assert max(lag.values()) <= cap + 1e-4, (max(lag.values()), cap)


@test
def test_addon_operator(s):
    """Register the add-on like Blender would and run its main operator."""
    import addon_utils
    mod = addon_utils.enable("muscle_rig", default_set=False)
    assert mod is not None, "add-on failed to enable"
    try:
        assert hasattr(bpy.types, "VIEW3D_PT_muscle_rig")
        bpy.context.scene.muscle_rig.use_hand = True
        bpy.context.view_layer.objects.active = s.body  # a bound mesh is enough
        with bpy.context.temp_override(active_object=s.body, object=s.body):
            assert bpy.ops.muscle_rig.apply.poll()
            assert bpy.ops.muscle_rig.apply() == {'FINISHED'}
        assert "MCH-MUS-thenar.L" in s.rig.data.bones
        assert bulge.MODIFIER_NAME in s.body.modifiers

        # Run the sidebar panel's draw() against a stub layout so Python
        # errors in the UI code show up headless; check the props it draws.
        drawn = []

        class Stub:
            def __getattr__(self, name):
                return lambda *a, **k: self

            def prop(self, data, prop, **k):
                path = prop[2:-2] if prop.startswith('["') else prop
                assert (path in data.keys()) if prop.startswith('["') else hasattr(data, prop), prop
                drawn.append(prop)
                return self

        class Panel:
            layout = Stub()
        bpy.context.view_layer.objects.active = s.rig
        bpy.types.VIEW3D_PT_muscle_rig.draw(Panel(), bpy.context)
        assert any(p.startswith('["muscle_flex_') for p in drawn), drawn
    finally:
        addon_utils.disable("muscle_rig", default_set=False)


# --------------------------------------------------------------------------
# Lifecycle (these rebuild the scene, so they run last)


@test
def test_rebuild_is_idempotent(s):
    def snapshot():
        return (sorted(b.name for b in s.rig.data.bones if b.name.startswith("MCH-MUS-")),
                sorted(vg.name for vg in s.body.vertex_groups),
                [m.name for m in s.body.modifiers],
                len(s.body.animation_data.drivers))
    first = snapshot()
    api.apply(s.rig, ("arm", "chest", "hand"), meshes=[s.body])
    assert snapshot() == first


@test
def test_strip_removes_everything(s):
    api.strip(s.rig, meshes=[s.body])
    assert not [b for b in s.rig.data.bones if b.name.startswith(build.PREFIXES)]
    assert not [vg for vg in s.body.vertex_groups if vg.name.startswith(weights.MASK_PREFIX)]
    assert [m.name for m in s.body.modifiers] == ["Armature"]
    assert not s.body.animation_data or not len(s.body.animation_data.drivers)
    api.apply(s.rig, ("arm", "chest", "hand"), meshes=[s.body])


@test
def test_rigify_regenerate_rebuilds_muscles(s):
    api.install_rigify_hook(s.meta, ("arm", "chest", "hand"))
    s.meta.hide_set(False)
    bpy.context.view_layer.objects.active = s.meta
    s.meta.select_set(True)
    bpy.ops.pose.rigify_generate()
    rig = s.meta.data.rigify_target_rig
    assert rig is s.rig, "Rigify should regenerate into the same object"
    assert "MCH-MUS-biceps.L" in rig.data.bones, "hook did not rebuild the muscles"
    mod = s.body.modifiers[bulge.MODIFIER_NAME]
    demo_scene.pose_arm(rig, ".L", elbow=115)
    bpy.context.evaluated_depsgraph_get().update()
    assert mod[bulge.input_identifier(mod.node_group, "MUS-biceps.L")] > 0.005
    s.rest_pose()


# --------------------------------------------------------------------------


def measure_performance(s, frames=48):
    """Average depsgraph evaluation time per frame for three setups."""
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, frames
    _keyframe_swing(s.rig)
    results = {}
    for label, muscles, jig in (("rigify_only", False, False), ("bulge", True, False),
                                ("bulge_jiggle", True, True)):
        demo_scene.set_muscles_enabled(s.body, muscles, jiggle=jig)
        scene.frame_set(1)
        dg = bpy.context.evaluated_depsgraph_get()
        t = time.perf_counter()
        for frame in range(1, frames + 1):
            scene.frame_set(frame)
            s.body.evaluated_get(dg)  # frame_set already evaluated everything
        results[label] = (time.perf_counter() - t) / frames * 1000.0
    s.rig.animation_data_clear()
    scene.frame_set(1)
    s.rest_pose()
    return results


def main():
    print(f"Blender {bpy.app.version_string}")
    s = Scene()
    print(f"scene: {len(s.body.data.vertices)} verts, {len(s.built)} muscles, built in {s.build_seconds:.1f}s")
    failed = 0
    for fn in TESTS:
        t = time.perf_counter()
        try:
            fn(s)
            print(f"PASS {fn.__name__} ({time.perf_counter() - t:.1f}s)")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    if "--perf" in sys.argv:
        for label, ms in measure_performance(s).items():
            print(f"PERF {label}: {ms:.1f} ms/frame")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    return failed


if __name__ == "__main__":
    run(main)
