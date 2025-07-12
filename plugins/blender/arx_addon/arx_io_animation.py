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

import logging
import bpy
import re
from mathutils import Vector, Quaternion, Matrix
from .arx_io_util import arx_pos_to_blender_for_model, arx_transform_to_blender, blender_pos_to_arx, ArxException
from .dataTea import TeaSerializer, TeaFrame, THEO_GROUPANIM
from .dataCommon import SavedVec3, ArxQuat

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def blender_to_arx_transform(location, rotation, scale, scale_factor=0.1, flip_w=True, flip_x=False, flip_y=True, flip_z=False):
    """Exact inverse of arx_transform_to_blender"""
    # Reverse the location transformation: from blender back to arx coordinates 
    arx_pos = blender_pos_to_arx(location) 
    arx_loc = Vector(arx_pos) / scale_factor
    
    # Reverse the rotation transformation
    rot_matrix = rotation.to_matrix().to_4x4()
    # Inverse transform matrix (transpose of the original)
    inv_transform_matrix = Matrix([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])
    transformed_matrix = inv_transform_matrix @ rot_matrix @ inv_transform_matrix.inverted()
    arx_rot = transformed_matrix.to_quaternion()
    
    # Reverse the flips
    w, x, y, z = arx_rot
    arx_rot = Quaternion((
        -w if flip_w else w,
        -x if flip_x else x,
        -y if flip_y else y,
        -z if flip_z else z
    ))
    
    # Reverse the scale transformation 
    arx_scale = Vector((scale.x, scale.z, scale.y))
    
    return arx_loc, arx_rot, arx_scale


def parse_group_index(name):
    """
    Parse the group index from vertex group or bone names.
    Handles formats like 'grp:23:toe4', 'grp:00:all', etc.
    Returns the numeric index or None if not found.
    """
    match = re.match(r'grp:(\d+):', name)
    if match:
        return int(match.group(1))
    match = re.search(r'(\d+)', name)
    if match:
        return int(match.group(1))
    return None

class ArxAnimationManager(object):
    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.teaSerializer = TeaSerializer()

    def build_mappings(self, armature_obj, obj, data):
        """
        Build mappings from group indices to bones and vertex groups.
        Args:
            armature_obj: Blender armature object.
            obj: Blender mesh object.
            data: List of TeaFrame objects from TeaSerializer.read.
        Returns:
            bone_map: Dict mapping group indices to bones.
            vg_map: Dict mapping group indices to vertex group names.
            animatable_indices: Set of indices that can be animated.
        """
        bone_map = {}
        for bone in armature_obj.pose.bones:
            group_index = parse_group_index(bone.name)
            if group_index is not None:
                bone_map[group_index] = bone
                self.log.debug("Mapped bone '%s' to group index %d", bone.name, group_index)
            else:
                self.log.warning("Could not parse group index from bone name: %s", bone.name)
        
        vg_map = {}
        for vg in obj.vertex_groups:
            group_index = parse_group_index(vg.name)
            if group_index is not None:
                vg_map[group_index] = vg.name
                self.log.debug("Mapped vertex group '%s' to group index %d", vg.name, group_index)
            else:
                self.log.warning("Could not parse group index from vertex group name: %s", vg.name)
        
        num_groups = len(data[0].groups)
        animatable_indices = set(bone_map.keys()) & set(range(num_groups))
        self.log.info("Can animate %d groups (indices: %s)", len(animatable_indices), sorted(animatable_indices))
        
        return bone_map, vg_map, animatable_indices

    def calculate_frame_timing(self, data, frame_rate):
        """
        Calculate Blender frame numbers from TEA frame durations.
        Args:
            data: List of TeaFrame objects.
            frame_rate: Target frame rate (frames per second).
        Returns:
            frame_times: List of cumulative times (seconds) for each frame.
            blender_frames: List of corresponding Blender frame numbers.
            total_duration: Total animation duration in seconds.
            total_blender_frames: Total number of Blender frames.
        """
        current_time = 0.0
        frame_times = []
        blender_frames = []
        min_frame_duration = 1.0 / frame_rate
        
        for frame_index, frame in enumerate(data):
            frame_times.append(current_time)
            blender_frame_float = (current_time * frame_rate) + 1.0
            blender_frame = max(1, round(blender_frame_float))
            blender_frames.append(blender_frame)
            
            duration_seconds = max(frame.duration, min_frame_duration)
            current_time += duration_seconds
            
            self.log.debug("TEA frame %d: time=%.3fs -> Blender frame %d (duration=%dms)", 
                           frame_index, frame_times[-1], blender_frame, frame.duration * 1000)
        
        total_duration = current_time
        total_blender_frames = max(len(data), round(total_duration * frame_rate))
        
        if total_blender_frames < len(data):
            self.log.warning("Animation too short (%d frames), adjusting to %d frames", 
                             total_blender_frames, len(data))
            blender_frames = list(range(1, len(data) + 1))
            total_blender_frames = len(data)
        
        self.log.info("Total animation duration: %.3fs (%d TEA frames) -> %d Blender frames at %.1f fps", 
                      total_duration, len(data), total_blender_frames, frame_rate)
        
        return frame_times, blender_frames, total_duration, total_blender_frames

    def apply_frame_transforms(self, frame, frame_index, blender_frame, obj, armature_obj, bone_map, animatable_indices, scale_factor, flip_w, flip_x, flip_y, flip_z):
        """
        Apply transformations for a single TEA frame to Blender objects and bones.
        Args:
            frame: TeaFrame object containing animation data.
            frame_index: Index of the current frame.
            blender_frame: Corresponding Blender frame number.
            obj: Blender mesh object.
            armature_obj: Blender armature object.
            bone_map: Dict mapping group indices to bones.
            animatable_indices: Set of indices that can be animated.
            scale_factor: Scaling factor for positions.
            flip_w, flip_x, flip_y, flip_z: Boolean flags for quaternion component flipping.
        """
        bpy.context.scene.frame_set(blender_frame)
        self.log.debug("Processing TEA frame %d -> Blender frame %d: duration=%dms", 
                       frame_index, blender_frame, frame.duration * 1000)

        if frame.translation or frame.rotation:
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.context.view_layer.objects.active = obj
            
            if frame.translation:
                root_location = Vector((frame.translation.x, frame.translation.y, frame.translation.z))
                root_location *= 0.1
                root_loc, _, _ = arx_transform_to_blender(root_location, Quaternion((1,0,0,0)), Vector((1,1,1)), scale_factor, flip_w, flip_x, flip_y, flip_z)
                if frame_index == 0:
                    obj.location = root_loc
                else:
                    obj.location = obj.location + root_loc
                obj.keyframe_insert(data_path="location")
                self.log.debug("Frame %d: Applied root translation=%s to mesh", frame_index, root_loc)

            if frame.rotation:
                root_rotation = Quaternion((frame.rotation.w, frame.rotation.x, frame.rotation.y, frame.rotation.z))
                _, root_rot, _ = arx_transform_to_blender(Vector((0,0,0)), root_rotation, Vector((1,1,1)), scale_factor, flip_w, flip_x, flip_y, flip_z)
                obj.rotation_mode = 'QUATERNION'
                obj.rotation_quaternion = root_rot
                obj.keyframe_insert(data_path="rotation_quaternion")
                self.log.debug("Frame %d: Applied root rotation=%s to mesh", frame_index, root_rot)
            
            bpy.context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode='POSE')

        for group_index in animatable_indices:
            group = frame.groups[group_index]
            bone = bone_map[group_index]
            
            if group.key_group == -1:
                continue

            self.log.debug("Frame %d, Group %d, Bone %s: translate=%s, Quaternion=%s, zoom=%s",
                           frame_index, group_index, bone.name, group.translate, group.Quaternion, group.zoom)

            location = Vector((group.translate.x, group.translate.y, group.translate.z))
            rotation = Quaternion((group.Quaternion.w, group.Quaternion.x, group.Quaternion.y, group.Quaternion.z))
            scale = Vector((group.zoom.x, group.zoom.y, group.zoom.z))
            
            loc, rot, scl = arx_transform_to_blender(location, rotation, scale, scale_factor, flip_w, flip_x, flip_y, flip_z)
            
            bone.location = loc
            bone.rotation_mode = 'QUATERNION'
            bone.rotation_quaternion = rot
            bone.scale = scl
            
            bone.keyframe_insert(data_path="location")
            bone.keyframe_insert(data_path="rotation_quaternion")
            bone.keyframe_insert(data_path="scale")
            
            if frame_index in (0, len(frame.groups) - 1):
                self.log.debug("Frame %d, Group %d, Bone %s: Applied loc=%s, rot=%s, scl=%s, matrix=%s", 
                               frame_index, group_index, bone.name, loc, rot, scl, bone.matrix)

    def loadAnimation(self, path, action_name=None, frame_rate=24.0, scale_factor=0.1, axis_transform=None, flip_w=False, flip_x=False, flip_y=False, flip_z=False):
        """
        Load an animation from a TEA file and apply it to the active mesh and its armature.
        Args:
            path: Path to the TEA file.
            action_name: Name for the Blender action (optional).
            frame_rate: Target frame rate (default 24.0).
            scale_factor: Scaling factor for positions (default 0.1).
            axis_transform: Optional function to transform coordinates (if None, uses arx_transform_to_blender).
            flip_w, flip_x, flip_y, flip_z: Boolean flags for quaternion component flipping.
        Returns:
            The created Blender action, or None if the import fails.
        """
        data = self.teaSerializer.read(path)
        if not data:
            self.log.error("No animation data loaded from file: {}".format(path))
            return None

        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            self.log.error("No mesh object selected for animation import")
            return None

        armature_obj = None
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object:
                armature_obj = modifier.object
                break

        if not armature_obj:
            self.log.error("No armature found for mesh '%s'", obj.name)
            return None

        bone_map, vg_map, animatable_indices = self.build_mappings(armature_obj, obj, data)
        
        if not animatable_indices:
            self.log.error("No matching bone indices found for animation groups")
            return None

        self.log.info("Mesh '%s' has %d vertex groups, %d with parseable indices", 
                      obj.name, len(obj.vertex_groups), len(vg_map))
        self.log.info("Armature '%s' has %d bones, %d with parseable indices", 
                      armature_obj.name, len(armature_obj.pose.bones), len(bone_map))

        if not armature_obj.animation_data:
            armature_obj.animation_data_create()
        if not obj.animation_data:
            obj.animation_data_create()

        action_name = action_name or f"{armature_obj.name}_{path.split('/')[-1].replace('.tea', '')}"
        
        for action in bpy.data.actions:
            if action.name == action_name:
                bpy.data.actions.remove(action)

        action = bpy.data.actions.new(action_name)
        armature_obj.animation_data.action = action
        obj.animation_data.action = action
        
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='POSE')

        frame_times, blender_frames, total_duration, total_blender_frames = self.calculate_frame_timing(data, frame_rate)

        for frame_index, frame in enumerate(data):
            self.apply_frame_transforms(
                frame, frame_index, blender_frames[frame_index], obj, armature_obj,
                bone_map, animatable_indices, scale_factor, flip_w, flip_x, flip_y, flip_z
            )

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.scene.frame_end = total_blender_frames

        for fcurve in action.fcurves:
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = 'LINEAR'

        self.log.info("Animation loaded successfully: %d TEA frames -> %d Blender frames (%.2fs at %dfps), %d animated bones",
                      len(data), total_blender_frames, total_duration, frame_rate, len(animatable_indices))

        return action

    def saveAnimation(self, path, action_name=None, frame_rate=24.0, scale_factor=0.1, version=2015):
        """
        Export an animation from Blender to a TEA file.
        Args:
            path: Path to the output TEA file.
            action_name: Name of the action to export (default: active action).
            frame_rate: Source frame rate (default 24.0).
            scale_factor: Scaling factor for positions (default 0.1).
            version: TEA version (2014 or 2015, default 2015).
        Returns:
            True if successful, False otherwise.
        """
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            self.log.error("No mesh object selected for animation export")
            return False

        armature_obj = None
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object:
                armature_obj = modifier.object
                break

        if not armature_obj:
            self.log.error("No armature found for mesh '%s'", obj.name)
            return False

        # Get the action to export
        action = None
        if action_name:
            action = bpy.data.actions.get(action_name)
            if not action:
                self.log.error("Action '%s' not found", action_name)
                return False
        else:
            if armature_obj.animation_data and armature_obj.animation_data.action:
                action = armature_obj.animation_data.action
            else:
                self.log.error("No action found to export")
                return False

        # Build mappings
        bone_map = {}
        for bone in armature_obj.pose.bones:
            group_index = parse_group_index(bone.name)
            if group_index is not None:
                bone_map[group_index] = bone

        if not bone_map:
            self.log.error("No bones with parseable group indices found")
            return False

        # Determine animation frame range
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        self.log.info("Exporting animation '%s' frames %d-%d", action.name, frame_start, frame_end)

        # Extract animation data
        frames = []
        original_frame = bpy.context.scene.frame_current
        
        try:
            bpy.context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode='POSE')
            
            for frame_num in range(frame_start, frame_end + 1):
                bpy.context.scene.frame_set(frame_num)
                
                # Calculate frame duration
                duration = 1.0 / frame_rate  # Default duration
                
                # Get root translation and rotation from mesh object
                root_translation = None
                root_rotation = None
                
                if obj.animation_data and obj.animation_data.action == action:
                    root_translation = self._extract_translation_from_object(obj, scale_factor)
                    root_rotation = self._extract_rotation_from_object(obj)
                
                # Extract bone transformations
                groups = self._extract_bone_groups(armature_obj, bone_map, scale_factor)
                
                # Create frame
                frame = TeaFrame(
                    duration=duration,
                    flags=-1,  # Default flag (no step sound)
                    translation=root_translation,
                    rotation=root_rotation,
                    groups=groups,
                    sampleName=None
                )
                
                frames.append(frame)
                
        finally:
            bpy.context.scene.frame_set(original_frame)
            bpy.ops.object.mode_set(mode='OBJECT')

        if not frames:
            self.log.error("No animation frames extracted")
            return False

        # Write TEA file
        try:
            self.teaSerializer.write(frames, path, action.name, version)
            self.log.info("Successfully exported animation to %s", path)
            return True
        except Exception as e:
            self.log.error("Failed to write TEA file: %s", str(e))
            return False

    def _extract_translation_from_object(self, obj, scale_factor):
        """Extract translation from object, converting to Arx coordinate system."""
        if not obj.animation_data or not obj.animation_data.action:
            return None
            
        location = obj.location.copy()
        rotation = Quaternion((1, 0, 0, 0))  # Identity quaternion
        scale = Vector((1, 1, 1))  # Unit scale
        
        # Use inverse coordinate conversion with same defaults as import
        arx_loc, _, _ = blender_to_arx_transform(location, rotation, scale, scale_factor, flip_w=False, flip_x=False, flip_y=False, flip_z=False)
        
        arx_location = SavedVec3()
        arx_location.x = arx_loc.x
        arx_location.y = arx_loc.y
        arx_location.z = arx_loc.z
        return arx_location

    def _extract_rotation_from_object(self, obj):
        """Extract rotation from object, converting to Arx coordinate system."""
        if not obj.animation_data or not obj.animation_data.action:
            return None
            
        if obj.rotation_mode == 'QUATERNION':
            rotation = obj.rotation_quaternion.copy()
        else:
            rotation = obj.rotation_euler.to_quaternion()
            
        location = Vector((0, 0, 0))  # Zero location
        scale = Vector((1, 1, 1))  # Unit scale
        
        # Use inverse coordinate conversion with same defaults as import
        _, arx_rot, _ = blender_to_arx_transform(location, rotation, scale, 0.1, flip_w=False, flip_x=False, flip_y=False, flip_z=False)
        
        arx_rotation = ArxQuat()
        arx_rotation.w = arx_rot.w
        arx_rotation.x = arx_rot.x
        arx_rotation.y = arx_rot.y
        arx_rotation.z = arx_rot.z
        return arx_rotation

    def _extract_bone_groups(self, armature_obj, bone_map, scale_factor):
        """Extract bone transformations for all groups."""
        max_group_index = max(bone_map.keys()) if bone_map else 0
        groups = []
        
        for i in range(max_group_index + 1):
            group = THEO_GROUPANIM()
            
            if i in bone_map:
                bone = bone_map[i]
                
                # Get bone transformations
                location = bone.location.copy()
                if bone.rotation_mode == 'QUATERNION':
                    rotation = bone.rotation_quaternion.copy()
                else:
                    rotation = bone.rotation_euler.to_quaternion()
                scale = bone.scale.copy()
                
                # Use inverse coordinate conversion with same defaults as import
                arx_loc, arx_rot, arx_scale = blender_to_arx_transform(location, rotation, scale, scale_factor, flip_w=False, flip_x=False, flip_y=False, flip_z=False)
                
                group.key_group = i
                group.translate.x = arx_loc.x
                group.translate.y = arx_loc.y
                group.translate.z = arx_loc.z
                
                group.Quaternion.w = arx_rot.w
                group.Quaternion.x = arx_rot.x
                group.Quaternion.y = arx_rot.y
                group.Quaternion.z = arx_rot.z
                
                # Check if scale is significantly different from (1,1,1) before writing
                if abs(scale.x - 1.0) > 0.001 or abs(scale.y - 1.0) > 0.001 or abs(scale.z - 1.0) > 0.001:
                    group.zoom.x = arx_scale.x
                    group.zoom.y = arx_scale.y
                    group.zoom.z = arx_scale.z
                else:
                    # No significant scaling, write zeros like the original
                    group.zoom.x = 0.0
                    group.zoom.y = 0.0
                    group.zoom.z = 0.0
            else:
                # Empty group
                group.key_group = -1
                group.translate.x = 0.0
                group.translate.y = 0.0
                group.translate.z = 0.0
                group.Quaternion.w = 1.0
                group.Quaternion.x = 0.0
                group.Quaternion.y = 0.0
                group.Quaternion.z = 0.0
                group.zoom.x = 0.0
                group.zoom.y = 0.0
                group.zoom.z = 0.0
                
            groups.append(group)
            
        return groups
