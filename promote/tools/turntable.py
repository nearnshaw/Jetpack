"""Product shots of the built wearable for the marketplace video: a turntable frame sequence and a hero still.

  B=/Applications/Blender.app/Contents/MacOS/Blender
  $B -b blender/out/jetpack_suit_male.blend -P promote/tools/turntable.py -- turntable <frames_dir> [preview]
  $B -b blender/out/jetpack_suit_male.blend -P promote/tools/turntable.py -- hero promote/logo/jetpack_hero.png

Frames are transparent PNGs; the README has the ffmpeg line that lays them over the backdrop.
Same lighting and A-pose as blender/render_wearable.py (the marketplace thumbnail).
"""
import bpy, sys, os, math
from mathutils import Vector, Quaternion

argv = sys.argv[sys.argv.index('--') + 1:]
MODE, OUT = argv[0], argv[1]
PREVIEW = 'preview' in argv[2:]
SECONDS, FPS = 6, 30
START_DEG = 145          # starts on the back three-quarter view, where the pack is
scene = bpy.context.scene

arm = bpy.data.objects['Armature']
for side, sgn in (('Left', 1), ('Right', -1)):
    pb = arm.pose.bones['Avatar_%sArm' % side]
    pb.rotation_mode = 'QUATERNION'
    M = (arm.matrix_world @ pb.bone.matrix_local).to_3x3().normalized()
    pb.rotation_quaternion = Quaternion(M.inverted() @ Vector((0, 1, 0)), math.radians(62 * sgn))
bpy.context.view_layer.update()

scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.render_aa = '8' if PREVIEW else '32'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.display.shading.show_cavity = True
scene.display.shading.show_object_outline = True
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'Standard'

cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.lens = 50

def aim(loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()

# Spin the wearable about the suit's vertical axis, not the armature origin
PIVOT = Vector((0.0, 0.05, 0.0))
pivot = bpy.data.objects.new('Pivot', None)
scene.collection.objects.link(pivot)
pivot.location = PIVOT
arm.parent = pivot
arm.matrix_parent_inverse = pivot.matrix_world.inverted()

if MODE == 'turntable':
    os.makedirs(OUT, exist_ok=True)
    scale = 0.5 if PREVIEW else 1.0
    scene.render.resolution_x, scene.render.resolution_y = int(1920 * scale), int(1080 * scale)
    aim((0.0, -2.0, 1.45), (0.0, 0.05, 1.23))
    n = SECONDS * FPS
    step = 15 if PREVIEW else 1
    for i in range(0, n, step):
        pivot.rotation_euler = (0, 0, math.radians(START_DEG + 360 * i / n))
        scene.render.filepath = os.path.join(OUT, 'f%04d.png' % i)
        bpy.ops.render.render(write_still=True)
    print('TURNTABLE', n // step, 'frames ->', OUT)
elif MODE == 'hero':
    scene.render.resolution_x = scene.render.resolution_y = 1400
    pivot.rotation_euler = (0, 0, 0)
    cam.data.lens = 50
    aim((1.0, 1.15, 1.42), (-0.03, 0.06, 1.2))
    scene.render.filepath = OUT
    bpy.ops.render.render(write_still=True)
    print('HERO ->', OUT)
