"""Render preview shots (and optionally the 256px marketplace thumbnail) of a built wearable .blend.

  Blender --background blender/out/jetpack_suit_male.blend --python render_wearable.py -- <out_dir> [thumbnail.png]
"""
import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = argv[0]
THUMB = argv[1] if len(argv) > 1 else None
os.makedirs(OUT, exist_ok=True)
scene = bpy.context.scene

# Pose the T-pose arms down into a relaxed A-pose so the render reads like a worn garment
arm = bpy.data.objects['Armature']
from mathutils import Quaternion
for side, sgn in (('Left', 1), ('Right', -1)):
    pb = arm.pose.bones['Avatar_%sArm' % side]
    pb.rotation_mode = 'QUATERNION'
    M = (arm.matrix_world @ pb.bone.matrix_local).to_3x3().normalized()
    axis = M.inverted() @ Vector((0, 1, 0))
    pb.rotation_quaternion = Quaternion(axis, math.radians(62 * sgn))
bpy.context.view_layer.update()

scene.render.engine = 'BLENDER_WORKBENCH'
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
cam.data.lens = 60

def aim(loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()

def shot(path, loc, target, res=512):
    scene.render.resolution_x = scene.render.resolution_y = res
    aim(loc, target)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)

T = (0, 0.05, 1.22)
VIEWS = {
    'front': ((0.0, -2.4, 1.35), T),
    'back': ((0.0, 2.4, 1.35), T),
    'back34': ((1.6, 1.8, 1.55), T),
    'side': ((2.4, 0.15, 1.3), T),
}
for name, (loc, tgt) in VIEWS.items():
    shot(os.path.join(OUT, '%s.png' % name), loc, tgt)
if THUMB:
    cam.data.lens = 50
    shot(THUMB, (1.0, 1.15, 1.42), (-0.03, 0.06, 1.2), res=256)
