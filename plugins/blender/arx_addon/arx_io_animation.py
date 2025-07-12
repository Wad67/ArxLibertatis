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

# Animation constants from Arx Libertatis source
# Based on enum AnimationNumber in src/script/Script.h and animation mapping in src/script/ScriptedAnimation.cpp
class AnimationNumber:
    """Animation constants from Arx Libertatis engine."""
    
    # Basic animations
    ANIM_NONE = -1
    ANIM_WAIT = 0
    ANIM_WALK = 1
    ANIM_WALK2 = 2
    ANIM_WALK3 = 3
    ANIM_ACTION = 8
    ANIM_ACTION2 = 9
    ANIM_ACTION3 = 10
    ANIM_HIT1 = 11
    ANIM_STRIKE1 = 12
    ANIM_DIE = 13
    ANIM_WAIT2 = 14
    ANIM_RUN = 15
    ANIM_RUN2 = 16
    ANIM_RUN3 = 17
    ANIM_ACTION4 = 18
    ANIM_ACTION5 = 19
    ANIM_ACTION6 = 20
    ANIM_ACTION7 = 21
    ANIM_ACTION8 = 22
    ANIM_ACTION9 = 23
    ANIM_ACTION10 = 24
    ANIM_TALK_NEUTRAL = 30
    ANIM_TALK_HAPPY = 31
    ANIM_TALK_ANGRY = 32
    ANIM_WALK_BACKWARD = 33
    
    # Bare hand combat
    ANIM_BARE_READY = 34
    ANIM_BARE_UNREADY = 35
    ANIM_BARE_WAIT = 36
    ANIM_BARE_STRIKE_LEFT_START = 37
    ANIM_BARE_STRIKE_LEFT_CYCLE = 38
    ANIM_BARE_STRIKE_LEFT = 39
    ANIM_BARE_STRIKE_RIGHT_START = 40
    ANIM_BARE_STRIKE_RIGHT_CYCLE = 41
    ANIM_BARE_STRIKE_RIGHT = 42
    ANIM_BARE_STRIKE_TOP_START = 43
    ANIM_BARE_STRIKE_TOP_CYCLE = 44
    ANIM_BARE_STRIKE_TOP = 45
    ANIM_BARE_STRIKE_BOTTOM_START = 46
    ANIM_BARE_STRIKE_BOTTOM_CYCLE = 47
    ANIM_BARE_STRIKE_BOTTOM = 48
    
    # One-handed weapon combat
    ANIM_1H_READY_PART_1 = 49
    ANIM_1H_READY_PART_2 = 50
    ANIM_1H_UNREADY_PART_1 = 51
    ANIM_1H_UNREADY_PART_2 = 52
    ANIM_1H_WAIT = 53
    ANIM_1H_STRIKE_LEFT_START = 54
    ANIM_1H_STRIKE_LEFT_CYCLE = 55
    ANIM_1H_STRIKE_LEFT = 56
    ANIM_1H_STRIKE_RIGHT_START = 57
    ANIM_1H_STRIKE_RIGHT_CYCLE = 58
    ANIM_1H_STRIKE_RIGHT = 59
    ANIM_1H_STRIKE_TOP_START = 60
    ANIM_1H_STRIKE_TOP_CYCLE = 61
    ANIM_1H_STRIKE_TOP = 62
    ANIM_1H_STRIKE_BOTTOM_START = 63
    ANIM_1H_STRIKE_BOTTOM_CYCLE = 64
    ANIM_1H_STRIKE_BOTTOM = 65
    
    # Two-handed weapon combat
    ANIM_2H_READY_PART_1 = 66
    ANIM_2H_READY_PART_2 = 67
    ANIM_2H_UNREADY_PART_1 = 68
    ANIM_2H_UNREADY_PART_2 = 69
    ANIM_2H_WAIT = 70
    ANIM_2H_STRIKE_LEFT_START = 71
    ANIM_2H_STRIKE_LEFT_CYCLE = 72
    ANIM_2H_STRIKE_LEFT = 73
    ANIM_2H_STRIKE_RIGHT_START = 74
    ANIM_2H_STRIKE_RIGHT_CYCLE = 75
    ANIM_2H_STRIKE_RIGHT = 76
    ANIM_2H_STRIKE_TOP_START = 77
    ANIM_2H_STRIKE_TOP_CYCLE = 78
    ANIM_2H_STRIKE_TOP = 79
    ANIM_2H_STRIKE_BOTTOM_START = 80
    ANIM_2H_STRIKE_BOTTOM_CYCLE = 81
    ANIM_2H_STRIKE_BOTTOM = 82
    
    # Dagger combat
    ANIM_DAGGER_READY_PART_1 = 83
    ANIM_DAGGER_READY_PART_2 = 84
    ANIM_DAGGER_UNREADY_PART_1 = 85
    ANIM_DAGGER_UNREADY_PART_2 = 86
    ANIM_DAGGER_WAIT = 87
    ANIM_DAGGER_STRIKE_LEFT_START = 88
    ANIM_DAGGER_STRIKE_LEFT_CYCLE = 89
    ANIM_DAGGER_STRIKE_LEFT = 90
    ANIM_DAGGER_STRIKE_RIGHT_START = 91
    ANIM_DAGGER_STRIKE_RIGHT_CYCLE = 92
    ANIM_DAGGER_STRIKE_RIGHT = 93
    ANIM_DAGGER_STRIKE_TOP_START = 94
    ANIM_DAGGER_STRIKE_TOP_CYCLE = 95
    ANIM_DAGGER_STRIKE_TOP = 96
    ANIM_DAGGER_STRIKE_BOTTOM_START = 97
    ANIM_DAGGER_STRIKE_BOTTOM_CYCLE = 98
    ANIM_DAGGER_STRIKE_BOTTOM = 99
    
    # Missile/bow combat
    ANIM_MISSILE_READY_PART_1 = 100
    ANIM_MISSILE_READY_PART_2 = 101
    ANIM_MISSILE_UNREADY_PART_1 = 102
    ANIM_MISSILE_UNREADY_PART_2 = 103
    ANIM_MISSILE_WAIT = 104
    ANIM_MISSILE_STRIKE_PART_1 = 105
    ANIM_MISSILE_STRIKE_PART_2 = 106
    ANIM_MISSILE_STRIKE_CYCLE = 107
    ANIM_MISSILE_STRIKE = 108
    
    # Shield animations
    ANIM_SHIELD_START = 109
    ANIM_SHIELD_CYCLE = 110
    ANIM_SHIELD_HIT = 111
    ANIM_SHIELD_END = 112
    
    # Magic casting
    ANIM_CAST_START = 113
    ANIM_CAST_CYCLE = 114
    ANIM_CAST = 115
    ANIM_CAST_END = 116
    
    # Advanced movement
    ANIM_DEATH_CRITICAL = 117
    ANIM_CROUCH = 118
    ANIM_CROUCH_WALK = 119
    ANIM_CROUCH_WALK_BACKWARD = 120
    ANIM_LEAN_RIGHT = 121
    ANIM_LEAN_LEFT = 122
    ANIM_JUMP = 123
    ANIM_HOLD_TORCH = 124
    ANIM_WALK_MINISTEP = 125
    ANIM_STRAFE_RIGHT = 126
    ANIM_STRAFE_LEFT = 127
    ANIM_MEDITATION = 128
    ANIM_WAIT_SHORT = 129
    
    # Fight movement
    ANIM_FIGHT_WALK_FORWARD = 130
    ANIM_FIGHT_WALK_BACKWARD = 131
    ANIM_FIGHT_WALK_MINISTEP = 132
    ANIM_FIGHT_STRAFE_RIGHT = 133
    ANIM_FIGHT_STRAFE_LEFT = 134
    ANIM_FIGHT_WAIT = 135
    
    # More advanced animations
    ANIM_LEVITATE = 136
    ANIM_CROUCH_START = 137
    ANIM_CROUCH_WAIT = 138
    ANIM_CROUCH_END = 139
    ANIM_JUMP_ANTICIPATION = 140
    ANIM_JUMP_UP = 141
    ANIM_JUMP_CYCLE = 142
    ANIM_JUMP_END = 143
    ANIM_TALK_NEUTRAL_HEAD = 144
    ANIM_TALK_ANGRY_HEAD = 145
    ANIM_TALK_HAPPY_HEAD = 146
    ANIM_STRAFE_RUN_LEFT = 147
    ANIM_STRAFE_RUN_RIGHT = 148
    ANIM_CROUCH_STRAFE_LEFT = 149
    ANIM_CROUCH_STRAFE_RIGHT = 150
    ANIM_WALK_SNEAK = 151
    ANIM_GRUNT = 152
    ANIM_JUMP_END_PART2 = 153
    ANIM_HIT_SHORT = 154
    ANIM_U_TURN_LEFT = 155
    ANIM_U_TURN_RIGHT = 156
    ANIM_RUN_BACKWARD = 157
    ANIM_U_TURN_LEFT_FIGHT = 158
    ANIM_U_TURN_RIGHT_FIGHT = 159

# Animation name to number mapping from ScriptedAnimation.cpp
ANIMATION_NAME_TO_NUMBER = {
    "wait": AnimationNumber.ANIM_WAIT,
    "wait2": AnimationNumber.ANIM_WAIT2,
    "walk": AnimationNumber.ANIM_WALK,
    "walk1": AnimationNumber.ANIM_WALK,
    "walk2": AnimationNumber.ANIM_WALK2,
    "walk3": AnimationNumber.ANIM_WALK3,
    "walk_backward": AnimationNumber.ANIM_WALK_BACKWARD,
    "walk_ministep": AnimationNumber.ANIM_WALK_MINISTEP,
    "wait_short": AnimationNumber.ANIM_WAIT_SHORT,
    "walk_sneak": AnimationNumber.ANIM_WALK_SNEAK,
    "action": AnimationNumber.ANIM_ACTION,
    "action1": AnimationNumber.ANIM_ACTION,
    "action2": AnimationNumber.ANIM_ACTION2,
    "action3": AnimationNumber.ANIM_ACTION3,
    "action4": AnimationNumber.ANIM_ACTION4,
    "action5": AnimationNumber.ANIM_ACTION5,
    "action6": AnimationNumber.ANIM_ACTION6,
    "action7": AnimationNumber.ANIM_ACTION7,
    "action8": AnimationNumber.ANIM_ACTION8,
    "action9": AnimationNumber.ANIM_ACTION9,
    "action10": AnimationNumber.ANIM_ACTION10,
    "hit1": AnimationNumber.ANIM_HIT1,
    "hit": AnimationNumber.ANIM_HIT1,
    "hold_torch": AnimationNumber.ANIM_HOLD_TORCH,
    "hit_short": AnimationNumber.ANIM_HIT_SHORT,
    "strike1": AnimationNumber.ANIM_STRIKE1,
    "strike": AnimationNumber.ANIM_STRIKE1,
    "shield_start": AnimationNumber.ANIM_SHIELD_START,
    "shield_cycle": AnimationNumber.ANIM_SHIELD_CYCLE,
    "shield_hit": AnimationNumber.ANIM_SHIELD_HIT,
    "shield_end": AnimationNumber.ANIM_SHIELD_END,
    "strafe_right": AnimationNumber.ANIM_STRAFE_RIGHT,
    "strafe_left": AnimationNumber.ANIM_STRAFE_LEFT,
    "strafe_run_left": AnimationNumber.ANIM_STRAFE_RUN_LEFT,
    "strafe_run_right": AnimationNumber.ANIM_STRAFE_RUN_RIGHT,
    "die": AnimationNumber.ANIM_DIE,
    "dagger_ready_part_1": AnimationNumber.ANIM_DAGGER_READY_PART_1,
    "dagger_ready_part_2": AnimationNumber.ANIM_DAGGER_READY_PART_2,
    "dagger_unready_part_1": AnimationNumber.ANIM_DAGGER_UNREADY_PART_1,
    "dagger_unready_part_2": AnimationNumber.ANIM_DAGGER_UNREADY_PART_2,
    "dagger_wait": AnimationNumber.ANIM_DAGGER_WAIT,
    "dagger_strike_left_start": AnimationNumber.ANIM_DAGGER_STRIKE_LEFT_START,
    "dagger_strike_left_cycle": AnimationNumber.ANIM_DAGGER_STRIKE_LEFT_CYCLE,
    "dagger_strike_left": AnimationNumber.ANIM_DAGGER_STRIKE_LEFT,
    "dagger_strike_right_start": AnimationNumber.ANIM_DAGGER_STRIKE_RIGHT_START,
    "dagger_strike_right_cycle": AnimationNumber.ANIM_DAGGER_STRIKE_RIGHT_CYCLE,
    "dagger_strike_right": AnimationNumber.ANIM_DAGGER_STRIKE_RIGHT,
    "dagger_strike_top_start": AnimationNumber.ANIM_DAGGER_STRIKE_TOP_START,
    "dagger_strike_top_cycle": AnimationNumber.ANIM_DAGGER_STRIKE_TOP_CYCLE,
    "dagger_strike_top": AnimationNumber.ANIM_DAGGER_STRIKE_TOP,
    "dagger_strike_bottom_start": AnimationNumber.ANIM_DAGGER_STRIKE_BOTTOM_START,
    "dagger_strike_bottom_cycle": AnimationNumber.ANIM_DAGGER_STRIKE_BOTTOM_CYCLE,
    "dagger_strike_bottom": AnimationNumber.ANIM_DAGGER_STRIKE_BOTTOM,
    "death_critical": AnimationNumber.ANIM_DEATH_CRITICAL,
    "run": AnimationNumber.ANIM_RUN,
    "run1": AnimationNumber.ANIM_RUN,
    "run2": AnimationNumber.ANIM_RUN2,
    "run3": AnimationNumber.ANIM_RUN3,
    "run_backward": AnimationNumber.ANIM_RUN_BACKWARD,
    "talk_neutral": AnimationNumber.ANIM_TALK_NEUTRAL,
    "talk_angry": AnimationNumber.ANIM_TALK_ANGRY,
    "talk_happy": AnimationNumber.ANIM_TALK_HAPPY,
    "talk_neutral_head": AnimationNumber.ANIM_TALK_NEUTRAL_HEAD,
    "talk_angry_head": AnimationNumber.ANIM_TALK_ANGRY_HEAD,
    "talk_happy_head": AnimationNumber.ANIM_TALK_HAPPY_HEAD,
    "bare_ready": AnimationNumber.ANIM_BARE_READY,
    "bare_unready": AnimationNumber.ANIM_BARE_UNREADY,
    "bare_wait": AnimationNumber.ANIM_BARE_WAIT,
    "bare_strike_left_start": AnimationNumber.ANIM_BARE_STRIKE_LEFT_START,
    "bare_strike_left_cycle": AnimationNumber.ANIM_BARE_STRIKE_LEFT_CYCLE,
    "bare_strike_left": AnimationNumber.ANIM_BARE_STRIKE_LEFT,
    "bare_strike_right_start": AnimationNumber.ANIM_BARE_STRIKE_RIGHT_START,
    "bare_strike_right_cycle": AnimationNumber.ANIM_BARE_STRIKE_RIGHT_CYCLE,
    "bare_strike_right": AnimationNumber.ANIM_BARE_STRIKE_RIGHT,
    "bare_strike_top_start": AnimationNumber.ANIM_BARE_STRIKE_TOP_START,
    "bare_strike_top_cycle": AnimationNumber.ANIM_BARE_STRIKE_TOP_CYCLE,
    "bare_strike_top": AnimationNumber.ANIM_BARE_STRIKE_TOP,
    "bare_strike_bottom_start": AnimationNumber.ANIM_BARE_STRIKE_BOTTOM_START,
    "bare_strike_bottom_cycle": AnimationNumber.ANIM_BARE_STRIKE_BOTTOM_CYCLE,
    "bare_strike_bottom": AnimationNumber.ANIM_BARE_STRIKE_BOTTOM,
    "1h_ready_part_1": AnimationNumber.ANIM_1H_READY_PART_1,
    "1h_ready_part_2": AnimationNumber.ANIM_1H_READY_PART_2,
    "1h_unready_part_1": AnimationNumber.ANIM_1H_UNREADY_PART_1,
    "1h_unready_part_2": AnimationNumber.ANIM_1H_UNREADY_PART_2,
    "1h_wait": AnimationNumber.ANIM_1H_WAIT,
    "1h_strike_left_start": AnimationNumber.ANIM_1H_STRIKE_LEFT_START,
    "1h_strike_left_cycle": AnimationNumber.ANIM_1H_STRIKE_LEFT_CYCLE,
    "1h_strike_left": AnimationNumber.ANIM_1H_STRIKE_LEFT,
    "1h_strike_right_start": AnimationNumber.ANIM_1H_STRIKE_RIGHT_START,
    "1h_strike_right_cycle": AnimationNumber.ANIM_1H_STRIKE_RIGHT_CYCLE,
    "1h_strike_right": AnimationNumber.ANIM_1H_STRIKE_RIGHT,
    "1h_strike_top_start": AnimationNumber.ANIM_1H_STRIKE_TOP_START,
    "1h_strike_top_cycle": AnimationNumber.ANIM_1H_STRIKE_TOP_CYCLE,
    "1h_strike_top": AnimationNumber.ANIM_1H_STRIKE_TOP,
    "1h_strike_bottom_start": AnimationNumber.ANIM_1H_STRIKE_BOTTOM_START,
    "1h_strike_bottom_cycle": AnimationNumber.ANIM_1H_STRIKE_BOTTOM_CYCLE,
    "1h_strike_bottom": AnimationNumber.ANIM_1H_STRIKE_BOTTOM,
    "2h_ready_part_1": AnimationNumber.ANIM_2H_READY_PART_1,
    "2h_ready_part_2": AnimationNumber.ANIM_2H_READY_PART_2,
    "2h_unready_part_1": AnimationNumber.ANIM_2H_UNREADY_PART_1,
    "2h_unready_part_2": AnimationNumber.ANIM_2H_UNREADY_PART_2,
    "2h_wait": AnimationNumber.ANIM_2H_WAIT,
    "2h_strike_left_start": AnimationNumber.ANIM_2H_STRIKE_LEFT_START,
    "2h_strike_left_cycle": AnimationNumber.ANIM_2H_STRIKE_LEFT_CYCLE,
    "2h_strike_left": AnimationNumber.ANIM_2H_STRIKE_LEFT,
    "2h_strike_right_start": AnimationNumber.ANIM_2H_STRIKE_RIGHT_START,
    "2h_strike_right_cycle": AnimationNumber.ANIM_2H_STRIKE_RIGHT_CYCLE,
    "2h_strike_right": AnimationNumber.ANIM_2H_STRIKE_RIGHT,
    "2h_strike_top_start": AnimationNumber.ANIM_2H_STRIKE_TOP_START,
    "2h_strike_top_cycle": AnimationNumber.ANIM_2H_STRIKE_TOP_CYCLE,
    "2h_strike_top": AnimationNumber.ANIM_2H_STRIKE_TOP,
    "2h_strike_bottom_start": AnimationNumber.ANIM_2H_STRIKE_BOTTOM_START,
    "2h_strike_bottom_cycle": AnimationNumber.ANIM_2H_STRIKE_BOTTOM_CYCLE,
    "2h_strike_bottom": AnimationNumber.ANIM_2H_STRIKE_BOTTOM,
    "missile_ready_part_1": AnimationNumber.ANIM_MISSILE_READY_PART_1,
    "missile_ready_part_2": AnimationNumber.ANIM_MISSILE_READY_PART_2,
    "missile_unready_part_1": AnimationNumber.ANIM_MISSILE_UNREADY_PART_1,
    "missile_unready_part_2": AnimationNumber.ANIM_MISSILE_UNREADY_PART_2,
    "missile_wait": AnimationNumber.ANIM_MISSILE_WAIT,
    "missile_strike_part_1": AnimationNumber.ANIM_MISSILE_STRIKE_PART_1,
    "missile_strike_part_2": AnimationNumber.ANIM_MISSILE_STRIKE_PART_2,
    "missile_strike_cycle": AnimationNumber.ANIM_MISSILE_STRIKE_CYCLE,
    "missile_strike": AnimationNumber.ANIM_MISSILE_STRIKE,
    "meditation": AnimationNumber.ANIM_MEDITATION,
    "cast_start": AnimationNumber.ANIM_CAST_START,
    "cast_cycle": AnimationNumber.ANIM_CAST_CYCLE,
    "cast": AnimationNumber.ANIM_CAST,
    "cast_end": AnimationNumber.ANIM_CAST_END,
    "crouch": AnimationNumber.ANIM_CROUCH,
    "crouch_walk": AnimationNumber.ANIM_CROUCH_WALK,
    "crouch_walk_backward": AnimationNumber.ANIM_CROUCH_WALK_BACKWARD,
    "crouch_strafe_left": AnimationNumber.ANIM_CROUCH_STRAFE_LEFT,
    "crouch_strafe_right": AnimationNumber.ANIM_CROUCH_STRAFE_RIGHT,
    "crouch_start": AnimationNumber.ANIM_CROUCH_START,
    "crouch_wait": AnimationNumber.ANIM_CROUCH_WAIT,
    "crouch_end": AnimationNumber.ANIM_CROUCH_END,
    "lean_right": AnimationNumber.ANIM_LEAN_RIGHT,
    "lean_left": AnimationNumber.ANIM_LEAN_LEFT,
    "levitate": AnimationNumber.ANIM_LEVITATE,
    "jump": AnimationNumber.ANIM_JUMP,
    "jump_anticipation": AnimationNumber.ANIM_JUMP_ANTICIPATION,
    "jump_up": AnimationNumber.ANIM_JUMP_UP,
    "jump_cycle": AnimationNumber.ANIM_JUMP_CYCLE,
    "jump_end": AnimationNumber.ANIM_JUMP_END,
    "jump_end_part2": AnimationNumber.ANIM_JUMP_END_PART2,
    "fight_walk_forward": AnimationNumber.ANIM_FIGHT_WALK_FORWARD,
    "fight_walk_backward": AnimationNumber.ANIM_FIGHT_WALK_BACKWARD,
    "fight_walk_ministep": AnimationNumber.ANIM_FIGHT_WALK_MINISTEP,
    "fight_strafe_right": AnimationNumber.ANIM_FIGHT_STRAFE_RIGHT,
    "fight_strafe_left": AnimationNumber.ANIM_FIGHT_STRAFE_LEFT,
    "fight_wait": AnimationNumber.ANIM_FIGHT_WAIT,
    "grunt": AnimationNumber.ANIM_GRUNT,
    "u_turn_left": AnimationNumber.ANIM_U_TURN_LEFT,
    "u_turn_right": AnimationNumber.ANIM_U_TURN_RIGHT,
    "u_turn_left_fight": AnimationNumber.ANIM_U_TURN_LEFT_FIGHT,
    "u_turn_right_fight": AnimationNumber.ANIM_U_TURN_RIGHT_FIGHT,
}

# Reverse mapping from number to name
ANIMATION_NUMBER_TO_NAME = {v: k for k, v in ANIMATION_NAME_TO_NUMBER.items()}

# AnimUseType flags from Animation.h
class AnimUseType:
    """Animation use flags from Arx Libertatis engine."""
    EA_LOOP = 1 << 0         # Animation loops
    EA_REVERSE = 1 << 1      # Animation plays in reverse
    EA_PAUSED = 1 << 2       # Animation is paused
    EA_ANIMEND = 1 << 3      # Animation has ended
    EA_STATICANIM = 1 << 4   # Static animation
    EA_STOPEND = 1 << 5      # Stop at end
    EA_FORCEPLAY = 1 << 6    # Force play animation
    EA_EXCONTROL = 1 << 7    # External control

# Looping animations based on engine logic (Animation.cpp lines 581-587)
LOOPING_ANIMATIONS = {
    AnimationNumber.ANIM_WALK,
    AnimationNumber.ANIM_WALK2,
    AnimationNumber.ANIM_WALK3,
    AnimationNumber.ANIM_RUN,
    AnimationNumber.ANIM_RUN2,
    AnimationNumber.ANIM_RUN3,
    # Additional looping animations based on common sense
    AnimationNumber.ANIM_WAIT,
    AnimationNumber.ANIM_WAIT2,
    AnimationNumber.ANIM_WAIT_SHORT,
    AnimationNumber.ANIM_BARE_WAIT,
    AnimationNumber.ANIM_1H_WAIT,
    AnimationNumber.ANIM_2H_WAIT,
    AnimationNumber.ANIM_DAGGER_WAIT,
    AnimationNumber.ANIM_MISSILE_WAIT,
    AnimationNumber.ANIM_FIGHT_WAIT,
    AnimationNumber.ANIM_CROUCH_WAIT,
    AnimationNumber.ANIM_SHIELD_CYCLE,
    AnimationNumber.ANIM_CAST_CYCLE,
    AnimationNumber.ANIM_LEVITATE,
    AnimationNumber.ANIM_MEDITATION,
}

def get_animation_number_from_name(name: str) -> int:
    """Get animation number from animation name using engine constants."""
    return ANIMATION_NAME_TO_NUMBER.get(name.lower(), AnimationNumber.ANIM_NONE)

def get_animation_name_from_number(num: int) -> str:
    """Get animation name from animation number using engine constants."""
    return ANIMATION_NUMBER_TO_NAME.get(num, "unknown")

def is_looping_animation(anim_number: int) -> bool:
    """Check if animation should loop based on engine-defined animation types."""
    return anim_number in LOOPING_ANIMATIONS

def detect_animation_type_from_action(action) -> int:
    """Detect animation type from Blender action name using engine constants."""
    if not action or not action.name:
        return AnimationNumber.ANIM_NONE
    
    # Try exact match first
    action_lower = action.name.lower()
    if action_lower in ANIMATION_NAME_TO_NUMBER:
        return ANIMATION_NAME_TO_NUMBER[action_lower]
    
    # Try partial matches for common patterns
    for anim_name, anim_number in ANIMATION_NAME_TO_NUMBER.items():
        if anim_name in action_lower:
            return anim_number
    
    # Default fallback
    return AnimationNumber.ANIM_WAIT

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
        try:
            data = self.teaSerializer.read(path)
            if not data:
                self.log.error("No animation data loaded from file: {}".format(path))
                return None
        except Exception as e:
            self.log.error("Failed to load TEA file %s: %s", path, str(e))
            # Show user-friendly error in Blender
            bpy.ops.object.dialog_operator(
                'INVOKE_DEFAULT',
                message=f"Failed to load animation file: {str(e)}"
            )
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

        # Detect animation type using engine constants
        anim_number = detect_animation_type_from_action(action)
        is_looping_anim = is_looping_animation(anim_number)
        
        # Check for step sounds in any frame (indicates footstep animation)
        has_step_sounds = any(frame.flags == 9 for frame in data)
        if has_step_sounds:
            is_looping_anim = True
            
        # Set custom properties including sound effects
        action["arx_animation_number"] = anim_number
        action["arx_animation_name"] = get_animation_name_from_number(anim_number)
        if is_looping_anim:
            action["arx_loop"] = True
            self.log.info("Animation '%s' (type %d) marked as looping based on engine constants", 
                         get_animation_name_from_number(anim_number), anim_number)
        
        # Store sound effect information in action custom properties
        sound_effects = []
        step_sound_frames = []
        for frame_idx, frame in enumerate(data):
            if frame.sampleName:
                sound_effects.append(f"{frame_idx}:{frame.sampleName}")
            if frame.flags == 9:  # Step sound flag
                step_sound_frames.append(frame_idx)
        
        if sound_effects:
            action["arx_sound_effects"] = ";".join(sound_effects)
            self.log.info("Animation has %d embedded sound effects: %s", len(sound_effects), sound_effects)
        
        if step_sound_frames:
            action["arx_step_sound_frames"] = ",".join(map(str, step_sound_frames))
            self.log.info("Animation has step sounds at frames: %s", step_sound_frames)
        
        # Store comprehensive TEA format metadata
        action["arx_tea_version"] = 2015  # Default version
        action["arx_tea_nb_frames"] = len(data)
        action["arx_tea_nb_groups"] = len(data[0].groups) if data else 0
        action["arx_tea_nb_key_frames"] = len(data)
        
        # Store frame-specific metadata for editing
        frame_flags = []
        frame_durations = []
        frame_info_strings = []
        keyframe_flags = []
        
        for frame_idx, frame in enumerate(data):
            frame_flags.append(str(frame.flags))
            frame_durations.append(str(frame.duration))
            frame_info_strings.append(frame.info_frame or "")
            
            # Pack keyframe boolean flags into a single integer
            flags = 0
            if frame.key_move: flags |= 1
            if frame.key_orient: flags |= 2
            if frame.key_morph: flags |= 4
            if frame.master_key_frame: flags |= 8
            if frame.key_frame: flags |= 16
            keyframe_flags.append(str(flags))
        
        action["arx_frame_flags"] = ",".join(frame_flags)
        action["arx_frame_durations"] = ",".join(frame_durations)
        action["arx_frame_info_strings"] = ";".join(frame_info_strings)
        action["arx_keyframe_flags"] = ",".join(keyframe_flags)
        
        self.log.info("Stored comprehensive TEA metadata: version=%d, frames=%d, groups=%d", 
                     2015, len(data), len(data[0].groups) if data else 0)

        self.log.info("Animation loaded successfully: %d TEA frames -> %d Blender frames (%.2fs at %dfps), %d animated bones",
                      len(data), total_blender_frames, total_duration, frame_rate, len(animatable_indices))

        return action
        
    def _show_error_dialog(self, message):
        """Show error dialog to user in Blender."""
        def draw(self, context):
            self.layout.label(text=message)
        
        bpy.context.window_manager.popup_menu(draw, title="Animation Import Error", icon='ERROR')

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
        
        # Pre-calculate frame durations and total animation length
        total_frames = frame_end - frame_start + 1
        frame_durations = []
        
        # Check if custom durations are stored
        custom_durations_str = action.get("arx_frame_durations", "")
        if custom_durations_str:
            custom_durations = []
            for d_str in custom_durations_str.split(","):
                try:
                    custom_durations.append(float(d_str))
                except ValueError:
                    custom_durations.append(1.0 / frame_rate)
            frame_durations = custom_durations
        
        # Fill missing durations with default
        while len(frame_durations) < total_frames:
            frame_durations.append(1.0 / frame_rate)
        
        try:
            bpy.context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode='POSE')
            
            for frame_idx, frame_num in enumerate(range(frame_start, frame_end + 1)):
                bpy.context.scene.frame_set(frame_num)
                
                # Use pre-calculated duration
                duration = frame_durations[frame_idx]
                
                # Get root translation and rotation from mesh object using absolute positioning
                root_translation = None
                root_rotation = None
                
                if obj.animation_data and obj.animation_data.action == action:
                    root_translation = self._extract_translation_from_object(obj, scale_factor)
                    root_rotation = self._extract_rotation_from_object(obj)
                
                # Extract bone transformations
                groups = self._extract_bone_groups(armature_obj, bone_map, scale_factor)
                
                # Detect if this frame has root movement
                has_root_movement = (root_translation is not None or root_rotation is not None)
                
                # Detect animation type and determine if it should have step sounds
                anim_number = action.get("arx_animation_number", detect_animation_type_from_action(action))
                is_looping = is_looping_animation(anim_number)
                
                has_bone_movement = any(
                    i in bone_map and (
                        abs(bone_map[i].location.length) > 0.001 or
                        abs(bone_map[i].rotation_quaternion.angle) > 0.001
                    ) for i in range(len(groups))
                )
                
                # Set step sound flag for movement frames in walking/running animations
                is_walk_run_anim = anim_number in {
                    AnimationNumber.ANIM_WALK, AnimationNumber.ANIM_WALK2, AnimationNumber.ANIM_WALK3,
                    AnimationNumber.ANIM_RUN, AnimationNumber.ANIM_RUN2, AnimationNumber.ANIM_RUN3,
                    AnimationNumber.ANIM_WALK_BACKWARD, AnimationNumber.ANIM_RUN_BACKWARD,
                    AnimationNumber.ANIM_CROUCH_WALK, AnimationNumber.ANIM_CROUCH_WALK_BACKWARD,
                    AnimationNumber.ANIM_FIGHT_WALK_FORWARD, AnimationNumber.ANIM_FIGHT_WALK_BACKWARD
                }
                step_sound_flag = 9 if (is_walk_run_anim and has_bone_movement) else -1
                
                # Extract sound effects from action custom properties
                sample_name = None
                sound_effects = action.get("arx_sound_effects", "")
                if sound_effects:
                    # Parse sound effects in format "frame:sample_name;frame:sample_name"
                    for effect in sound_effects.split(";"):
                        if ":" in effect:
                            effect_frame_str, effect_sample = effect.split(":", 1)
                            if int(effect_frame_str) == (frame_num - frame_start):
                                sample_name = effect_sample
                                break
                
                # Check if this frame should have step sound flag
                step_sound_frames_str = action.get("arx_step_sound_frames", "")
                is_step_sound_frame = False
                if step_sound_frames_str:
                    step_sound_frames = [int(f) for f in step_sound_frames_str.split(",") if f.strip()]
                    is_step_sound_frame = (frame_num - frame_start) in step_sound_frames
                
                # Override step sound flag if explicitly set
                if is_step_sound_frame:
                    step_sound_flag = 9
                
                # Extract comprehensive frame metadata from action
                frame_relative_idx = frame_idx  # Use frame index, not frame number
                
                # Extract frame flags
                frame_flags_str = action.get("arx_frame_flags", "")
                if frame_flags_str:
                    frame_flags_list = frame_flags_str.split(",")
                    if frame_relative_idx < len(frame_flags_list):
                        try:
                            step_sound_flag = int(frame_flags_list[frame_relative_idx])
                        except ValueError:
                            pass
                
                # Extract frame duration
                frame_durations_str = action.get("arx_frame_durations", "")
                if frame_durations_str:
                    frame_durations_list = frame_durations_str.split(",")
                    if frame_relative_idx < len(frame_durations_list):
                        try:
                            duration = float(frame_durations_list[frame_relative_idx])
                        except ValueError:
                            pass
                
                # Extract frame info string
                info_frame = ""
                frame_info_strings_str = action.get("arx_frame_info_strings", "")
                if frame_info_strings_str:
                    frame_info_list = frame_info_strings_str.split(";")
                    if frame_relative_idx < len(frame_info_list):
                        info_frame = frame_info_list[frame_relative_idx]
                
                # Extract keyframe flags
                key_move = bool(root_translation)
                key_orient = bool(root_rotation)
                key_morph = False
                master_key_frame = True
                key_frame = True
                
                keyframe_flags_str = action.get("arx_keyframe_flags", "")
                if keyframe_flags_str:
                    keyframe_flags_list = keyframe_flags_str.split(",")
                    if frame_relative_idx < len(keyframe_flags_list):
                        try:
                            flags = int(keyframe_flags_list[frame_relative_idx])
                            key_move = bool(flags & 1)
                            key_orient = bool(flags & 2)
                            key_morph = bool(flags & 4)
                            master_key_frame = bool(flags & 8)
                            key_frame = bool(flags & 16)
                        except ValueError:
                            pass
                
                # Create frame
                frame = TeaFrame(
                    duration=duration,
                    flags=step_sound_flag,
                    translation=root_translation,
                    rotation=root_rotation,
                    groups=groups,
                    sampleName=sample_name,
                    key_move=key_move,
                    key_orient=key_orient,
                    key_morph=key_morph,
                    master_key_frame=master_key_frame,
                    key_frame=key_frame,
                    info_frame=info_frame
                )
                
                frames.append(frame)
                
        finally:
            bpy.context.scene.frame_set(original_frame)
            bpy.ops.object.mode_set(mode='OBJECT')

        if not frames:
            self.log.error("No animation frames extracted")
            return False

        # Use version from action metadata if available
        export_version = action.get("arx_tea_version", version)
        
        # Write TEA file
        try:
            self.teaSerializer.write(frames, path, action.name, export_version)
            self.log.info("Successfully exported animation to %s (version %d)", path, export_version)
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
    
    def _convert_translation_delta_to_arx(self, location_delta, scale_factor):
        """Convert location delta from Blender to Arx coordinate system."""
        location = location_delta.copy()
        rotation = Quaternion((1, 0, 0, 0))  # Identity quaternion
        scale = Vector((1, 1, 1))  # Unit scale
        
        # Use inverse coordinate conversion
        arx_loc, _, _ = blender_to_arx_transform(location, rotation, scale, scale_factor, flip_w=False, flip_x=False, flip_y=False, flip_z=False)
        
        arx_location = SavedVec3()
        arx_location.x = arx_loc.x
        arx_location.y = arx_loc.y
        arx_location.z = arx_loc.z
        return arx_location
    
    def _convert_rotation_delta_to_arx(self, rotation_delta):
        """Convert rotation delta from Blender to Arx coordinate system."""
        location = Vector((0, 0, 0))  # Zero location
        scale = Vector((1, 1, 1))  # Unit scale
        
        # Use inverse coordinate conversion
        _, arx_rot, _ = blender_to_arx_transform(location, rotation_delta, scale, 0.1, flip_w=False, flip_x=False, flip_y=False, flip_z=False)
        
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
        
        # Ensure consistent group count across all frames
        for i in range(max_group_index + 1):
            group = THEO_GROUPANIM()
            
            # Initialize with default values matching original TEA files
            group.key_group = -1  # Will be overridden if bone exists
            group.translate.x = 0.0
            group.translate.y = 0.0
            group.translate.z = 0.0
            group.Quaternion.w = 1.0  # Identity quaternion
            group.Quaternion.x = 0.0
            group.Quaternion.y = 0.0
            group.Quaternion.z = 0.0
            group.zoom.x = 0.0  # Critical: default zoom to 0.0 like original files
            group.zoom.y = 0.0
            group.zoom.z = 0.0
            
            if i in bone_map:
                bone = bone_map[i]
                
                # Get bone transformations in pose space
                location = bone.location.copy()
                if bone.rotation_mode == 'QUATERNION':
                    rotation = bone.rotation_quaternion.copy()
                else:
                    rotation = bone.rotation_euler.to_quaternion()
                scale = bone.scale.copy()
                
                # Use inverse coordinate conversion
                arx_loc, arx_rot, arx_scale = blender_to_arx_transform(
                    location, rotation, scale, scale_factor, 
                    flip_w=False, flip_x=False, flip_y=False, flip_z=False
                )
                
                group.key_group = i
                group.translate.x = arx_loc.x
                group.translate.y = arx_loc.y
                group.translate.z = arx_loc.z
                
                group.Quaternion.w = arx_rot.w
                group.Quaternion.x = arx_rot.x
                group.Quaternion.y = arx_rot.y
                group.Quaternion.z = arx_rot.z
                
                # Handle scale - use 0.0 as default like original TEA files
                if abs(scale.x - 1.0) > 0.001 or abs(scale.y - 1.0) > 0.001 or abs(scale.z - 1.0) > 0.001:
                    group.zoom.x = arx_scale.x
                    group.zoom.y = arx_scale.y
                    group.zoom.z = arx_scale.z
                else:
                    # Default scale values (0.0 like original TEA files - engine treats as no scaling)
                    group.zoom.x = 0.0
                    group.zoom.y = 0.0
                    group.zoom.z = 0.0
            else:
                # Empty/unused group - mark as inactive
                group.key_group = -1
                group.translate.x = 0.0
                group.translate.y = 0.0
                group.translate.z = 0.0
                group.Quaternion.w = 1.0  # Identity quaternion
                group.Quaternion.x = 0.0
                group.Quaternion.y = 0.0
                group.Quaternion.z = 0.0
                group.zoom.x = 0.0  # Default scale like original TEA files
                group.zoom.y = 0.0
                group.zoom.z = 0.0
                
            groups.append(group)
            
        return groups
