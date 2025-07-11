#!/usr/bin/env python3
"""
Test script for Arx actor and animation discovery.
Run this separately from Blender to test the file discovery logic.
"""

import os
import glob
import re
from collections import defaultdict
import json

class ArxActor:
    def __init__(self, name):
        self.name = name
        self.ftl_files = []
        self.animations = {}  # animation_name -> {'path': str, 'type': str, 'layer': int}
        self.base_path = ""
        
    def add_ftl(self, ftl_path):
        self.ftl_files.append(ftl_path)
        if not self.base_path:
            self.base_path = os.path.dirname(ftl_path)
    
    def add_animation(self, anim_name, tea_path, anim_type="unknown", layer=0):
        self.animations[anim_name] = {
            'path': tea_path,
            'type': anim_type,
            'layer': layer
        }
    
    def to_dict(self):
        return {
            'name': self.name,
            'base_path': self.base_path,
            'ftl_files': self.ftl_files,
            'animation_count': len(self.animations),
            'animations': self.animations
        }

def extract_actor_name(file_path):
    """Extract actor name from file path"""
    basename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(basename)[0]
    
    # Clean up common suffixes
    name = name_without_ext.lower()
    
    # Remove common suffixes like _base, _tweaks, etc.
    suffixes_to_remove = ['_base', '_tweaks', '_lod', '_low', '_high']
    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    
    return name

def classify_animation_type(anim_name):
    """Classify animation by name patterns"""
    name = anim_name.lower()
    
    # Locomotion patterns (Layer 0)
    locomotion_patterns = [
        'wait', 'idle', 'walk', 'run', 'strafe', 'turn', 'backward',
        'sneak', 'crouch', 'jump', 'fall', 'land'
    ]
    
    # Combat patterns (Layer 1)
    combat_patterns = [
        '1h_', '2h_', 'bare_', 'dagger_', 'bow_', 'crossbow_',
        'sword', 'axe', 'mace', 'staff',
        'attack', 'hit', 'strike', 'swing', 'thrust',
        'parry', 'block', 'ready', 'unready'
    ]
    
    # Spell patterns (Layer 1-2)
    spell_patterns = [
        'cast', 'spell', 'magic', 'summon', 'enchant'
    ]
    
    # Interaction patterns (Layer 2)
    interaction_patterns = [
        'drink', 'eat', 'use', 'take', 'give', 'open', 'close',
        'talk', 'gesture', 'point', 'wave', 'bow'
    ]
    
    # Death/damage patterns (Layer 3)
    death_patterns = [
        'die', 'death', 'dead', 'damage', 'wound', 'hurt'
    ]
    
    # Check patterns in order of priority
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

def animation_matches_actor(tea_path, actor_name):
    """Check if an animation file belongs to an actor"""
    tea_basename = os.path.basename(tea_path).lower()
    tea_name = os.path.splitext(tea_basename)[0]
    
    # Direct name match
    if actor_name in tea_name:
        return True
    
    # Check if in same directory tree
    tea_dir = os.path.dirname(tea_path).lower()
    if actor_name in tea_dir:
        return True
    
    # Check for common prefixes
    actor_parts = actor_name.split('_')
    for part in actor_parts:
        if len(part) > 3 and part in tea_name:  # Only match meaningful parts
            return True
    
    return False

def discover_actors(root_path):
    """Discover all actors and their animations in a directory tree"""
    actors = {}
    
    print(f"Scanning directory: {root_path}")
    
    # First pass: Find all FTL files and create actors
    ftl_files = glob.glob(f"{root_path}/**/*.ftl", recursive=True)
    print(f"Found {len(ftl_files)} FTL files")
    
    for ftl_path in ftl_files:
        actor_name = extract_actor_name(ftl_path)
        
        if actor_name not in actors:
            actors[actor_name] = ArxActor(actor_name)
        
        actors[actor_name].add_ftl(ftl_path)
        print(f"  Actor: {actor_name} -> {os.path.basename(ftl_path)}")
    
    print(f"\nDiscovered {len(actors)} unique actors")
    
    # Second pass: Find animations for each actor
    tea_files = glob.glob(f"{root_path}/**/*.tea", recursive=True)
    print(f"Found {len(tea_files)} TEA files")
    
    unmatched_animations = []
    
    for tea_path in tea_files:
        tea_basename = os.path.basename(tea_path)
        anim_name = os.path.splitext(tea_basename)[0]
        
        matched = False
        for actor_name, actor in actors.items():
            if animation_matches_actor(tea_path, actor_name):
                anim_type, layer = classify_animation_type(anim_name)
                actor.add_animation(anim_name, tea_path, anim_type, layer)
                print(f"  {actor_name}: {anim_name} (type: {anim_type}, layer: {layer})")
                matched = True
                break
        
        if not matched:
            unmatched_animations.append(tea_path)
    
    print(f"\nMatching complete:")
    print(f"  Matched animations: {len(tea_files) - len(unmatched_animations)}")
    print(f"  Unmatched animations: {len(unmatched_animations)}")
    
    if unmatched_animations:
        print("\nUnmatched animations:")
        for tea_path in unmatched_animations[:10]:  # Show first 10
            print(f"  {tea_path}")
        if len(unmatched_animations) > 10:
            print(f"  ... and {len(unmatched_animations) - 10} more")
    
    return actors, unmatched_animations

def analyze_actors(actors):
    """Analyze discovered actors and their animation patterns"""
    print(f"\n=== ACTOR ANALYSIS ===")
    
    # Find actors with most animations (likely the main character types)
    actors_by_anim_count = sorted(actors.items(), key=lambda x: len(x[1].animations), reverse=True)
    
    print(f"\nTop actors by animation count:")
    for actor_name, actor in actors_by_anim_count[:10]:
        layer_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for anim_data in actor.animations.values():
            layer_counts[anim_data['layer']] += 1
            type_counts[anim_data['type']] += 1
        
        print(f"  {actor_name}: {len(actor.animations)} animations")
        print(f"    Layers: {dict(layer_counts)}")
        print(f"    Types: {dict(type_counts)}")
        print(f"    Path: {actor.base_path}")
        print()
    
    # Look for actors with 'base' in name
    base_actors = {name: actor for name, actor in actors.items() if 'base' in name}
    if base_actors:
        print(f"\nActors with 'base' in name ({len(base_actors)}):")
        for name, actor in base_actors.items():
            print(f"  {name}: {len(actor.animations)} animations")
    
    # Analyze animation types across all actors
    all_anim_types = defaultdict(int)
    all_layers = defaultdict(int)
    
    for actor in actors.values():
        for anim_data in actor.animations.values():
            all_anim_types[anim_data['type']] += 1
            all_layers[anim_data['layer']] += 1
    
    print(f"\nAnimation type distribution:")
    for anim_type, count in sorted(all_anim_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {anim_type}: {count}")
    
    print(f"\nAnimation layer distribution:")
    for layer, count in sorted(all_layers.items()):
        print(f"  Layer {layer}: {count}")

def save_results(actors, unmatched, output_file="actor_discovery_results.json"):
    """Save discovery results to JSON file"""
    results = {
        'actors': {name: actor.to_dict() for name, actor in actors.items()},
        'unmatched_animations': unmatched,
        'summary': {
            'total_actors': len(actors),
            'total_matched_animations': sum(len(actor.animations) for actor in actors.values()),
            'total_unmatched_animations': len(unmatched)
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")

def main():
    # Test with the current directory structure
    root_path = "/home/burner/Desktop/ArxLibertatis/plugins/blender/arx_addon"
    
    # You can change this to point to your actual Arx data directory
    if len(os.sys.argv) > 1:
        root_path = os.sys.argv[1]
    
    print(f"Testing actor discovery in: {root_path}")
    
    if not os.path.exists(root_path):
        print(f"ERROR: Path does not exist: {root_path}")
        return
    
    try:
        actors, unmatched = discover_actors(root_path)
        analyze_actors(actors)
        save_results(actors, unmatched)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()