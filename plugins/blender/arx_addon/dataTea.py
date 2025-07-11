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

from .dataCommon import (
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
        return results
