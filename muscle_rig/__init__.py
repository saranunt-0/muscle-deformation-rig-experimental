bl_info = {
    "name": "Muscle Rig (Rigify)",
    "author": "muscle-deformation-rig-experimental",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Muscle",
    "description": "Pose-driven muscle bulge + jiggle on top of a generated Rigify rig",
    "category": "Rigging",
}

if "bpy" in locals():
    import importlib
    for _m in (spec, library, build, weights, bulge, jiggle, api, ui):  # noqa: F821
        importlib.reload(_m)

import bpy  # noqa: E402

from . import spec, library, build, weights, bulge, jiggle, api, ui  # noqa: E402,F401


def register():
    ui.register()


def unregister():
    ui.unregister()
