# Copyright 2019-2020 Arx Libertatis Team (see the AUTHORS file)
#
# This file is part of Arx Libertatis.
#
# Arx Libertatis is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Arx Libertatis is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Arx Libertatis. If not, see <http://www.gnu.org/licenses/>.

import bpy
import os
from bpy.props import IntProperty, BoolProperty, StringProperty, CollectionProperty, PointerProperty, EnumProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from mathutils import Matrix, Vector, Quaternion
from .arx_io_util import ArxException, arx_pos_to_blender_for_model, arx_transform_to_blender
from .managers import getAddon
import math

g_areaToLevel = {
    0:0, 8:0, 11:0, 12:0,
    1:1, 13:1, 14:1,
    2:2, 15:2,
    3:3, 16:3, 17:3,
    4:4, 18:4, 19:4,
    5:5, 21:5,
    6:6, 22:6,
    7:7, 23:7
}

def importArea(context, report, area_id):
    scene_name = f"Area_{area_id:02d}"
    scene = bpy.data.scenes.get(scene_name)
    if scene:
        report({'INFO'}, f"Area Scene named [{scene_name}] already exists.")
        return
    report({'INFO'}, f"Creating new Area Scene [{scene_name}]")
    scene = bpy.data.scenes.new(name=scene_name)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.01
    getAddon(context).sceneManager.importScene(context, scene, area_id)

class CUSTOM_OT_arx_area_list_reload(Operator):
    bl_idname = "arx.arx_area_list_reload"
    bl_label = "Reload Area List"
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        area_list.clear()
        for area_id, value in getAddon(context).arxFiles.levels.levels.items():
            item = area_list.add()
            item.name = f'Area {area_id}'
            item.area_id = area_id
            item.level_id = g_areaToLevel.get(area_id, -1)
        return {"FINISHED"}

class ARX_area_properties(PropertyGroup):
    area_id: IntProperty(name="Arx Area ID", min=0)
    level_id: IntProperty(name="Arx Level ID", description="Levels consist of areas", min=-1)

class SCENE_UL_arx_area_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.3)
        split.label(text=item.name)
        split.label(text=str(item.area_id))
        split.label(text=str(item.level_id))
    def invoke(self, context, event):
        pass

class CUSTOM_OT_arx_area_list_import_selected(Operator):
    bl_idname = "arx.area_list_import_selected"
    bl_label = "Import Selected Area"
    def invoke(self, context, event):
        area_list = context.window_manager.arx_areas_col
        area = area_list[context.window_manager.arx_areas_idx]
        try:
            importArea(context, self.report, area.area_id)
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

class ArxOperatorImportAllLevels(Operator):
    bl_idname = "arx.operator_import_all_levels"
    bl_label = "Import All Levels"
    def execute(self, context):
        for area_id, value in getAddon(context).arxFiles.levels.levels.items():
            try:
                importArea(context, self.report, area_id)
            except ArxException as e:
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}
        return {'FINISHED'}

class ArxAnimationTestProperties(PropertyGroup):
    model: StringProperty(name="Model", description="Selected NPC model")
    animation: StringProperty(name="Animation", description="Selected animation")
    flip_w: BoolProperty(name="Flip W", default=False, description="Flip quaternion W component")
    flip_x: BoolProperty(name="Flip X", default=False, description="Flip quaternion X component")
    flip_y: BoolProperty(name="Flip Y", default=False, description="Flip quaternion Y component")
    flip_z: BoolProperty(name="Flip Z", default=False, description="Flip quaternion Z component")
    axis_mapping: EnumProperty(
        name="Axis Mapping",
        items=[
            ('XYZ', "X→X, Y→Y, Z→Z", "No remapping"),
            ('XZY', "X→X, Y→Z, Z→-Y", "Map Y to Z, Z to -Y"),
            ('YZX', "X→-Z, Y→Y, Z→X", "Map X to -Z, Z to X"),
            ('ZXY', "X→Y, Y→Z, Z→X", "Map X to Y, Y to Z, Z to X"),
            ('ZYX', "X→Z, Y→Y, Z→X", "Map X to Z, Z to X"),
            ('YXZ', "X→Y, Y→X, Z→Z", "Map X to Y, Y to X")
        ],
        default='ZXY',
        description="Axis remapping for quaternions"
    )

class ArxModelListProperties(PropertyGroup):
    model_list: CollectionProperty(type=bpy.types.PropertyGroup)
    model_list_loaded: BoolProperty(default=False)

class ArxModelListItem(PropertyGroup):
    name: StringProperty()

class ArxOperatorRefreshModelList(Operator):
    bl_idname = "arx.refresh_model_list"
    bl_label = "Refresh Model List"
    
    def execute(self, context):
        addon = getAddon(context)
        arx_files = addon.arxFiles
        
        arx_files.updateAll()
        context.scene.arx_model_list_props.model_list.clear()
        
        for key in arx_files.models.data.keys():
            if key[0] == "npc":
                item = context.scene.arx_model_list_props.model_list.add()
                item.name = key[-1]
        
        context.scene.arx_model_list_props.model_list_loaded = True
        
        print(f"Arx directory: {arx_files.rootPath}")
        print(f"Models: {list(arx_files.models.data.keys())}")
        print(f"Animations: {list(arx_files.animations.data.keys())}")
        
        if not context.scene.arx_model_list_props.model_list:
            self.report({'WARNING'}, "No NPC models found")
        else:
            self.report({'INFO'}, f"Found {len(context.scene.arx_model_list_props.model_list)} NPC models")
        
        return {'FINISHED'}

class ArxOperatorTestGoblinAnimations(Operator):
    bl_idname = "arx.test_goblin_animations"
    bl_label = "Test Selected Animation"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        addon = getAddon(context)
        arx_files = addon.arxFiles
        if not arx_files.models.data or not arx_files.animations.data:
            arx_files.updateAll()
            print(f"Models: {list(arx_files.models.data.keys())}")
            print(f"Animations: {list(arx_files.animations.data.keys())}")
        
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        for action in bpy.data.actions:
            bpy.data.actions.remove(action)
        for collection in bpy.data.collections:
            bpy.data.collections.remove(collection)
        for mesh in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)
        for armature in bpy.data.armatures:
            bpy.data.armatures.remove(armature)
        
        props = context.scene.arx_animation_test
        model_name = props.model
        if not model_name:
            self.report({'ERROR'}, "No model selected")
            return {'CANCELLED'}
        
        model_key = tuple(["npc", model_name])
        if model_key not in arx_files.models.data:
            self.report({'ERROR'}, f"Model {model_name} not found in ArxFiles")
            return {'CANCELLED'}
        
        model_data = arx_files.models.data[model_key]
        model_path = os.path.join(model_data.path, model_data.model)
        
        try:
            addon.objectManager.loadFile(context, model_path, context.scene, import_tweaks=False)
        except ArxException as e:
            self.report({'ERROR'}, f"Failed to import model {model_name}: {str(e)}")
            return {'CANCELLED'}
        
        obj = None
        for o in bpy.data.objects:
            if o.name.startswith(f"npc/{model_name}") and o.type == 'MESH':
                obj = o
                break
        if not obj:
            self.report({'ERROR'}, f"Model mesh {model_name} not found")
            return {'CANCELLED'}
        
        armature_obj = None
        for o in bpy.data.objects:
            if o.name.startswith(f"npc/{model_name}") and o.type == 'ARMATURE':
                armature_obj = o
                break
        if not armature_obj:
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object:
                    armature_obj = modifier.object
                    break
        if not armature_obj:
            self.report({'ERROR'}, f"No armature found for mesh '{obj.name}'")
            return {'CANCELLED'}
        
        anim_name = props.animation
        if not anim_name:
            self.report({'ERROR'}, "No animation selected")
            return {'CANCELLED'}
        
        anim_key = anim_name
        if anim_key not in arx_files.animations.data:
            self.report({'ERROR'}, f"Animation {anim_key} not found in ArxFiles")
            return {'CANCELLED'}
        
        anim_path = arx_files.animations.data[anim_key]
        frame_rate = context.scene.render.fps
        
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            action = addon.animationManager.loadAnimation(
                anim_path, 
                f"g{model_name}_{anim_name}", 
                frame_rate=frame_rate, 
                axis_transform=None,
                flip_w=props.flip_w,
                flip_x=props.flip_x,
                flip_y=props.flip_y,
                flip_z=props.flip_z
            )
            if action is None:
                self.report({'ERROR'}, f"Failed to apply animation {anim_key}: possible group count mismatch (check log)")
                return {'CANCELLED'}
            self.report({'INFO'}, f"Imported animation: {anim_name}")
        except ArxException as e:
            self.report({'ERROR'}, f"Failed to import {anim_key}: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class ArxAnimationTestPanel(Panel):
    bl_idname = "SCENE_PT_arx_animation_test"
    bl_label = "Arx Animation Test"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        props = context.scene.arx_animation_test
        addon = getAddon(context)
        arx_files = addon.arxFiles
        
        if not context.scene.arx_model_list_props.model_list_loaded:
            layout.operator("arx.refresh_model_list", text="Load Models")
            return
        
        layout.operator("arx.refresh_model_list", text="Refresh Models")
        
        if not context.scene.arx_model_list_props.model_list:
            layout.label(text="WARNING: No NPC models found", icon='ERROR')
            return
        
        row = layout.row()
        row.label(text="Model:")
        row.operator("arx.select_model", text=props.model if props.model else "Select Model")
        
        if props.model:
            anim_list = [
                anim for anim in sorted(arx_files.animations.data.keys())
                if props.model.lower() in anim.lower()
            ]
            row = layout.row()
            row.label(text="Animation:")
            row.operator("arx.select_animation", text=props.animation if props.animation else "Select Animation")
            if not anim_list:
                layout.label(text="WARNING: No animations found for selected model", icon='ERROR')
        
        layout.prop(props, "axis_mapping", text="Axis Mapping")
        layout.prop(props, "flip_w", text="Flip W")
        layout.prop(props, "flip_x", text="Flip X")
        layout.prop(props, "flip_y", text="Flip Y")
        layout.prop(props, "flip_z", text="Flip Z")
        
        layout.operator("arx.test_goblin_animations", text="Test Selected Animation")

class ArxSelectModelOperator(Operator):
    bl_idname = "arx.select_model"
    bl_label = "Select Model"
    model: StringProperty()

    def invoke(self, context, event):
        context.window_manager.invoke_props_dialog(self, width=200)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        model_list = context.scene.arx_model_list_props.model_list
        for item in model_list:
            layout.operator("arx.set_model", text=item.name).model = item.name
        if not model_list:
            layout.label(text="No models available")

    def execute(self, context):
        return {'FINISHED'}

class ArxSetModelOperator(Operator):
    bl_idname = "arx.set_model"
    bl_label = "Set Model"
    model: StringProperty()

    def execute(self, context):
        props = context.scene.arx_animation_test
        props.model = self.model
        props.animation = ""
        return {'FINISHED'}

class ArxSelectAnimationOperator(Operator):
    bl_idname = "arx.select_animation"
    bl_label = "Select Animation"
    animation: StringProperty()

    def invoke(self, context, event):
        context.window_manager.invoke_props_dialog(self, width=200)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.arx_animation_test
        arx_files = getAddon(context).arxFiles
        matching_anims = []
        model_words = props.model.lower().split('_')
        for anim in sorted(arx_files.animations.data.keys()):
            anim_lower = anim.lower()
            if any(word in anim_lower for word in model_words):
                matching_anims.append(anim)
        
        for anim in matching_anims:
            display_name = anim.replace('.tea', '') if anim.endswith('.tea') else anim
            layout.operator("arx.set_animation", text=display_name).animation = anim
        
        if not matching_anims:
            layout.label(text="No animations available")

    def execute(self, context):
        return {'FINISHED'}

class ArxSetAnimationOperator(Operator):
    bl_idname = "arx.set_animation"
    bl_label = "Set Animation"
    animation: StringProperty()

    def execute(self, context):
        props = context.scene.arx_animation_test
        props.animation = self.animation
        return {'FINISHED'}

classes = (
    CUSTOM_OT_arx_area_list_reload,
    ARX_area_properties,
    SCENE_UL_arx_area_list,
    CUSTOM_OT_arx_area_list_import_selected,
    ArxOperatorImportAllLevels,
    ArxAnimationTestProperties,
    ArxModelListProperties,
    ArxModelListItem,
    ArxOperatorRefreshModelList,
    ArxOperatorTestGoblinAnimations,
    ArxAnimationTestPanel,
    ArxSelectModelOperator,
    ArxSetModelOperator,
    ArxSelectAnimationOperator,
    ArxSetAnimationOperator,
)

def arx_ui_area_register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bpy.types.WindowManager.arx_areas_col = CollectionProperty(type=ARX_area_properties)
    bpy.types.WindowManager.arx_areas_idx = IntProperty()
    bpy.types.Scene.arx_animation_test = PointerProperty(type=ArxAnimationTestProperties)
    bpy.types.Scene.arx_model_list_props = PointerProperty(type=ArxModelListProperties)

def arx_ui_area_unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.WindowManager.arx_areas_col
    del bpy.types.WindowManager.arx_areas_idx
    del bpy.types.Scene.arx_animation_test
    del bpy.types.Scene.arx_model_list_props
