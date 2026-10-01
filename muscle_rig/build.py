"""Add / remove muscle sensor bones on a generated Rigify rig.

Per muscle and side, two non-deforming bones are created:

* ``MCH-MUS-<name>_ins``  tiny target bone parented to the insertion bone.
* ``MCH-MUS-<name>``      origin -> insertion line of action, parented to the
                          origin bone, with a Stretch To (volume preservation
                          XZ) aimed at the target. When the line shortens its
                          X/Z scale grows, when it lengthens it shrinks. That
                          scale is the muscle's "activation"; ``bulge.py``
                          reads it with a driver and pushes the skin.

The bones never deform the mesh, so the rig's own skinning (twist, bends,
B-Bones) is left exactly as Rigify made it. Everything is plain constraints,
so it evaluates in the depsgraph without Python.
"""

import bpy
from mathutils import Vector

from .spec import DIRECTIONS, sided

PREFIXES = ("MCH-MUS-", "DEF-MUS-")  # DEF- kept so old builds get cleaned up
COLL_MCH = "Muscles (MCH)"
FLEX_PREFIX = "muscle_flex_"

# Where the flex sliders live. Rigify already shows the arm's settings bone
# when an arm control is selected, so animators find them next to IK/FK.
PROP_OWNERS = {
    "arm": "upper_arm_parent{s}",
    "forearm": "upper_arm_parent{s}",
    "hand": "upper_arm_parent{s}",
    "chest": "torso",
    "face": "jaw_master",
}
FALLBACK_OWNER = "root"


def flex_prop_name(group, side):
    return f"{FLEX_PREFIX}{group}{side}"


def direction(name, side):
    d = Vector(DIRECTIONS[name])
    if side.endswith("R"):
        d.x = -d.x
    return d


def attach_point(ebones, attach, side):
    eb = ebones[sided(attach.bone, side)]
    p = eb.head.lerp(eb.tail, attach.t)
    for dname, amount in attach.offset:
        p += direction(dname, side) * (amount * eb.length)
    return p


class _Mode:
    """Switch ``obj`` into ``mode`` and restore the previous state on exit."""

    def __init__(self, obj, mode):
        self.obj, self.mode = obj, mode

    def __enter__(self):
        vl = bpy.context.view_layer
        self.prev_active = vl.objects.active
        self.prev_mode = self.obj.mode
        self.prev_hide = self.obj.hide_get()
        self.obj.hide_set(False)
        if self.prev_active is not None and self.prev_active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        vl.objects.active = self.obj
        if self.obj.mode != self.mode:
            bpy.ops.object.mode_set(mode=self.mode)
        return self.obj

    def __exit__(self, *exc):
        if self.obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        self.obj.hide_set(self.prev_hide)
        bpy.context.view_layer.objects.active = self.prev_active
        if self.prev_active is self.obj and self.prev_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=self.prev_mode)
        return False


def _collection(arm, name):
    colls = getattr(arm, "collections_all", arm.collections)
    return colls.get(name)


def ensure_flex_prop(rig, group, side):
    owner = sided(PROP_OWNERS.get(group, FALLBACK_OWNER), side)
    if owner not in rig.pose.bones:
        owner = FALLBACK_OWNER if FALLBACK_OWNER in rig.pose.bones else rig.pose.bones[0].name
    pb = rig.pose.bones[owner]
    prop = flex_prop_name(group, side)
    if prop not in pb:
        pb[prop] = 0.0
    pb.id_properties_ui(prop).update(
        min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
        description=f"Manual muscle tension for the {group}{side} muscles",
    )
    pb.property_overridable_library_set(f'["{prop}"]', True)
    return owner, prop


def remove_muscles(rig):
    """Delete every muscle bone. Flex properties are kept so any animation on
    them survives a rebuild."""
    ad = rig.animation_data
    if ad:
        for fc in list(ad.drivers):
            if any(p in fc.data_path for p in PREFIXES):
                ad.drivers.remove(fc)
    with _Mode(rig, 'EDIT'):
        ebones = rig.data.edit_bones
        for eb in [eb for eb in ebones if eb.name.startswith(PREFIXES)]:
            ebones.remove(eb)
    coll = _collection(rig.data, COLL_MCH)
    if coll is not None and len(coll.bones) == 0:
        rig.data.collections.remove(coll)


def build_muscles(rig, muscle_sets):
    """(Re)build the muscle bones for the given ``MuscleSet`` list.

    Returns a list of ``(spec, side)`` that were built. Muscles whose bones
    are missing on this rig (e.g. no fingers) are skipped with a message.
    """
    remove_muscles(rig)
    built, skipped = [], []
    with _Mode(rig, 'EDIT'):
        ebones = rig.data.edit_bones
        coll = _collection(rig.data, COLL_MCH) or rig.data.collections.new(COLL_MCH)
        coll.is_visible = False
        for mset in muscle_sets:
            for spec in mset.muscles:
                for side in mset.sides:
                    needed = [sided(n, side) for n in
                              (spec.origin.bone, spec.insertion.bone, spec.host)]
                    missing = [n for n in needed if n not in ebones]
                    if missing:
                        skipped.append((spec.name + side, missing))
                        continue
                    _build_edit_bones(ebones, spec, side, coll)
                    built.append((spec, side))

    for spec, side in built:
        _build_pose(rig, spec, side)
    for name, missing in skipped:
        print(f"[muscle_rig] skipped {name}: missing bones {missing}")
    rig["muscle_rig_sets"] = ",".join(m.name for m in muscle_sets)
    return built


def _build_edit_bones(ebones, spec, side, coll):
    n_line, n_ins = spec.bone_names(side)
    a = attach_point(ebones, spec.origin, side)
    b = attach_point(ebones, spec.insertion, side)

    line = ebones.new(n_line)
    line.head, line.tail = a, b
    line.parent = ebones[sided(spec.origin.bone, side)]
    line.use_deform = False
    coll.assign(line)

    ins = ebones.new(n_ins)
    ins.head = b
    ins.tail = b + (b - a) * 0.1
    ins.parent = ebones[sided(spec.insertion.bone, side)]
    ins.use_deform = False
    coll.assign(ins)


def _build_pose(rig, spec, side):
    n_line, n_ins = spec.bone_names(side)
    pb = rig.pose.bones[n_line]
    st = pb.constraints.new('STRETCH_TO')
    st.name = "Muscle Stretch"
    st.target, st.subtarget = rig, n_ins
    st.rest_length = rig.data.bones[n_line].length
    st.volume = 'VOLUME_XZX'
    st.keep_axis = 'SWING_Y'
    st.bulge = spec.bulge
    # In XZ mode each axis is bound to sqrt(limit), so square the per-axis
    # limits from the spec.
    st.use_bulge_min, st.bulge_min = True, spec.bulge_min ** 2
    st.use_bulge_max, st.bulge_max = True, spec.bulge_max ** 2
    ensure_flex_prop(rig, spec.flex_group, side)


def activation(rig, spec, side):
    """Current thickness factor of a muscle (1 = rest), for tests/debug."""
    return rig.pose.bones[spec.bone_names(side)[0]].matrix.to_scale().x
