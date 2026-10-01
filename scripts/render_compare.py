"""Render before/after comparisons of the muscle layer (Cycles, CPU).

    python scripts/render_compare.py --out docs/images [--samples 24] [--size 480]

Each sheet shows one pose three ways: plain Rigify skinning, with the muscle
layer, and a signed heat map of how the muscle layer moved each vertex along
its normal (red = pushed out, blue = pulled in, grey = untouched).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import demo_scene  # noqa: E402
from _runner import run  # noqa: E402

HEAT_MAX_MM = 15.0

# name -> (pose kwargs, flex, thumb, camera direction from subject, focus bones, margin)
SHOTS = {
    "biceps_flex": (dict(abduct=35, twist=-90, elbow=115), 0.0, 0.0,
                    "bend", ("ORG-upper_arm.L", "ORG-forearm.L"), 1.3),
    "arm_bent_side": (dict(swing=20, elbow=120), 0.0, 0.0,
                      (1, -0.15, 0), ("ORG-upper_arm.L", "ORG-forearm.L"), 1.35),
    "shoulder_raise": (dict(abduct=60), 0.0, 0.0,
                       (0.15, -1, 0.1), ("ORG-shoulder.L", "ORG-upper_arm.L"), 1.6),
    "wrist_curl": (dict(swing=30, elbow=70, wrist=70), 0.0, 0.0,
                   (0.3, -1, 0.2), ("ORG-forearm.L", "ORG-hand.L"), 1.5),
    "flex_slider": (dict(abduct=35, twist=-90, elbow=80), 1.0, 0.0,
                    "bend", ("ORG-upper_arm.L", "ORG-forearm.L"), 1.3),
    "thumb_in": (dict(), 0.0, 1.0,
                 (-0.55, -0.35, -0.75), ("ORG-hand.L", "ORG-thumb.01.L", "ORG-palm.04.L"), 2.0),
}


def setup_render(scene, samples, size):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    try:
        scene.cycles.use_denoising = True
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    except (AttributeError, TypeError):
        scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.image_settings.file_format = 'PNG'
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.045, 0.05, 0.055, 1)
    bg.inputs["Strength"].default_value = 1.0
    scene.world = world

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = 'ORTHO'
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    # Lights ride with the camera so every view gets the same raking key.
    for name, offset, energy, size_ in (("Key", (1.2, 0.0, 1.4), 120, 0.8),
                                        ("Fill", (-1.4, 0.0, 0.2), 25, 2.0),
                                        ("Rim", (0.0, 0.0, -0.3), 60, 1.0)):
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.size = energy, size_
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.parent = cam
        if name == "Rim":
            light.location = (0.0, 0.8, -2.6)  # behind the subject
        else:
            light.location = offset
        con = light.constraints.new('TRACK_TO')
        con.track_axis, con.up_axis = 'TRACK_NEGATIVE_Z', 'UP_Y'
        light["track"] = True
    return cam


def frame(cam, rig, bones, view, margin):
    pts = []
    for n in bones:
        pb = rig.pose.bones[n]
        pts += [rig.matrix_world @ pb.head, rig.matrix_world @ pb.tail]
    center = sum(pts, Vector()) / len(pts)
    if view == "bend":
        # Look straight at the elbow's bend plane, from the front.
        ua, fa = rig.pose.bones["ORG-upper_arm.L"], rig.pose.bones["ORG-forearm.L"]
        view = (ua.tail - ua.head).cross(fa.tail - fa.head)
        if view.y > 0:
            view = -view
    view = Vector(view).normalized()  # direction from subject to camera
    cam.location = center + view * 3.0
    cam.rotation_euler = (-view).to_track_quat('-Z', 'Y').to_euler()
    inv = cam.rotation_euler.to_matrix().inverted()
    local = [inv @ (p - center) for p in pts]
    extent = max(max(abs(p.x) for p in local), max(abs(p.y) for p in local)) * 2
    cam.data.ortho_scale = max(extent * margin, 0.12)
    target = bpy.data.objects.get("CamTarget") or bpy.data.objects.new("CamTarget", None)
    if target.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(target)
    target.location = center
    for obj in bpy.context.scene.objects:
        if obj.get("track"):
            obj.constraints[0].target = target


def materials(body):
    skin = body.data.materials[0]
    heat = bpy.data.materials.get("Heat") or bpy.data.materials.new("Heat")
    heat.use_nodes = True
    nt = heat.node_tree
    nt.nodes.clear()
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "mus_heat"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].color = (0.05, 0.25, 0.9, 1)          # pulled in
    els[1].position, els[1].color = 1.0, (1.0, 0.8, 0.15, 1)  # pushed out
    for pos, col in ((0.5, (0.45, 0.47, 0.5, 1)), (0.78, (0.9, 0.25, 0.12, 1))):
        els.new(pos).color = col
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return skin, heat


def write_heat(body, off, on, normals):
    """Signed push along the normal, mapped to 0..1 with 0.5 = untouched."""
    d = np.einsum("ij,ij->i", on - off, normals) * 1000.0
    attr = body.data.attributes.get("mus_heat") or body.data.attributes.new("mus_heat", 'FLOAT', 'POINT')
    attr.data.foreach_set("value", np.clip(0.5 + 0.5 * d / HEAT_MAX_MM, 0, 1).astype(np.float32))
    return float(d.max()), float(d.min())


def eval_coords(body):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    nor = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("normal", nor)
    ev.to_mesh_clear()
    return co.reshape(-1, 3), nor.reshape(-1, 3)


def compose(paths, labels, out):
    from PIL import Image, ImageDraw, ImageFont
    imgs = [Image.open(p).convert("RGB") for p in paths]
    w, h = imgs[0].size
    pad = 34
    sheet = Image.new("RGB", (w * len(imgs), h + pad), (22, 24, 26))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=17)
    except TypeError:
        font = ImageFont.load_default()
    for i, (img, label) in enumerate(zip(imgs, labels)):
        sheet.paste(img, (i * w, pad))
        draw.text((i * w + 12, 8), label, fill=(225, 225, 225), font=font)
    sheet.save(out)
    for p in paths:
        os.remove(p)


def set_flex(rig, value):
    for pb in rig.pose.bones:
        for k in pb.keys():
            if k.startswith("muscle_flex_"):
                pb[k] = value


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    def arg(name, default):
        return type(default)(argv[argv.index(name) + 1]) if name in argv else default

    out_dir = os.path.abspath(arg("--out", os.path.join(demo_scene.ROOT, "docs", "images")))
    shots = arg("--shots", ",".join(SHOTS)).split(",")
    os.makedirs(out_dir, exist_ok=True)
    meta, rig, body, built, painted = demo_scene.build()
    scene = bpy.context.scene
    cam = setup_render(scene, arg("--samples", 24), arg("--size", 480))
    skin, heat = materials(body)

    for shot in shots:
        pose, flex, thumb, view, focus, margin = SHOTS[shot]
        for side in (".L", ".R"):
            demo_scene.pose_arm(rig, side, **pose)
            demo_scene.pose_thumb(rig, side, thumb)
        set_flex(rig, flex)
        bpy.context.view_layer.update()
        frame(cam, rig, focus, view, margin)

        demo_scene.set_muscles_enabled(body, False, jiggle=False)
        off, normals = eval_coords(body)
        demo_scene.set_muscles_enabled(body, True, jiggle=False)
        out_mm, in_mm = write_heat(body, off, eval_coords(body)[0], normals)

        tmp = []
        for enabled, mat in ((False, skin), (True, skin), (True, heat)):
            demo_scene.set_muscles_enabled(body, enabled, jiggle=False)
            body.data.materials[0] = mat
            path = os.path.join(out_dir, f"_{shot}_{len(tmp)}.png")
            scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            tmp.append(path)
        body.data.materials[0] = skin
        flex_note = f", flex {flex:g}" if flex else ""
        compose(tmp, ["Rigify only", f"+ muscle layer{flex_note}",
                      f"push: +{out_mm:.0f} mm out (red) / {in_mm:.0f} mm in (blue)"],
                os.path.join(out_dir, f"{shot}.png"))
        print(f"wrote {shot} (out {out_mm:.1f} mm, in {in_mm:.1f} mm)")


if __name__ == "__main__":
    run(main)
