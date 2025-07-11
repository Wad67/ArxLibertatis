#!/usr/bin/env python3
"""
Test script for name matching and string comprehension logic.
This tests the core logic for matching animations to actors.
"""

import re
import os
from collections import defaultdict

def test_name_extraction():
    """Test actor name extraction from various file paths"""
    test_cases = [
        # Format: (file_path, expected_actor_name)
        ("human_base.ftl", "human"),
        ("goblin_base_tweaks.ftl", "goblin"), 
        ("rat_king.ftl", "rat_king"),
        ("player_base.ftl", "player"),
        ("npc_chicken_base.ftl", "npc_chicken"),
        ("models/characters/human_base.ftl", "human"),
        ("characters/goblins/goblin_lord_base.ftl", "goblin_lord"),
        ("items/weapons/sword_base.ftl", "sword"),
    ]
    
    print("=== TESTING NAME EXTRACTION ===")
    
    for file_path, expected in test_cases:
        basename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(basename)[0]
        
        # Clean up common suffixes
        name = name_without_ext.lower()
        suffixes_to_remove = ['_base', '_tweaks', '_lod', '_low', '_high']
        for suffix in suffixes_to_remove:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        status = "✓" if name == expected else "✗"
        print(f"  {status} {file_path} -> '{name}' (expected: '{expected}')")

def test_animation_classification():
    """Test animation type classification"""
    test_cases = [
        # Format: (animation_name, expected_type, expected_layer)
        ("human_normal_wait", "locomotion", 0),
        ("human_normal_walk", "locomotion", 0),
        ("human_run_forward", "locomotion", 0),
        ("human_1h_ready_part_1", "combat", 1),
        ("human_bare_attack_1", "combat", 1),
        ("human_cast_start", "spell", 2),
        ("human_drink", "interaction", 2),
        ("human_die", "death", 3),
        ("goblin_walk", "locomotion", 0),
        ("rat_attack", "combat", 1),
        ("chicken_walk", "locomotion", 0),
    ]
    
    print("\n=== TESTING ANIMATION CLASSIFICATION ===")
    
    def classify_animation_type(anim_name):
        name = anim_name.lower()
        
        locomotion_patterns = ['wait', 'idle', 'walk', 'run', 'strafe', 'turn', 'backward', 'sneak', 'crouch']
        combat_patterns = ['1h_', '2h_', 'bare_', 'attack', 'hit', 'ready', 'sword', 'bow']
        spell_patterns = ['cast', 'spell', 'magic']
        interaction_patterns = ['drink', 'eat', 'use', 'take', 'talk']
        death_patterns = ['die', 'death', 'dead']
        
        for pattern in death_patterns:
            if pattern in name:
                return 'death', 3
        for pattern in spell_patterns:
            if pattern in name:
                return 'spell', 2
        for pattern in interaction_patterns:
            if pattern in name:
                return 'interaction', 2
        for pattern in combat_patterns:
            if pattern in name:
                return 'combat', 1
        for pattern in locomotion_patterns:
            if pattern in name:
                return 'locomotion', 0
        return 'unknown', 0
    
    for anim_name, expected_type, expected_layer in test_cases:
        anim_type, layer = classify_animation_type(anim_name)
        
        type_match = "✓" if anim_type == expected_type else "✗"
        layer_match = "✓" if layer == expected_layer else "✗"
        
        print(f"  {type_match}{layer_match} {anim_name}")
        print(f"      -> type: {anim_type} (expected: {expected_type})")
        print(f"      -> layer: {layer} (expected: {expected_layer})")

def test_animation_actor_matching():
    """Test matching animations to actors"""
    test_cases = [
        # Format: (actor_name, animation_file, should_match)
        ("human", "human_normal_walk.tea", True),
        ("human", "human_1h_ready.tea", True),
        ("human", "goblin_walk.tea", False),
        ("goblin", "goblin_attack.tea", True),
        ("rat", "rat_king_idle.tea", True),  # Should match even with extra parts
        ("chicken", "chicken_walk.tea", True),
        ("player", "human_player_walk.tea", True),  # Should match with extra context
        ("sword", "human_sword_attack.tea", False),  # Sword is weapon, not actor
    ]
    
    print("\n=== TESTING ANIMATION-ACTOR MATCHING ===")
    
    def animation_matches_actor(tea_path, actor_name):
        tea_basename = os.path.basename(tea_path).lower()
        tea_name = os.path.splitext(tea_basename)[0]
        
        # Direct name match
        if actor_name in tea_name:
            return True
        
        # Check for common prefixes
        actor_parts = actor_name.split('_')
        for part in actor_parts:
            if len(part) > 3 and part in tea_name:
                return True
        
        return False
    
    for actor_name, animation_file, should_match in test_cases:
        matches = animation_matches_actor(animation_file, actor_name)
        
        status = "✓" if matches == should_match else "✗"
        result = "MATCH" if matches else "NO MATCH"
        expected = "MATCH" if should_match else "NO MATCH"
        
        print(f"  {status} '{actor_name}' vs '{animation_file}' -> {result} (expected: {expected})")

def test_base_actor_detection():
    """Test detection of 'base' actors vs specialized variants"""
    test_cases = [
        "human_base.ftl",
        "human_player.ftl", 
        "human_guard.ftl",
        "human_noble.ftl",
        "goblin_base.ftl",
        "goblin_king.ftl",
        "goblin_warrior.ftl",
        "rat_base.ftl",
        "rat_king.ftl",
    ]
    
    print("\n=== TESTING BASE ACTOR DETECTION ===")
    print("Actors with 'base' in name (likely main archetypes):")
    
    base_actors = []
    variant_actors = []
    
    for file_path in test_cases:
        basename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(basename)[0]
        
        if 'base' in name_without_ext.lower():
            base_actors.append(name_without_ext)
            print(f"  ✓ BASE: {name_without_ext}")
        else:
            variant_actors.append(name_without_ext)
            print(f"    VARIANT: {name_without_ext}")
    
    print(f"\nSummary:")
    print(f"  Base actors: {len(base_actors)}")
    print(f"  Variant actors: {len(variant_actors)}")

def test_pattern_robustness():
    """Test edge cases and unusual naming patterns"""
    test_cases = [
        # Test various naming conventions
        "HumanBase.ftl",  # CamelCase
        "human-base.ftl",  # Dash separator
        "human base.ftl",  # Space separator  
        "human_BASE.ftl",  # Mixed case
        "human_base_v2.ftl",  # Version numbers
        "human_base_final.ftl",  # Common suffixes
        "01_human_base.ftl",  # Numeric prefixes
        "characters/human/base.ftl",  # Directory structure
    ]
    
    print("\n=== TESTING PATTERN ROBUSTNESS ===")
    
    def extract_actor_name_robust(file_path):
        basename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(basename)[0]
        
        # Normalize case and separators
        name = name_without_ext.lower()
        name = re.sub(r'[-\s]+', '_', name)  # Convert dashes/spaces to underscores
        
        # Remove numeric prefixes
        name = re.sub(r'^\d+_', '', name)
        
        # Remove common suffixes
        suffixes = ['_base', '_tweaks', '_lod', '_low', '_high', '_v\d+', '_final', '_new']
        for suffix in suffixes:
            name = re.sub(suffix + r'$', '', name)
        
        return name
    
    for file_path in test_cases:
        actor_name = extract_actor_name_robust(file_path)
        print(f"  {file_path} -> '{actor_name}'")

def main():
    """Run all tests"""
    test_name_extraction()
    test_animation_classification()
    test_animation_actor_matching()
    test_base_actor_detection()
    test_pattern_robustness()
    
    print("\n=== TEST COMPLETE ===")
    print("Review the results above to identify any logic issues.")
    print("Patterns with ✗ marks need attention.")

if __name__ == "__main__":
    main()