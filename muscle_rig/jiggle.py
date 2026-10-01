"""Muscle jiggle as a Geometry Nodes simulation (no add-ons, bakeable).

Each vertex is a damped spring that chases its armature-deformed position.
The spring lives in a point cloud inside a Simulation Zone (position +
velocity per point); the mesh then gets ``offset * mask * strength`` where the
mask is ``mus_jiggle``, baked from the ``MUS-jiggle`` vertex group.

Damping acts on the velocity *relative to the target* (the skin's own
motion), so a limb moving at constant speed carries its flesh along and only
acceleration (starts, stops, impacts) makes it wobble. Damping against world
velocity instead would make every fast swing drag centimetres behind.

Integration is semi-implicit Euler with implicit damping:
    vt = (target - target_prev) / dt
    v' = (v + dt*(k*(target - p) + c*vt)) / (1 + c*dt),   p' = p + v'*dt
with k = (2*pi*f)^2 and c = 2*zeta*(2*pi*f). It is stable for f below about
fps/pi (7.6 Hz at 24 fps); the UI caps frequency at 6 Hz. The offset is
clamped to "Max Offset" so a hard pose change can never explode the mesh.
"""

import math

import bpy

from .bulge import place_after_armature
from .weights import JIGGLE_ATTR

GROUP_NAME = "MUS_Jiggle"
GROUP_VERSION = 5
MODIFIER_NAME = "MUS Jiggle"

INPUTS = (
    # name, socket type, default, min, max, description
    ("Mask", "NodeSocketString", JIGGLE_ATTR, None, None,
     "Attribute (or vertex group) that scales the effect"),
    ("Strength", "NodeSocketFloat", 1.0, 0.0, 3.0, "Overall multiplier"),
    ("Frequency", "NodeSocketFloat", 4.0, 0.2, 6.0,
     "Wobble frequency in Hz (lower = floppier)"),
    ("Damping", "NodeSocketFloat", 0.3, 0.0, 2.0,
     "Damping ratio: 0 wobbles forever, 1 settles without overshoot"),
    ("Max Offset", "NodeSocketFloat", 0.03, 0.0, 1.0,
     "Largest distance a vertex may lag behind, in object units"),
    ("Debug Output", "NodeSocketBool", False, None, None,
     "Store the per-vertex lag length in the 'mus_jiggle_lag' attribute"),
)


def _sock(sockets, name):
    for s in sockets:
        if s.name == name and getattr(s, "enabled", True):
            return s
    raise KeyError(name)


class _Builder:
    def __init__(self, ng):
        self.ng = ng
        self.x = 0

    def node(self, kind, **props):
        n = self.ng.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (self.x, 0)
        self.x += 160
        return n

    def link(self, a, b):
        self.ng.links.new(a, b)

    def math(self, op, a, b):
        n = self.node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.link(a, n.inputs[0])
        if b is not None:
            self.link(b, n.inputs[1])
        if scale is not None:
            if isinstance(scale, (int, float)):
                n.inputs[3].default_value = scale
            else:
                self.link(scale, n.inputs[3])
        return n.outputs[1] if op == 'LENGTH' else n.outputs[0]

    def sample_position(self, geometry):
        """Field: position of the point with the same index in ``geometry``."""
        n = self.node("GeometryNodeSampleIndex", data_type='FLOAT_VECTOR', domain='POINT')
        self.link(geometry, _sock(n.inputs, "Geometry"))
        self.link(self.node("GeometryNodeInputPosition").outputs[0], _sock(n.inputs, "Value"))
        self.link(self.node("GeometryNodeInputIndex").outputs[0], _sock(n.inputs, "Index"))
        return _sock(n.outputs, "Value")

    def named(self, data_type, name):
        n = self.node("GeometryNodeInputNamedAttribute", data_type=data_type)
        if isinstance(name, str):
            _sock(n.inputs, "Name").default_value = name
        else:
            self.link(name, _sock(n.inputs, "Name"))
        return _sock(n.outputs, "Attribute")

    def store(self, geometry, name, value):
        n = self.node("GeometryNodeStoreNamedAttribute", data_type='FLOAT_VECTOR', domain='POINT')
        self.link(geometry, _sock(n.inputs, "Geometry"))
        _sock(n.inputs, "Name").default_value = name
        self.link(value, _sock(n.inputs, "Value"))
        return _sock(n.outputs, "Geometry")


def ensure_node_group():
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None and ng.get("muscle_rig_version") == GROUP_VERSION:
        return ng
    if ng is None:
        ng = bpy.data.node_groups.new(GROUP_NAME, 'GeometryNodeTree')
    ng.nodes.clear()
    ng.interface.clear()
    ng["muscle_rig_version"] = GROUP_VERSION

    iface = ng.interface
    iface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    for name, stype, default, lo, hi, desc in INPUTS:
        s = iface.new_socket(name, in_out='INPUT', socket_type=stype)
        s.default_value = default
        s.description = desc
        if lo is not None:
            s.min_value, s.max_value = lo, hi
    iface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    b = _Builder(ng)
    gi = b.node("NodeGroupInput")
    go = b.node("NodeGroupOutput")
    g_in = _sock(gi.outputs, "Geometry")

    # Initial state: one point per vertex at the deformed position.
    size = b.node("GeometryNodeAttributeDomainSize", component='MESH')
    b.link(g_in, _sock(size.inputs, "Geometry"))
    pts = b.node("GeometryNodePoints")
    b.link(_sock(size.outputs, "Point Count"), _sock(pts.inputs, "Count"))
    b.link(b.sample_position(g_in), _sock(pts.inputs, "Position"))

    sim_in = b.node("GeometryNodeSimulationInput")
    sim_out = b.node("GeometryNodeSimulationOutput")
    sim_in.pair_with_output(sim_out)
    b.link(_sock(pts.outputs, "Points"), _sock(sim_in.inputs, "Geometry"))
    state = _sock(sim_in.outputs, "Geometry")
    dt = _sock(sim_in.outputs, "Delta Time")

    # Spring constants from frequency / damping ratio.
    omega = b.math('MULTIPLY', _sock(gi.outputs, "Frequency"), 2.0 * math.pi)
    k = b.math('MULTIPLY', omega, omega)
    c = b.math('MULTIPLY', b.math('MULTIPLY', _sock(gi.outputs, "Damping"), omega), 2.0)
    kdt = b.math('MULTIPLY', k, dt)
    inv = b.math('DIVIDE', 1.0, b.math('ADD', 1.0, b.math('MULTIPLY', c, dt)))

    p = b.node("GeometryNodeInputPosition").outputs[0]
    v = b.named('FLOAT_VECTOR', "mus_vel")
    target = b.sample_position(g_in)
    # Target velocity from the previous target (absent on the first frame ->
    # the initial points sit on the target, so use position instead).
    prev = b.node("GeometryNodeInputNamedAttribute", data_type='FLOAT_VECTOR')
    _sock(prev.inputs, "Name").default_value = "mus_prev"
    prev_t = b.node("GeometryNodeSwitch", input_type='VECTOR')
    b.link(_sock(prev.outputs, "Exists"), prev_t.inputs[0])
    b.link(p, prev_t.inputs[1])
    b.link(_sock(prev.outputs, "Attribute"), prev_t.inputs[2])
    inv_dt = b.math('DIVIDE', 1.0, b.math('MAXIMUM', dt, 1e-6))
    vt = b.vmath('SCALE', b.vmath('SUBTRACT', target, prev_t.outputs[0]), scale=inv_dt)
    cdt = b.math('MULTIPLY', c, dt)

    force = b.vmath('ADD', b.vmath('SCALE', b.vmath('SUBTRACT', target, p), scale=kdt),
                    b.vmath('SCALE', vt, scale=cdt))
    v1 = b.vmath('SCALE', b.vmath('ADD', v, force), scale=inv)
    p1 = b.vmath('ADD', p, b.vmath('SCALE', v1, scale=dt))
    lag = b.vmath('SUBTRACT', p1, target)
    clamp = b.math('MINIMUM', b.math('DIVIDE', _sock(gi.outputs, "Max Offset"),
                                     b.math('MAXIMUM', b.vmath('LENGTH', lag), 1e-6)), 1.0)
    p2 = b.vmath('ADD', target, b.vmath('SCALE', lag, scale=clamp))
    # When clamped, keep only the target's velocity (no stored energy).
    v2 = b.vmath('ADD', vt, b.vmath('SCALE', b.vmath('SUBTRACT', v1, vt), scale=clamp))

    # Store the new velocity under a temporary name first so Set Position
    # still reads the old one, then rename. Also remember this target.
    geo = b.store(state, "mus_vel_next", v2)
    setp = b.node("GeometryNodeSetPosition")
    b.link(geo, _sock(setp.inputs, "Geometry"))
    b.link(p2, _sock(setp.inputs, "Position"))
    geo = b.store(_sock(setp.outputs, "Geometry"), "mus_vel", b.named('FLOAT_VECTOR', "mus_vel_next"))
    geo = b.store(geo, "mus_prev", b.sample_position(g_in))
    b.link(geo, _sock(sim_out.inputs, "Geometry"))

    # Apply lag * mask * strength to the real mesh.
    lagged = b.sample_position(_sock(sim_out.outputs, "Geometry"))
    offset = b.vmath('SUBTRACT', lagged, b.node("GeometryNodeInputPosition").outputs[0])
    weight = b.math('MULTIPLY', b.named('FLOAT', _sock(gi.outputs, "Mask")), _sock(gi.outputs, "Strength"))
    final = b.node("GeometryNodeSetPosition")
    b.link(g_in, _sock(final.inputs, "Geometry"))
    applied = b.vmath('SCALE', offset, scale=weight)
    b.link(applied, _sock(final.inputs, "Offset"))

    # Optional debug attribute (only written when the toggle is on).
    dbg = b.node("GeometryNodeStoreNamedAttribute", data_type='FLOAT', domain='POINT')
    b.link(_sock(final.outputs, "Geometry"), _sock(dbg.inputs, "Geometry"))
    _sock(dbg.inputs, "Name").default_value = "mus_jiggle_lag"
    b.link(b.vmath('LENGTH', applied), _sock(dbg.inputs, "Value"))
    switch = b.node("GeometryNodeSwitch", input_type='GEOMETRY')
    b.link(_sock(gi.outputs, "Debug Output"), switch.inputs[0])
    b.link(_sock(final.outputs, "Geometry"), switch.inputs[1])
    b.link(_sock(dbg.outputs, "Geometry"), switch.inputs[2])
    b.link(switch.outputs[0], _sock(go.inputs, "Geometry"))
    return ng


def input_identifier(ng, name):
    for item in ng.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == 'INPUT' and item.name == name:
            return item.identifier
    raise KeyError(name)


def add_jiggle_modifier(mesh_obj, **settings):
    """Add (or update) the jiggle modifier after Armature (and MUS Bulge).

    ``settings`` keys are input names with spaces replaced by underscores,
    e.g. ``frequency=3.0, max_offset=0.02``.
    """
    ng = ensure_node_group()
    mod = mesh_obj.modifiers.get(MODIFIER_NAME)
    if mod is None:
        mod = mesh_obj.modifiers.new(MODIFIER_NAME, 'NODES')
    mod.node_group = ng
    for key, value in settings.items():
        mod[input_identifier(ng, key.replace("_", " ").title())] = value

    place_after_armature(mesh_obj, mod, extra=1 if "MUS Bulge" in mesh_obj.modifiers else 0)
    return mod


def remove_jiggle_modifier(mesh_obj):
    mod = mesh_obj.modifiers.get(MODIFIER_NAME)
    if mod is not None:
        mesh_obj.modifiers.remove(mod)
