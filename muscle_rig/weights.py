"""Per-muscle skin masks.

Each muscle gets a vertex group ``MUS-<name><side>``: a smooth tube around
the belly part of its line of action, tapered at both ends and limited to
skin that already belongs to the muscle's region bones. The names never match
a bone, so the Armature modifier ignores them; only the bulge and jiggle
node groups read them. The rig's own skin weights are never touched.

Painting also measures each muscle's push amplitude: how far the masked skin
sits from the host bone axis, capped at the mask radius. Pushing the skin out
by ``(thickness - 1) * amplitude`` is roughly what scaling that limb section
would do; the cap keeps torso muscles (host = spine, far away) sane.
"""

import numpy as np

from .spec import sided

JIGGLE_GROUP = "MUS-jiggle"
MASK_PREFIX = "MUS-"
# Compact copy of the masks read by the bulge node group: for every vertex
# the K strongest muscles as (index, weight) pairs. Reading vertex groups in
# Geometry Nodes converts each one every frame, which was ~4x slower.
TOP_K = 3
IDX_ATTR = "mus_idx{}"
W_ATTR = "mus_w{}"
JIGGLE_ATTR = "mus_jiggle"


def _rest_coords(mesh_obj, rig):
    me = mesh_obj.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(rig.matrix_world.inverted() @ mesh_obj.matrix_world)
    return co @ m[:3, :3].T + m[:3, 3]


def _read_weights(mesh_obj, names):
    """Dense (n_verts, len(names)) array of weights for the given groups."""
    vgs = mesh_obj.vertex_groups
    col = {vgs[n].index: i for i, n in enumerate(names) if n in vgs}
    W = np.zeros((len(mesh_obj.data.vertices), len(names)))
    for v in mesh_obj.data.vertices:
        for g in v.groups:
            i = col.get(g.group)
            if i is not None:
                W[v.index, i] = g.weight
    return W


def _write_group(mesh_obj, name, weights):
    vg = mesh_obj.vertex_groups.get(name)
    if vg is not None:
        mesh_obj.vertex_groups.remove(vg)
    vg = mesh_obj.vertex_groups.new(name=name)
    for i in np.nonzero(weights > 1e-4)[0]:
        vg.add([int(i)], float(weights[i]), 'REPLACE')
    return vg


def deform_group_names(mesh_obj, rig):
    deform = {b.name for b in rig.data.bones if b.use_deform}
    return [vg.name for vg in mesh_obj.vertex_groups if vg.name in deform]


def clear_masks(mesh_obj):
    for vg in [vg for vg in mesh_obj.vertex_groups if vg.name.startswith(MASK_PREFIX)]:
        mesh_obj.vertex_groups.remove(vg)
    clear_baked(mesh_obj)


def muscle_falloff(co, rig, spec, side, region_share):
    """0..1 mask of one muscle belly on every vertex (rest pose).

    A bell (smooth dome) around the belly part of the line of action: peak at
    the belly centre, zero at ``radius`` sideways and half a belly length past
    either end. A dome reads as a muscle; a flat tube reads as an inflated arm.
    """
    line = rig.data.bones[spec.bone_names(side)[0]]
    p0, p1 = np.array(line.head_local), np.array(line.tail_local)
    t0, t1 = spec.belly
    a = p0 + (p1 - p0) * t0
    u = (p1 - p0) * (t1 - t0)
    radius = spec.radius * line.length

    rel = co - a
    s = rel @ u / max(u @ u, 1e-12)
    perp = np.linalg.norm(rel - np.outer(s, u), axis=1)
    radial = np.clip(1.0 - (perp / radius) ** 2, 0.0, 1.0) ** 2
    ext = 0.5
    x = (s - 0.5) / (0.5 + ext)
    along = np.clip(1.0 - x ** 2, 0.0, 1.0) ** 1.5
    return radial * along * region_share


def _axis_distance(co, rig, bone_name):
    b = rig.data.bones[bone_name]
    a = np.array(b.head_local)
    u = np.array(b.tail_local) - a
    s = np.clip((co - a) @ u / max(u @ u, 1e-12), 0.0, 1.0)
    return np.linalg.norm(co - (a + np.outer(s, u)), axis=1)


def paint_masks(mesh_obj, rig, built):
    """Paint ``MUS-*`` vertex groups for ``built`` = [(spec, side), ...].

    The groups are the editable source: repaint them by hand if the
    procedural tube does not fit the character, then call ``bake_masks``.
    """
    clear_masks(mesh_obj)
    co = _rest_coords(mesh_obj, rig)
    base = deform_group_names(mesh_obj, rig)
    Wb = _read_weights(mesh_obj, base)
    base_total = np.maximum(Wb.sum(axis=1), 1e-12)
    col = {n: i for i, n in enumerate(base)}

    jiggle = np.zeros(len(co))
    for spec, side in built:
        region = [col[sided(r, side)] for r in spec.region if sided(r, side) in col]
        share = Wb[:, region].sum(axis=1) / base_total if region else np.ones(len(co))
        f = muscle_falloff(co, rig, spec, side, share) * spec.weight
        if f.max() < 1e-3:
            continue
        _write_group(mesh_obj, spec.mask_name(side), f)
        jiggle += f * spec.jiggle
    _write_group(mesh_obj, JIGGLE_GROUP, np.clip(jiggle, 0.0, 1.0))


def bake_masks(mesh_obj, rig, built):
    """Measure amplitudes and write the compact attributes from the groups.

    Returns ``(order, info)``: ``order`` is the list of (spec, side) whose
    position is the muscle index stored in ``mus_idx*``; ``info`` maps mask
    name -> (vertex count, push amplitude).
    """
    names = [spec.mask_name(side) for spec, side in built]
    present = [i for i, n in enumerate(names) if n in mesh_obj.vertex_groups]
    order = [built[i] for i in present]
    M = _read_weights(mesh_obj, [names[i] for i in present])
    co = _rest_coords(mesh_obj, rig)

    info = {}
    for j, (spec, side) in enumerate(order):
        f = M[:, j]
        if f.max() < 1e-3:
            continue
        dist = _axis_distance(co, rig, sided(spec.host, side))
        radius = spec.radius * rig.data.bones[spec.bone_names(side)[0]].length
        amplitude = min(float((dist * f ** 2).sum() / (f ** 2).sum()), radius)
        info[spec.mask_name(side)] = (int((f > 1e-4).sum()), amplitude)

    me = mesh_obj.data
    k = min(TOP_K, max(M.shape[1], 1))
    top = np.argsort(-M, axis=1)[:, :k] if M.shape[1] else np.zeros((len(co), 0), int)
    for slot in range(TOP_K):
        idx = top[:, slot] if slot < top.shape[1] else np.zeros(len(co), int)
        w = M[np.arange(len(co)), idx] if slot < top.shape[1] else np.zeros(len(co))
        for name, dtype, data in ((IDX_ATTR.format(slot), 'INT', idx.astype(np.int32)),
                                  (W_ATTR.format(slot), 'FLOAT', w.astype(np.float32))):
            attr = me.attributes.get(name)
            if attr is not None:
                me.attributes.remove(attr)
            attr = me.attributes.new(name, dtype, 'POINT')
            attr.data.foreach_set("value", data)

    jig = _read_weights(mesh_obj, [JIGGLE_GROUP])[:, 0].astype(np.float32)
    attr = me.attributes.get(JIGGLE_ATTR)
    if attr is not None:
        me.attributes.remove(attr)
    me.attributes.new(JIGGLE_ATTR, 'FLOAT', 'POINT').data.foreach_set("value", jig)
    return order, info


def clear_baked(mesh_obj):
    me = mesh_obj.data
    for name in [a.name for a in me.attributes if a.name.startswith("mus_")]:
        me.attributes.remove(me.attributes[name])
