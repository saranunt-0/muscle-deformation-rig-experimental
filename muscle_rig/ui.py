import bpy

from . import api, build, bulge, jiggle
from .library import SETS


def _rig_from_context(context):
    obj = context.active_object
    if obj is None:
        return None
    if obj.type == 'ARMATURE':
        return obj
    if obj.type == 'MESH':
        for m in obj.modifiers:
            if m.type == 'ARMATURE' and m.object is not None:
                return m.object
    return None


def _metarig_for(rig):
    for o in bpy.data.objects:
        if o.type == 'ARMATURE' and getattr(o.data, "rigify_target_rig", None) == rig:
            return o
    return None


class MuscleRigSettings(bpy.types.PropertyGroup):
    use_arm: bpy.props.BoolProperty(name="Arm", default=True, description=SETS["arm"].description)
    use_chest: bpy.props.BoolProperty(name="Chest", default=True, description=SETS["chest"].description)
    use_hand: bpy.props.BoolProperty(name="Hand", default=False, description=SETS["hand"].description)
    use_face: bpy.props.BoolProperty(name="Face", default=False, description=SETS["face"].description)
    add_jiggle: bpy.props.BoolProperty(name="Jiggle", default=True,
                                       description="Add the jiggle simulation modifier to bound meshes")

    def set_names(self):
        return [n for n in ("arm", "chest", "hand", "face") if getattr(self, f"use_{n}")]


class MUSCLERIG_OT_apply(bpy.types.Operator):
    """Build muscle bones on the Rigify rig and paint weights on every mesh bound to it"""
    bl_idname = "muscle_rig.apply"
    bl_label = "Build Muscles"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _rig_from_context(context) is not None

    def execute(self, context):
        rig = _rig_from_context(context)
        settings = context.scene.muscle_rig
        if not settings.set_names():
            self.report({'WARNING'}, "Pick at least one muscle set")
            return {'CANCELLED'}
        built, stats = api.apply(rig, settings.set_names(), add_jiggle=settings.add_jiggle)
        meshes = ", ".join(stats) or "no bound meshes"
        self.report({'INFO'}, f"Built {len(built)} muscles; painted {meshes}")
        return {'FINISHED'}


class MUSCLERIG_OT_strip(bpy.types.Operator):
    """Remove all muscle bones, weights and jiggle modifiers from this rig"""
    bl_idname = "muscle_rig.strip"
    bl_label = "Remove Muscles"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _rig_from_context(context) is not None

    def execute(self, context):
        api.strip(_rig_from_context(context))
        return {'FINISHED'}


class MUSCLERIG_OT_install_hook(bpy.types.Operator):
    """Make Rigify rebuild the muscles automatically every time you press Re-Generate Rig"""
    bl_idname = "muscle_rig.install_hook"
    bl_label = "Rebuild on Re-Generate"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        rig = _rig_from_context(context)
        return rig is not None and _metarig_for(rig) is not None

    def execute(self, context):
        rig = _rig_from_context(context)
        meta = _metarig_for(rig)
        text = api.install_rigify_hook(meta, context.scene.muscle_rig.set_names())
        self.report({'INFO'}, f"{meta.name}: Rigify will run '{text.name}' after generating")
        return {'FINISHED'}


class VIEW3D_PT_muscle_rig(bpy.types.Panel):
    bl_label = "Muscle Rig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Muscle"

    def draw(self, context):
        layout = self.layout
        rig = _rig_from_context(context)
        if rig is None:
            layout.label(text="Select a Rigify rig or a mesh bound to it")
            return
        settings = context.scene.muscle_rig
        layout.label(text=rig.name, icon='ARMATURE_DATA')
        row = layout.row(align=True)
        for name in ("arm", "chest", "hand", "face"):
            row.prop(settings, f"use_{name}", toggle=True)
        layout.prop(settings, "add_jiggle")
        row = layout.row(align=True)
        row.operator(MUSCLERIG_OT_apply.bl_idname, icon='MOD_ARMATURE')
        row.operator(MUSCLERIG_OT_strip.bl_idname, text="", icon='TRASH')
        layout.operator(MUSCLERIG_OT_install_hook.bl_idname, icon='FILE_SCRIPT')

        flex = [(pb, k) for pb in rig.pose.bones for k in pb.keys() if k.startswith(build.FLEX_PREFIX)]
        if flex:
            box = layout.box()
            box.label(text="Flex (keyable)")
            for pb, key in sorted(flex, key=lambda x: x[1]):
                box.prop(pb, f'["{key}"]', text=key[len(build.FLEX_PREFIX):], slider=True)

        for mesh in api.bound_meshes(rig):
            bmod = mesh.modifiers.get(bulge.MODIFIER_NAME)
            if bmod is not None and bmod.node_group is not None:
                box = layout.box()
                box.label(text=f"Bulge: {mesh.name}", icon='MOD_CAST')
                row = box.row(align=True)
                row.prop(bmod, "show_viewport", text="")
                row.prop(bmod, f'["{bulge.input_identifier(bmod.node_group, "Strength")}"]', text="Strength")
            mod = mesh.modifiers.get(jiggle.MODIFIER_NAME)
            if mod is None or mod.node_group is None:
                continue
            box = layout.box()
            box.label(text=f"Jiggle: {mesh.name}", icon='MOD_SOFT')
            box.prop(mod, "show_viewport", text="Enabled")
            for name, *_ in jiggle.INPUTS[1:]:
                box.prop(mod, f'["{jiggle.input_identifier(mod.node_group, name)}"]', text=name)
            box.label(text="Bake: Physics tab > Simulation Nodes", icon='INFO')


CLASSES = (MuscleRigSettings, MUSCLERIG_OT_apply, MUSCLERIG_OT_strip,
           MUSCLERIG_OT_install_hook, VIEW3D_PT_muscle_rig)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.muscle_rig = bpy.props.PointerProperty(type=MuscleRigSettings)


def unregister():
    del bpy.types.Scene.muscle_rig
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
