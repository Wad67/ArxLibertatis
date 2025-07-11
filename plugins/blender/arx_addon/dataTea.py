# Copyright 2014-2019 Arx Libertatis Team (see the AUTHORS file)
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

from ctypes import (
    LittleEndianStructure,
    c_char,
    c_int32,
    c_uint32,
    c_float
)

try:
    from .dataCommon import (
        SavedVec3,
        ArxQuat,
        SerializationException,
        UnexpectedValueException
    )
except ImportError:
    from dataCommon import (
        SavedVec3,
        ArxQuat,
        SerializationException,
        UnexpectedValueException
    )

class THEA_HEADER(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("identity",      c_char * 20), # THEO_SIZE_IDENTITY_ANIM
        ("version",       c_uint32),
        ("anim_name",     c_char * 256), # SIZE_NAME
        ("nb_frames",     c_int32),
        ("nb_groups",     c_int32),
        ("nb_key_frames", c_int32),
    ]

class THEA_KEYFRAME_2014(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("num_frame",        c_int32),
        ("flag_frame",       c_int32),
        ("master_key_frame", c_int32), # bool
        ("key_frame",        c_int32), # bool
        ("key_move",         c_int32), # bool
        ("key_orient",       c_int32), # bool
        ("key_morph",        c_int32), # bool
        ("time_frame",       c_int32),
    ]

class THEA_KEYFRAME_2015(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("num_frame",        c_int32),
        ("flag_frame",       c_int32),
        ("info_frame",       c_char * 256), # SIZE_NAME
        ("master_key_frame", c_int32), # bool
        ("key_frame",        c_int32), # bool
        ("key_move",         c_int32), # bool
        ("key_orient",       c_int32), # bool
        ("key_morph",        c_int32), # bool
        ("time_frame",       c_int32),
    ]

class THEA_MORPH(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("unknown1", c_int32),
        ("unknown2", c_int32),
        ("unknown3", c_int32),
        ("unknown4", c_int32),
    ]

class THEO_GROUPANIM(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("key_group",  c_int32),
        ("angle",      c_char * 8), # ignored
        ("Quaternion", ArxQuat),
        ("translate",  SavedVec3),
        ("zoom",       SavedVec3),
    ]

class THEA_SAMPLE(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("sample_name",  c_char * 256), # SIZE_NAME
        ("sample_size",  c_int32)
    ]

from ctypes import sizeof
from typing import List
from collections import namedtuple
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TeaFrame = namedtuple("TeaFrame", ['duration', 'flags', 'translation', 'rotation', 'groups', 'sampleName'])

class TeaSerializer(object):
    def __init__(self):
        self.log = logging.getLogger(__name__)

    def read(self, fileName) -> List[TeaFrame]:
        f = open(fileName, "rb")
        data = f.read()
        f.close()
        self.log.debug("Read %i bytes from file %s", len(data), fileName)

        pos = 0
        header = THEA_HEADER.from_buffer_copy(data, pos)
        pos += sizeof(THEA_HEADER)

        self.log.debug("Header: Frames=%d, KeyFrames=%d", header.nb_frames, header.nb_key_frames)
        self.log.debug(
            "Header - Identity: {0}; Version: {1}; Frames: {2}; Groups {3}; KeyFrames {4}".format(
                header.identity, header.version, header.nb_frames, header.nb_groups, header.nb_key_frames))

        if header.nb_frames < 0:
            raise UnexpectedValueException("header.nb_frames = " + str(header.nb_frames))
        if header.nb_groups < 0:
            raise UnexpectedValueException("header.nb_groups = " + str(header.nb_groups))
        if header.nb_key_frames < 0:
            raise UnexpectedValueException("header.nb_key_frames = " + str(header.nb_key_frames))

        results = []
        default_frame_rate = 24.0  # Configurable default
        for i in range(header.nb_key_frames):
            if header.version == 2014:
                kf = THEA_KEYFRAME_2014.from_buffer_copy(data, pos)
                pos += sizeof(THEA_KEYFRAME_2014)
            elif header.version == 2015:
                kf = THEA_KEYFRAME_2015.from_buffer_copy(data, pos)
                pos += sizeof(THEA_KEYFRAME_2015)
                if kf.info_frame:
                    self.log.info("Keyframe str: %s", kf.info_frame.decode('iso-8859-1'))
            else:
                raise SerializationException("Unknown version: " + str(header.version))

            self.log.debug("Keyframe %d: raw time_frame=%d", i, kf.time_frame)
            if kf.time_frame > 0:
                duration = kf.time_frame / 1000.0  # Convert microseconds to seconds
            else:
                duration = 1.0 / default_frame_rate
                self.log.warning("Invalid time_frame=%d for keyframe %d, using default duration %.3fs",
                                 kf.time_frame, i, duration)

            flags = kf.flag_frame
            if flags not in (-1, 9):
                raise UnexpectedValueException("flag_frame = " + str(flags))

            translation = None
            if kf.key_move != 0:
                translation = SavedVec3.from_buffer_copy(data, pos)
                pos += sizeof(SavedVec3)

            rotation = None
            if kf.key_orient != 0:
                pos += 8  # skip THEO_ANGLE
                rotation = ArxQuat.from_buffer_copy(data, pos)
                pos += sizeof(ArxQuat)

            if kf.key_morph != 0:
                morph = THEA_MORPH.from_buffer_copy(data, pos)
                pos += sizeof(THEA_MORPH)

            groupsList = (THEO_GROUPANIM * header.nb_groups).from_buffer_copy(data, pos)
            pos += sizeof(groupsList)

            num_sample = c_int32.from_buffer_copy(data, pos)
            pos += sizeof(c_int32)

            sampleName = None
            if num_sample.value != -1:
                sample = THEA_SAMPLE.from_buffer_copy(data, pos)
                pos += sizeof(THEA_SAMPLE)
                sampleName = sample.sample_name.decode('iso-8859-1')
                pos += sample.sample_size

            pos += 4  # skip num_sfx
            results.append(TeaFrame(
                duration=duration,
                flags=flags,
                translation=translation,
                rotation=rotation,
                groups=groupsList,
                sampleName=sampleName
            ))

        self.log.debug("File loaded with %d frames", len(results))
        
        # Perform interpolation like the engine does
        interpolated_results = self._interpolate_missing_transforms(results)
        
        return interpolated_results
    
    def _interpolate_missing_transforms(self, frames):
        """
        Interpolate missing translation and rotation data between keyframes,
        following the same logic as the Arx engine (Animation.cpp lines 374-422).
        """
        if not frames:
            return frames
            
        # Convert to mutable list for modification
        interpolated_frames = []
        for frame in frames:
            # Create a copy with the same structure
            interpolated_frames.append(TeaFrame(
                duration=frame.duration,
                flags=frame.flags,
                translation=frame.translation,
                rotation=frame.rotation,
                groups=frame.groups,
                sampleName=frame.sampleName
            ))
        
        # Interpolate missing translations
        self._interpolate_translations(interpolated_frames)
        
        # Interpolate missing rotations  
        self._interpolate_rotations(interpolated_frames)
        
        return interpolated_frames
    
    def _interpolate_translations(self, frames):
        """
        Interpolate missing translation data between keyframes.
        Based on Animation.cpp lines 374-395.
        """
        for i in range(len(frames)):
            if frames[i].translation is None:
                # Find previous frame with translation data
                k = i - 1
                while k >= 0 and frames[k].translation is None:
                    k -= 1
                
                # Find next frame with translation data
                j = i + 1
                while j < len(frames) and frames[j].translation is None:
                    j += 1
                
                if j < len(frames) and k >= 0:
                    # Linear interpolation between keyframes
                    r1 = self._get_time_between_keyframes(frames, k, i)
                    r2 = self._get_time_between_keyframes(frames, i, j)
                    
                    if r1 + r2 > 0:
                        tot = 1.0 / (r1 + r2)
                        r1 *= tot
                        r2 *= tot
                        
                        # Interpolate translation
                        trans_k = frames[k].translation
                        trans_j = frames[j].translation
                        
                        interpolated_translation = SavedVec3()
                        interpolated_translation.x = trans_j.x * r1 + trans_k.x * r2
                        interpolated_translation.y = trans_j.y * r1 + trans_k.y * r2
                        interpolated_translation.z = trans_j.z * r1 + trans_k.z * r2
                        
                        # Update frame with interpolated translation
                        frames[i] = TeaFrame(
                            duration=frames[i].duration,
                            flags=frames[i].flags,
                            translation=interpolated_translation,
                            rotation=frames[i].rotation,
                            groups=frames[i].groups,
                            sampleName=frames[i].sampleName
                        )
                        
                        self.log.debug("Interpolated translation for frame %d: x=%.3f, y=%.3f, z=%.3f", 
                                     i, interpolated_translation.x, interpolated_translation.y, interpolated_translation.z)
    
    def _interpolate_rotations(self, frames):
        """
        Interpolate missing rotation data between keyframes.
        Based on Animation.cpp lines 397-422.
        """
        for i in range(len(frames)):
            if frames[i].rotation is None:
                # Find previous frame with rotation data
                k = i - 1
                while k >= 0 and frames[k].rotation is None:
                    k -= 1
                
                # Find next frame with rotation data
                j = i + 1
                while j < len(frames) and frames[j].rotation is None:
                    j += 1
                
                if j < len(frames) and k >= 0:
                    # Linear interpolation between keyframes
                    r1 = self._get_time_between_keyframes(frames, k, i)
                    r2 = self._get_time_between_keyframes(frames, i, j)
                    
                    if r1 + r2 > 0:
                        tot = 1.0 / (r1 + r2)
                        r1 *= tot
                        r2 *= tot
                        
                        # Interpolate rotation (quaternion)
                        rot_k = frames[k].rotation
                        rot_j = frames[j].rotation
                        
                        interpolated_rotation = ArxQuat()
                        interpolated_rotation.w = rot_j.w * r1 + rot_k.w * r2
                        interpolated_rotation.x = rot_j.x * r1 + rot_k.x * r2
                        interpolated_rotation.y = rot_j.y * r1 + rot_k.y * r2
                        interpolated_rotation.z = rot_j.z * r1 + rot_k.z * r2
                        
                        # Update frame with interpolated rotation
                        frames[i] = TeaFrame(
                            duration=frames[i].duration,
                            flags=frames[i].flags,
                            translation=frames[i].translation,
                            rotation=interpolated_rotation,
                            groups=frames[i].groups,
                            sampleName=frames[i].sampleName
                        )
                        
                        self.log.debug("Interpolated rotation for frame %d: w=%.3f, x=%.3f, y=%.3f, z=%.3f", 
                                     i, interpolated_rotation.w, interpolated_rotation.x, interpolated_rotation.y, interpolated_rotation.z)
    
    def _get_time_between_keyframes(self, frames, start_idx, end_idx):
        """
        Calculate time between two keyframes based on frame durations.
        """
        if start_idx >= end_idx:
            return 0.0
            
        total_time = 0.0
        for i in range(start_idx, end_idx):
            total_time += frames[i].duration
            
        return total_time
