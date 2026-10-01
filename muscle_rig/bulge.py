"""Muscle bulge as a Geometry Nodes push along the skin normal.

After the Armature modifier the mesh gets

    offset = normal * sum_k( mus_w{k} * input[mus_idx{k}] ) * Strength

with one float input per muscle and k over the 3 strongest muscles per vertex
(baked by ``weights.bake_masks``; an Index Switch picks the input). The cost
is therefore independent of the number of muscles. Each input is driven by

    (thickness - 1 + flex * gain) * amplitude

where ``thickness`` is the X scale of the muscle's Stretch To line bone,
``flex`` the manual slider and ``amplitude`` the measured distance from the
host bone axis to the masked skin. Drivers are simple expressions, so they
run without Python (no auto-run needed) and evaluate on every frame.
"""

import bpy

from .build import ensure_flex_prop

MODIFIER_NAME = "MUS Bulge"


def _sock(sockets, name):
    for s in sockets:
        if s.name == name and getattr(s, "enabled", True):
            return s
    raise KeyError(name)


def input_identifier(ng, name):
    for item in ng.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == 'INPUT' and item.name == name:
            return item.identifier
    raise KeyError(name)


def build_node_group(rig, mask_names):
    from .weights import IDX_ATTR, TOP_K, W_ATTR

    name = f"MUS_Bulge.{rig.name}"
    ng = bpy.data.node_groups.get(name) or bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.nodes.clear()
    ng.interface.clear()
    iface = ng.interface
    iface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    s = iface.new_socket("Strength", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value, s.min_value, s.max_value = 1.0, 0.0, 5.0
    s.description = "Overall bulge multiplier"
    for mask in mask_names:
        s = iface.new_socket(mask, in_out='INPUT', socket_type='NodeSocketFloat')
        s.description = "Driven: outward push in object units at full mask"
    iface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")
    gi.location, go.location = (-600, 0), (1400, 0)

    acc = None
    for k in range(TOP_K if mask_names else 0):
        idx = nodes.new("GeometryNodeInputNamedAttribute")
        idx.data_type = 'INT'
        _sock(idx.inputs, "Name").default_value = IDX_ATTR.format(k)
        w = nodes.new("GeometryNodeInputNamedAttribute")
        w.data_type = 'FLOAT'
        _sock(w.inputs, "Name").default_value = W_ATTR.format(k)
        switch = nodes.new("GeometryNodeIndexSwitch")
        switch.data_type = 'FLOAT'
        while len(switch.index_switch_items) < len(mask_names):
            switch.index_switch_items.new()
        while len(switch.index_switch_items) > len(mask_names):
            switch.index_switch_items.remove(switch.index_switch_items[-1])
        links.new(_sock(idx.outputs, "Attribute"), switch.inputs[0])
        for i, mask in enumerate(mask_names):
            links.new(_sock(gi.outputs, mask), switch.inputs[i + 1])
        mad = nodes.new("ShaderNodeMath")
        mad.operation = 'MULTIPLY_ADD'
        links.new(_sock(w.outputs, "Attribute"), mad.inputs[0])
        links.new(switch.outputs[0], mad.inputs[1])
        if acc is None:
            mad.inputs[2].default_value = 0.0
        else:
            links.new(acc, mad.inputs[2])
        acc = mad.outputs[0]
        for j, n in enumerate((idx, w, switch, mad)):
            n.location = (200 * j, -300 * k)

    total = nodes.new("ShaderNodeMath")
    total.operation = 'MULTIPLY'
    total.location = (800, 0)
    if acc is not None:
        links.new(acc, total.inputs[0])
    else:
        total.inputs[0].default_value = 0.0
    links.new(_sock(gi.outputs, "Strength"), total.inputs[1])

    normal = nodes.new("GeometryNodeInputNormal")
    normal.location = (800, -200)
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = 'SCALE'
    scale.location = (1000, -100)
    links.new(normal.outputs[0], scale.inputs[0])
    links.new(total.outputs[0], scale.inputs[3])

    setp = nodes.new("GeometryNodeSetPosition")
    setp.location = (1200, 0)
    links.new(_sock(gi.outputs, "Geometry"), _sock(setp.inputs, "Geometry"))
    if mask_names:
        # Only touch skin that has a muscle: ~20% of a body, saves field work.
        w0 = nodes.new("GeometryNodeInputNamedAttribute")
        w0.data_type = 'FLOAT'
        _sock(w0.inputs, "Name").default_value = W_ATTR.format(0)
        w0.location = (800, -400)
        sel = nodes.new("ShaderNodeMath")
        sel.operation = 'GREATER_THAN'
        sel.inputs[1].default_value = 1e-4
        sel.location = (1000, -400)
        links.new(_sock(w0.outputs, "Attribute"), sel.inputs[0])
        links.new(sel.outputs[0], _sock(setp.inputs, "Selection"))
    links.new(scale.outputs[0], _sock(setp.inputs, "Offset"))
    links.new(_sock(setp.outputs, "Geometry"), _sock(go.inputs, "Geometry"))
    return ng


def place_after_armature(mesh_obj, mod, extra=0):
    """Move ``mod`` to sit right after the Armature modifier (+ ``extra``)."""
    mods = list(mesh_obj.modifiers)
    arm = next((i for i, m in enumerate(mods) if m.type == 'ARMATURE'), None)
    if arm is None:
        return
    target = min(arm + 1 + extra, len(mods) - 1)
    if mods.index(mod) != target:
        with bpy.context.temp_override(object=mesh_obj, active_object=mesh_obj):
            bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=target)


def remove_bulge(mesh_obj):
    ad = mesh_obj.animation_data
    if ad:
        for fc in list(ad.drivers):
            if fc.data_path.startswith(f'modifiers["{MODIFIER_NAME}"]'):
                ad.drivers.remove(fc)
    mod = mesh_obj.modifiers.get(MODIFIER_NAME)
    if mod is not None:
        mesh_obj.modifiers.remove(mod)


def add_bulge(mesh_obj, rig, order, info):
    """Add the bulge modifier and one driver per muscle.

    ``order`` and ``info`` come from ``weights.bake_masks``: the input order
    must match the indices baked into ``mus_idx*``.
    """
    remove_bulge(mesh_obj)
    ng = build_node_group(rig, [spec.mask_name(side) for spec, side in order])
    mod = mesh_obj.modifiers.new(MODIFIER_NAME, 'NODES')
    mod.node_group = ng
    place_after_armature(mesh_obj, mod)

    for spec, side in order:
        mask = spec.mask_name(side)
        if mask not in info:
            continue
        amplitude = info[mask][1] * spec.push
        owner, prop = ensure_flex_prop(rig, spec.flex_group, side)
        fc = mesh_obj.driver_add(f'modifiers["{MODIFIER_NAME}"]["{input_identifier(ng, mask)}"]')
        for m in list(fc.modifiers):
            fc.modifiers.remove(m)
        drv = fc.driver
        drv.type = 'SCRIPTED'
        s = drv.variables.new()
        s.name, s.type = "s", 'TRANSFORMS'
        t = s.targets[0]
        t.id = rig
        t.bone_target = spec.bone_names(side)[0]
        t.transform_type = 'SCALE_X'
        # LOCAL_SPACE includes the Stretch To result but not the parent's or
        # the object's scale (TRANSFORM_SPACE reads 1.0 here, verified on
        # Blender 4.5 and 5.0 by tests/test_muscle_rig.py).
        t.transform_space = 'LOCAL_SPACE'
        f = drv.variables.new()
        f.name, f.type = "flex", 'SINGLE_PROP'
        f.targets[0].id_type = 'OBJECT'
        f.targets[0].id = rig
        f.targets[0].data_path = f'pose.bones["{owner}"]["{prop}"]'
        drv.expression = f"(s - 1 + flex * {spec.flex_gain:g}) * {amplitude:.5g}"
    return mod
