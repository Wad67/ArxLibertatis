# Copyright 2015-2020 Arx Libertatis Team (see the AUTHORS file)
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

import importlib
import sys

if "ArxAddon" in locals():
    importlib.reload(sys.modules["arx_addon.managers"])

if "ArxFacePanel" in locals():
    importlib.reload(sys.modules["arx_addon.meshEdit"])

from .arx_io_util import ArxException
from .managers import ArxAddon
from .meshEdit import ArxFacePanel, ArxMeshAddCustomProperties

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, StringProperty
from .arx_ui_area import (
    arx_ui_area_register,
    arx_ui_area_unregister
)
from .managers import arxAddonReload, getAddon

import logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger('ArxAddon')

class ArxAddonPreferences(AddonPreferences):
    bl_idname = __package__
    def reload(self, context):
        arxAddonReload()
    arxAssetPath: StringProperty(name="Arx assets root directory", subtype='DIR_PATH', update=reload)
    arxAllowLibFallback: BoolProperty(name="Allow use of fallback io library, only import ftl models, scenes are broken!", update=reload)
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "arxAssetPath")
        layout.prop(self, "arxAllowLibFallback")

class ArxModelsPanel(bpy.types.Panel):
    bl_idname = "SCENE_PT_models_panel"
    bl_label = "Arx Libertatis Models"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    def draw(self, context):
        layout = self.layout
        layout.operator("arx.operator_import_all_models")
        layout.operator("arx.operator_test_model_export")

class ArxOperatorTestModelExport(bpy.types.Operator):
    bl_idname = "arx.operator_test_model_export"
    bl_label = "Test model export"
    bl_description = "Test exporting a model"
    def execute(self, context):
        try:
            getAddon(context).testModelExport()
            return {'FINISHED'}
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class ArxOperatorImportAllModels(bpy.types.Operator):
    bl_idname = "arx.operator_import_all_models"
    bl_label = "Import all models"
    bl_description = "Import all available models"
    def execute(self, context):
        try:
            getAddon(context).assetManager.importAllModels(context)
            return {'FINISHED'}
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class ImportFTL(bpy.types.Operator, ImportHelper):
    bl_idname = "arx.import_ftl"
    bl_label = 'Import FTL model'
    bl_description = 'Import Arx Fatalis Model (.ftl) file'
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".ftl"
    check_extension = True
    filter_glob: StringProperty(default="*.ftl", options={'HIDDEN'})
    import_tweaks: BoolProperty(name="Import Tweaks", description="Import model tweaks", default=False)
    def execute(self, context):
        try:
            scene = context.scene
            getAddon(context).objectManager.loadFile(context, self.filepath, scene, self.import_tweaks)
            return {'FINISHED'}
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

def menu_func_import_ftl(self, context):
    self.layout.operator(ImportFTL.bl_idname, text="Arx Fatalis Model (.ftl)")

class ExportFTL(bpy.types.Operator, ExportHelper):
    bl_idname = "arx.export_ftl"
    bl_label = 'Export FTL model'
    bl_description = 'Export Arx Fatalis Model (.ftl) file'
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".ftl"
    check_extension = True
    filter_glob: StringProperty(default="*.ftl", options={'HIDDEN'})
    def execute(self, context):
        try:
            getAddon(context).objectManager.saveFile(self.filepath)
            return {'FINISHED'}
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

def menu_func_export_ftl(self, context):
    self.layout.operator(ExportFTL.bl_idname, text="Arx Fatalis Model (.ftl)")

class ImportTea(bpy.types.Operator, ImportHelper):
    bl_idname = "arx.import_tea"
    bl_label = "Import Tea animation"
    bl_description = "Import Tea animation (.tea) file"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".tea"
    check_extension = True
    filter_glob: StringProperty(default="*.tea", options={'HIDDEN'})
    def execute(self, context):
        try:
            getAddon(context).animationManager.loadAnimation(self.filepath)
            return {'FINISHED'}
        except ArxException as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

def menu_func_import_tea(self, context):
    self.layout.operator(ImportTea.bl_idname, text="Tea animation (.tea)")

classes = (
    ArxAddonPreferences,
    ArxOperatorImportAllModels,
    ArxOperatorTestModelExport,
    ArxModelsPanel,
    ArxMeshAddCustomProperties,
    ArxFacePanel,
    ImportFTL,
    ExportFTL,
    ImportTea
)

def register():
    log.debug("register")
    for cls in classes:
        bpy.utils.register_class(cls)
    arx_ui_area_register()
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_ftl)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_ftl)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_tea)

def unregister():
    log.debug("unregister")
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_ftl)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_ftl)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_tea)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    arx_ui_area_unregister()
    arxAddonReload()
