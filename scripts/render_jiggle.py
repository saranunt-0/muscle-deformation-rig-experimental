"""Render the jiggle demo: the arm snaps up and stops, the muscles keep going.

    python scripts/render_jiggle.py --out docs/images [--frames 36] [--size 320]

Writes ``jiggle.gif`` (skin | lag heat map, per frame) and ``jiggle_strip.png``
(a few key frames) plus ``jiggle_lag.csv`` (peak lag per frame, in mm).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import demo_scene  # noqa: E402
import render_compare as rc  # noqa: E402
from _runner import run  # noqa: E402
from muscle_rig import jiggle  # noqa: E402

LAG_MAX_MM = 12.0


def animate(rig):
    """Left arm: quick eased raise over 6 frames, then hold still."""
    from math import radians
    from mathutils import Quaternion
    demo_scene.set_fk(rig, ".L")
    ua = rig.pose.bones["upper_arm_fk.L"]
    fa = rig.pose.bones["forearm_fk.L"]
    ua.rotation_mode, fa.rotation_mode = 'QUATERNION', 'XYZ'
    for frame, abduct, elbow in ((1, 0, 10), (3, 0, 10), (9, 65, 40), (60, 65, 40)):
        ua.rotation_quaternion = Quaternion((0, 0, 1), radians(abduct)) @ Quaternion((0, 1, 0), radians(-60))
        fa.rotation_euler = (radians(elbow), 0, 0)
        ua.keyframe_insert("rotation_quaternion", frame=frame)
        fa.keyframe_insert("rotation_euler", frame=frame)


def lag_material():
    mat = bpy.data.materials.new("Lag")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "mus_jiggle_lag"
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = 'MULTIPLY'
    scale.inputs[1].default_value = 1000.0 / LAG_MAX_MM
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].color = (0.45, 0.47, 0.5, 1)
    els[1].color = (1.0, 0.8, 0.15, 1)
    els.new(0.5).color = (0.9, 0.25, 0.12, 1)
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(attr.outputs["Fac"], scale.inputs[0])
    nt.links.new(scale.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    def arg(name, default):
        return type(default)(argv[argv.index(name) + 1]) if name in argv else default

    out_dir = os.path.abspath(arg("--out", os.path.join(demo_scene.ROOT, "docs", "images")))
    frames = arg("--frames", 36)
    size = arg("--size", 320)
    os.makedirs(out_dir, exist_ok=True)

    meta, rig, body, built, painted = demo_scene.build(sets=("arm", "chest"))
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, frames
    cam = rc.setup_render(scene, arg("--samples", 12), size)
    mod = jiggle.add_jiggle_modifier(body, debug_output=True)
    skin, lag = body.data.materials[0], lag_material()
    animate(rig)

    scene.frame_set(7)
    rc.frame(cam, rig, ("ORG-upper_arm.L", "ORG-forearm.L", "ORG-shoulder.L"), (0, -1, 0.15), 1.5)

    from PIL import Image
    gif, peaks, keep = [], [], {}
    for f in range(1, frames + 1):
        scene.frame_set(f)  # sequential: the simulation needs every frame
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        me = ev.to_mesh()
        attr = me.attributes.get("mus_jiggle_lag")
        values = np.zeros(len(me.vertices))
        if attr is not None:
            attr.data.foreach_get("value", values)
        ev.to_mesh_clear()
        peaks.append(values.max() * 1000.0)
        panels = []
        for mat in (skin, lag):
            body.data.materials[0] = mat
            path = os.path.join(out_dir, f"_j{f}_{len(panels)}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            panels.append(Image.open(path).convert("RGB"))
            os.remove(path)
        body.data.materials[0] = skin
        sheet = Image.new("RGB", (size * 2, size), (22, 24, 26))
        sheet.paste(panels[0], (0, 0))
        sheet.paste(panels[1], (size, 0))
        gif.append(sheet)
        if f in (6, 10, 13, 16, 30):
            keep[f] = sheet
        print(f"frame {f}: peak lag {peaks[-1]:.1f} mm")

    gif[0].save(os.path.join(out_dir, "jiggle.gif"), save_all=True, append_images=gif[1:],
                duration=int(1000 / scene.render.fps), loop=0, optimize=True)
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    strip = Image.new("RGB", (size * len(keep), size * 2 + 30), (22, 24, 26))
    draw = ImageDraw.Draw(strip)
    for i, (f, sheet) in enumerate(keep.items()):
        strip.paste(sheet.crop((0, 0, size, size)), (i * size, 30))
        strip.paste(sheet.crop((size, 0, size * 2, size)), (i * size, 30 + size))
        draw.text((i * size + 10, 7), f"frame {f}: lag {peaks[f - 1]:.1f} mm", fill=(225, 225, 225), font=font)
    strip.save(os.path.join(out_dir, "jiggle_strip.png"))
    with open(os.path.join(out_dir, "jiggle_lag.csv"), "w") as fh:
        fh.write("frame,peak_lag_mm\n")
        for f, p in enumerate(peaks, 1):
            fh.write(f"{f},{p:.3f}\n")
    mod_inputs = {name: mod[jiggle.input_identifier(mod.node_group, name)] for name, *_ in jiggle.INPUTS[1:5]}
    print("settings", mod_inputs)


if __name__ == "__main__":
    run(main)
