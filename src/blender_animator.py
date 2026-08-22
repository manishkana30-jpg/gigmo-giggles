import sys
import os
import json
import argparse
import bpy
import bmesh

# Extract arguments passed after "--"
argv = sys.argv
if "--" not in argv:
    argv = []
else:
    argv = argv[argv.index("--") + 1:]

parser = argparse.ArgumentParser(description="Procedural Blender Animator with Rhubarb Lipsync")
parser.add_argument("--audio", required=True, help="Path to input audio file")
parser.add_argument("--visemes", required=True, help="Path to input Rhubarb JSON visemes")
parser.add_argument("--output", required=True, help="Path to output render file (.mp4)")
parser.add_argument("--fps", type=int, default=24, help="Frames per second")
args = parser.parse_args(argv)

# Clear existing objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Set up render settings
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.fps = args.fps
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 50  # Lower res for faster rendering on CPU
scene.render.filepath = args.output
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.audio_codec = 'AAC'
scene.render.ffmpeg.audio_bitrate = 192

# Add camera
bpy.ops.object.camera_add(location=(0, -6, 1), rotation=(math.radians(90), 0, 0))
camera = bpy.context.object
scene.camera = camera

# Add light
bpy.ops.object.light_add(type='SUN', location=(5, -5, 5))
light = bpy.context.object
light.data.energy = 5.0

# Create procedural "talking" character (a Subdivided Cube)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
head = bpy.context.object
bpy.ops.object.modifier_add(type='SUBSURF')
head.modifiers["Subdivision"].levels = 2
bpy.ops.object.modifier_apply(modifier="Subdivision")
bpy.ops.object.shade_smooth()

# Give it a material
mat = bpy.data.materials.new(name="CharacterMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.2, 0.6, 0.8, 1.0) # Blueish
head.data.materials.append(mat)

# Add Basis shape key
sk_basis = head.shape_key_add(name="Basis")

# Viseme deformations (simulated by pulling the bottom vertices down/in)
visemes = ["A", "B", "C", "D", "E", "F", "G", "H", "X"]

for v in visemes:
    sk = head.shape_key_add(name=v)
    sk.value = 0.0
    
    # Procedurally deform the mesh for this viseme
    for vert in head.data.shape_keys.key_blocks[v].data:
        # Check if vertex is in the lower front area (the "mouth" region)
        if vert.co.y < -0.5 and vert.co.z < 0.5:
            if v in ["C", "D"]: # Open wide
                vert.co.z -= 0.5
            elif v in ["B", "E", "H"]: # Slightly open
                vert.co.z -= 0.2
            elif v in ["F", "G"]: # Puckered / Tucked
                vert.co.x *= 0.5
                vert.co.z -= 0.1

# Load Visemes JSON
if os.path.exists(args.visemes):
    with open(args.visemes, 'r') as f:
        viseme_data = json.load(f)
        
    mouth_cues = viseme_data.get("mouthCues", [])
    
    # Calculate duration
    if mouth_cues:
        end_time = mouth_cues[-1]["end"]
        scene.frame_end = int(end_time * args.fps)
    else:
        scene.frame_end = args.fps * 5 # Default 5 secs
        
    # Set keyframes
    # Reset all shape keys to 0
    for v in visemes:
        head.data.shape_keys.key_blocks[v].value = 0.0
        
    for cue in mouth_cues:
        start_time = cue["start"]
        end_time = cue["end"]
        value = cue["value"]
        
        start_frame = int(start_time * args.fps)
        end_frame = int(end_time * args.fps)
        
        if value in head.data.shape_keys.key_blocks:
            sk = head.data.shape_keys.key_blocks[value]
            
            # Keyframe 1: Shape turns ON at start
            sk.value = 1.0
            sk.keyframe_insert("value", frame=start_frame)
            
            # Ensure other shape keys are OFF at this frame
            for other_v in visemes:
                if other_v != value:
                    other_sk = head.data.shape_keys.key_blocks[other_v]
                    other_sk.value = 0.0
                    other_sk.keyframe_insert("value", frame=start_frame)

# Idle Animation (Bounce and Rotate slightly)
head.animation_data_create()
head.animation_data.action = bpy.data.actions.new(name="Idle")
fc_z = head.animation_data.action.fcurves.new(data_path="location", index=2)
fc_rot = head.animation_data.action.fcurves.new(data_path="rotation_euler", index=2)

import math
for f in range(0, scene.frame_end + 1, int(args.fps / 2)): # Every half second
    t = f / args.fps
    head.location.z = 1.0 + (math.sin(t * 3.0) * 0.1)
    head.rotation_euler.z = math.sin(t * 1.5) * 0.2
    
    head.keyframe_insert("location", index=2, frame=f)
    head.keyframe_insert("rotation_euler", index=2, frame=f)

# Add Audio sequence to Video Sequencer (so audio exports with video)
if not scene.sequence_editor:
    scene.sequence_editor_create()
    
if os.path.exists(args.audio):
    scene.sequence_editor.sequences.new_sound("Audio", args.audio, 1, 1)

print(f"Starting render of {scene.frame_end} frames to {args.output}...")
bpy.ops.render.render(animation=True)
print("Render complete!")
