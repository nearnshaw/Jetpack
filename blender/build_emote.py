"""Build the looping jetpack-thrust emote (avatar clip + smoke-puff prop clip) as a scene emote GLB.

  Blender --background <dcl-blender-toolkit>/assets/Avatar_File.blend --python build_emote.py -- <out_dir> <wearable_info.json> [move] [pose]

`move` builds the variant for rising while steering (jetpack_thrust_move_emote.glb); the default is rising
straight up (jetpack_thrust_emote.glb). The avatar clip is the same; only the puffs' baked position differs.

Emotes 2.0 layout: `Armature` (avatar, clip `Jetpack_Avatar`) + `Armature_Prop` (clip `Jetpack_Prop`),
both clips the same length. Particles are meshes skinned 1:1 to prop bones, animated by baked keys, since
emotes can't carry object animation or particle systems.
"""
import bpy, bmesh, math, os, sys, json
from mathutils import Vector, Quaternion, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_DIR, INFO = argv[0], argv[1]
STAGE = 'pose' if 'pose' in argv[2:] else 'all'
VARIANT = 'move' if 'move' in argv[2:] else 'rise'
SUFFIX = '_move' if VARIANT == 'move' else ''
os.makedirs(OUT_DIR, exist_ok=True)
info = json.load(open(INFO))

LOOP = 30                       # frames per loop at 30 fps -> 1.0 s
FIRST, LAST = 1, LOOP + 1       # last frame == first frame for a seamless loop

scene = bpy.context.scene
scene.render.fps = 30
scene.render.fps_base = 1.0
arm = bpy.data.objects['Armature']
vl = bpy.context.view_layer
BASE = {}
PROPS = {
    'CTRL_Avatar_UpperBody': ['FK > IK Arm L', 'FK > IK Arm R', 'FK > IK Leg L', 'FK > IK Leg R',
                              'IsoRot Arm  FK L', 'IsoRot Arm  FK R'],
    'CTRL_Avatar_Head': ['Inherit Rotation'],
}

# ------------------------------------------------------------------ rig helpers (skill: avatar-animations)
def capture_base():
    scene.frame_set(0)
    for pb in arm.pose.bones:
        BASE[pb.name] = (pb.location.copy(), pb.rotation_quaternion.copy(), pb.rotation_euler.copy(),
                         pb.scale.copy(), {k: pb[k] for k in PROPS.get(pb.name, [])})

def reset_all():
    for pb in arm.pose.bones:
        loc, rq, re, sc, props = BASE[pb.name]
        pb.location = loc; pb.rotation_quaternion = rq; pb.rotation_euler = re; pb.scale = sc
        for k, v in props.items():
            pb[k] = v
    vl.update()

def wpos(n): return arm.matrix_world @ arm.pose.bones[n].head
def wtail(n): return arm.matrix_world @ arm.pose.bones[n].tail

def rl(n, axis, deg):
    if isinstance(axis, str):
        axis = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}[axis]
    pb = arm.pose.bones[n]
    q = Quaternion(axis, math.radians(deg))
    if pb.rotation_mode == 'QUATERNION':
        pb.rotation_quaternion = pb.rotation_quaternion @ q
    else:
        pb.rotation_euler = (pb.rotation_euler.to_quaternion() @ q).to_euler(pb.rotation_mode)

def rw(n, axis, deg):
    if isinstance(axis, str):
        axis = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}[axis]
    vl.update()
    pb = arm.pose.bones[n]
    M = (arm.matrix_world @ pb.matrix).to_3x3().normalized()
    rl(n, M.inverted() @ Vector(axis), deg)

def key_all(frame, deform=False):
    vl.update()
    for pb in arm.pose.bones:
        if not pb.name.startswith('CTRL_') and not (deform and pb.bone.use_deform):
            continue
        pb.keyframe_insert('location', frame=frame)
        pb.keyframe_insert('rotation_quaternion' if pb.rotation_mode == 'QUATERNION' else 'rotation_euler', frame=frame)
        pb.keyframe_insert('scale', frame=frame)
        for k in PROPS.get(pb.name, []):
            pb.keyframe_insert('["%s"]' % k, frame=frame)

def new_action(obj, name, slot_name):
    act = bpy.data.actions.new(name)
    slot = act.slots.new('OBJECT', slot_name)
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = act
    obj.animation_data.action_slot = slot
    act.use_fake_user = True
    return act

def auto_sign(fn, metric):
    reset_all(); before = metric()
    fn(15); vl.update(); after = metric()
    reset_all()
    return 1 if after > before else -1

def auto_sign_pm(fn, metric, deg):
    """Sign for a hinge where a small test is ambiguous: bending a straight finger either way brings its
    tip closer to the wrist. Compare a large bend each way against a palm-side reference instead."""
    reset_all(); fn(deg); vl.update(); plus = metric()
    reset_all(); fn(-deg); vl.update(); minus = metric()
    reset_all()
    return 1 if plus > minus else -1

def palm_normal(full):
    """Unit normal of the knuckle plane, pointing to the palm side (where the idle thumb tip sits)."""
    reset_all()
    h, i1, p1 = (wpos('Avatar_%sHand%s' % (full, b)) for b in ('', 'Index1', 'Pinky1'))
    n = ((i1 + p1) / 2 - h).cross(p1 - i1).normalized()
    return n if (wpos('Avatar_%sHandThumb4' % full) - i1).dot(n) > 0 else -n

# ------------------------------------------------------------------ avatar clip
capture_base()
S = {}
for s, full in (('L', 'Left'), ('R', 'Right')):
    out = 1 if s == 'L' else -1
    S['abd' + s] = auto_sign(lambda d, s=s: rw('CTRL_FK_Avatar_Arm.' + s, 'Y', d),
                             lambda full=full, out=out: out * wpos('Avatar_%sHand' % full).x)
    S['back' + s] = auto_sign(lambda d, s=s: rw('CTRL_FK_Avatar_Arm.' + s, 'X', d),
                              lambda full=full: wpos('Avatar_%sHand' % full).y)
    S['elbow' + s] = auto_sign(lambda d, s=s: rl('CTRL_FK_Avatar_ForeArm.' + s, 'X', d),
                               lambda full=full: -wpos('Avatar_%sHand' % full).y)
    # Finger controls curl on local Z; local X swings the finger sideways in the plane of the palm.
    # A curl moves the tip toward the palm side of the knuckle plane.
    n = palm_normal(full)
    S['curl' + s] = auto_sign_pm(lambda d, s=s: [rl('CTRL_Avatar_HandIndex%d.%s' % (k, s), 'Z', d) for k in (1, 2, 3)],
                                 lambda full=full, n=n: wpos('Avatar_%sHandIndex4' % full).dot(n), 50)
    S['thumbcurl' + s] = auto_sign_pm(lambda d, s=s: [rl('CTRL_Avatar_HandThumb%d.%s' % (k, s), 'Z', d) for k in (2, 3)],
                                      lambda full=full, n=n: wpos('Avatar_%sHandThumb4' % full).dot(n), 35)
    # Thumb1 on local X swings the whole thumb across the palm, toward the pinky's base.
    S['thumbacross' + s] = auto_sign_pm(lambda d, s=s: rl('CTRL_Avatar_HandThumb1.' + s, 'X', d),
                                        lambda full=full: -(wpos('Avatar_%sHandThumb4' % full) - wpos('Avatar_%sHandPinky1' % full)).length, 35)
S['arch'] = auto_sign(lambda d: rw('CTRL_FK_Avatar_Spine1', 'X', d), lambda: wpos('Avatar_Neck').y)
S['headup'] = auto_sign(lambda d: rl('CTRL_Avatar_Head', 'X', d), lambda: wtail('Avatar_Head').y)
print('SIGNS', S)

def thrust_pose(j=0.0):
    """Arms flared out and a little back, elbows bent, fists, torso leaning slightly into the thrust. j = rumble (-1..1)."""
    reset_all()
    for sp in ('CTRL_FK_Avatar_Spine', 'CTRL_FK_Avatar_Spine1', 'CTRL_FK_Avatar_Spine2'):
        rw(sp, 'X', S['arch'] * (-2 + 0.4 * j))   # negative = slight forward lean into the thrust
    rl('CTRL_Avatar_Head', 'X', S['headup'] * (4 - 1 * j))
    for s in 'LR':
        rw('CTRL_FK_Avatar_Arm.' + s, 'Y', S['abd' + s] * (30 + 2.5 * j))
        rw('CTRL_FK_Avatar_Arm.' + s, 'X', S['back' + s] * 8)
        rl('CTRL_FK_Avatar_ForeArm.' + s, 'X', S['elbow' + s] * (28 - 4 * j))
        for finger in ('Index', 'Middle', 'Ring', 'Pinky'):
            for k, deg in ((1, 60), (2, 70), (3, 45)):         # a fist bends the middle joint most
                rl('CTRL_Avatar_Hand%s%d.%s' % (finger, k, s), 'Z', S['curl' + s] * deg)
        rl('CTRL_Avatar_HandThumb1.' + s, 'X', S['thumbacross' + s] * 35)   # thumb wraps over index + middle
        for k, deg in ((2, 30), (3, 45)):
            rl('CTRL_Avatar_HandThumb%d.%s' % (k, s), 'Z', S['thumbcurl' + s] * deg)
    vl.update()

def in_area():
    vl.update()
    bad = []
    h = wpos('Avatar_Hips')
    if abs(h.x) > 1.0 or abs(h.y) > 1.0:
        bad.append('ROOT')
    for pb in arm.pose.bones:
        if pb.bone.use_deform:
            for p in (wpos(pb.name), wtail(pb.name)):
                if abs(p.x) > 2 or abs(p.y) > 2 or p.z < 0 or p.z > 4:
                    bad.append(pb.name)
    return bad

# rumble keys: identical first/last frame so the loop closes
RUMBLE = [(1, 0.0), (6, 1.0), (11, -0.6), (16, 0.8), (21, -1.0), (26, 0.5), (LAST, 0.0)]
act_avatar = new_action(arm, 'Jetpack_Avatar', 'Avatar_Animation')
for frame, j in RUMBLE:
    thrust_pose(j)
    print('POSE', frame, 'handL', [round(v, 3) for v in wpos('Avatar_LeftHand')],
          'handR', [round(v, 3) for v in wpos('Avatar_RightHand')],
          'head', [round(v, 3) for v in wpos('Avatar_Head')], 'area', in_area() or 'ok')
    key_all(frame, deform=(frame in (FIRST, LAST)))

# ------------------------------------------------------------------ prop armature + FX meshes
for o in list(bpy.data.objects):
    if o.name.startswith('Armature_Prop'):
        bpy.data.objects.remove(o, do_unlink=True)

# Nozzle exits, measured on the wearable in rest pose; carried through Avatar_Spine2's motion per frame
NOZZLES = [Vector(n) for n in info['nozzles']]                     # [right(-x), left(+x)]
spine_rest = arm.matrix_world @ arm.data.bones['Avatar_Spine2'].matrix_local

def nozzle_world(i):
    vl.update()
    spine_pose = arm.matrix_world @ arm.pose.bones['Avatar_Spine2'].matrix
    return spine_pose @ spine_rest.inverted() @ NOZZLES[i]

# The Explorer parents emote props to the avatar's root, not to a bone, and the scene plays this emote with
# the upper-body mask: the hips (and so the spine and the pack) follow the Explorer's locomotion clip, not
# this clip's idle hips. Holding F climbs at 4-5 m/s, so the burn plays over the jump "rise" loops, whose hips
# differ by 5-6 cm between rising straight up and rising while steering (jog and run share the same hips).
# Each variant bakes the puffs against one of them; src/jetpack.ts swaps variants by horizontal speed.
# Avatar_Hips at the first key of each clip, in Blender armature space (cm, w-first quaternion), read from
# unity-explorer fc4eef391 Explorer/Assets/DCL/AvatarRendering/AvatarShape/Assets/Animations/*.anim
# (Unity armature-local (x, y, z) -> Blender (-x, -z, -y)).
LOCO_HIPS = {
    'Idle': ((-0.007, 98.514, -0.197), (0.02380, -0.02380, -0.69668, -0.71659)),
    'Jump_Rise_Loop': ((-0.000, 105.008, -2.537), (0.00000, 0.00000, 0.80579, 0.59220)),
    'Run_Jump_Rise_Loop': ((2.267, 106.868, 0.927), (0.04489, 0.00971, -0.75243, -0.65707)),
}

def loco_delta(clip):
    """World-space transform taking the pack from the idle hips to `clip`'s hips."""
    p0, q0 = Vector(LOCO_HIPS['Idle'][0]), Quaternion(LOCO_HIPS['Idle'][1])
    p, q = Vector(LOCO_HIPS[clip][0]), Quaternion(LOCO_HIPS[clip][1])
    rel = (q @ q0.inverted()).to_matrix().to_4x4()
    AW = arm.matrix_world
    return AW @ Matrix.Translation(p) @ rel @ Matrix.Translation(-p0) @ AW.inverted()

FLIGHT = loco_delta('Run_Jump_Rise_Loop' if VARIANT == 'move' else 'Jump_Rise_Loop')

# Thrust is smoke puffs only: no flame cone, so there is no crisp origin to betray the few cm the pack can sit
# off its baked position (props hang off the avatar root, not the pack's bone; see above). Puffs are born
# PUFF_TOP above the nozzle exit, inside the bell, in case the pack rides higher, and fade out by PUFF_LOW below
# it. Until they leave the exit they stay on the axis and no wider than the bell's inside (BELL_R at the exit,
# narrowing toward its roof), so they don't poke out of the tank's sides when the pack rides lower.
N_PUFF, PUFF_TOP, PUFF_LOW, PUFF_R = 16, 0.025, -0.22, 0.05
BELL_R, BELL_TAPER = 0.041, 0.6                                      # build_wearable.py TANK_PROFILE
bone_specs = []                                                      # (name, nozzle, index)
for i, side in enumerate(('R', 'L')):
    bone_specs += [('Puff_%s_%d' % (side, k), i, k) for k in range(N_PUFF)]

prop_data = bpy.data.armatures.new('Armature_Prop')
prop = bpy.data.objects.new('Armature_Prop', prop_data)
scene.collection.objects.link(prop)
for o in bpy.context.selected_objects:
    o.select_set(False)
vl.objects.active = prop
bpy.ops.object.mode_set(mode='EDIT')
for name, i, k in bone_specs:
    b = prop_data.edit_bones.new(name)
    b.head = NOZZLES[i]
    b.tail = NOZZLES[i] + Vector((0, 0, 0.1))                        # bone Y axis = world +Z
    b.use_deform = True
bpy.ops.object.mode_set(mode='OBJECT')

# FX meshes, built at the rest nozzle position and skinned 1:1 to their bone
fx_me = bpy.data.meshes.new('JetpackFX')
bm = bmesh.new()
uv_layer = bm.loops.layers.uv.new('UVMap')
bone_layer = bm.verts.layers.int.new('bone')   # bone index per vertex; vert refs go stale across bmesh ops
vgroups = {}                                                         # vert index -> bone name

def tag(verts, bone):
    for v in verts:
        vgroups[v] = bone

def add_ico(center, r, bone, mat, subdiv, u=0.5):
    # Build in a scratch bmesh: create_icosphere at subdiv > 1 reallocates verts of the target bmesh
    tb = bmesh.new()
    bmesh.ops.create_icosphere(tb, subdivisions=subdiv, radius=r)
    vmap = {tv: bm.verts.new(tv.co + center) for tv in tb.verts}
    for tf in tb.faces:
        f = bm.faces.new([vmap[tv] for tv in tf.verts])
        f.material_index = mat
        f.smooth = True
        for loop in f.loops:
            loop[uv_layer].uv = (u, 0.5)
    tb.free()
    return list(vmap.values())

all_tags = []
for name, i, k in bone_specs:
    vs = add_ico(NOZZLES[i], PUFF_R, name, 0, 2)
    bi = len(all_tags)
    for v in vs:
        v[bone_layer] = bi + 1
    all_tags.append(name)
bm.verts.index_update()
tags = [([v.index for v in bm.verts if v[bone_layer] == bi + 1], name) for bi, name in enumerate(all_tags)]
bm.normal_update()
bm.to_mesh(fx_me)
bm.free()

fx = bpy.data.objects.new('JetpackFX', fx_me)
scene.collection.objects.link(fx)
fx.parent = prop
for idx, name in tags:
    fx.vertex_groups.new(name=name).add(idx, 1.0, 'REPLACE')
fx.modifiers.new('Armature', 'ARMATURE').object = prop

# Material: smoke
smoke = bpy.data.materials.new('Jetpack_Smoke_MAT')
smoke.use_nodes = True
sb = next(n for n in smoke.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
sb.inputs['Base Color'].default_value = (0.80, 0.79, 0.78, 1.0)
sb.inputs['Roughness'].default_value = 1.0
smoke.diffuse_color = (0.8, 0.79, 0.78, 1.0)
fx_me.materials.append(smoke)

# ------------------------------------------------------------------ prop clip (baked per frame)
act_prop = new_action(prop, 'Jetpack_Prop', 'Prop_Animation')
rest_rot = {b.name: b.matrix_local.to_3x3() for b in prop_data.bones}

def h(n, k):
    """Deterministic pseudo-random in [0,1) per (bone, index)."""
    return (math.sin(n * 12.9898 + k * 78.233) * 43758.5453) % 1.0

def place(pb, pos, scale):
    """World position + per-axis scale for a parentless prop bone, tilted with the pack."""
    R = (FLIGHT.to_3x3().normalized() @ rest_rot[pb.name]).to_4x4()
    pb.matrix = Matrix.Translation(pos) @ R @ Matrix.Diagonal(Vector((*scale, 1.0)))

for frame in range(FIRST, LAST + 1):
    scene.frame_set(frame)                                            # evaluates the avatar clip
    nz = [FLIGHT @ nozzle_world(0), FLIGHT @ nozzle_world(1)]
    ph = (frame - FIRST) / LOOP                                       # 0..1 over the loop
    for pb in prop.pose.bones:
        name = pb.name
        side = 0 if '_R' in name else 1
        c = nz[side]
        sid = 1 + side
        k = int(name.rsplit('_', 1)[1])
        t = (2 * ph + k / N_PUFF + 0.15 * h(sid + 11, k)) % 1.0                  # 2 waves per loop
        ang = 2 * math.pi * (k / N_PUFF + 0.3 * h(sid + 13, k)) + 1.3 * t
        z = PUFF_TOP + (PUFF_LOW - PUFF_TOP) * t ** 1.5                     # linger near the exit, then sink
        rho = 0.005 + 0.085 * max(0.0, -z) / -PUFF_LOW                       # spread only once out of the bell
        pos = c + Vector((math.cos(ang) * rho, math.sin(ang) * rho + 0.03 * t, z))
        s = (math.sin(math.pi * t) ** 0.5) * (0.6 + 0.7 * t) * (0.8 + 0.4 * h(sid + 17, k))
        if z > 0:
            s = min(s, (BELL_R - BELL_TAPER * z - rho) / PUFF_R)
        place(pb, pos, (s, s, s))
    vl.update()
    for pb in prop.pose.bones:
        pb.keyframe_insert('location', frame=frame)
        pb.keyframe_insert('rotation_quaternion', frame=frame)
        pb.keyframe_insert('scale', frame=frame)

scene.frame_start, scene.frame_end = FIRST, LAST

# ------------------------------------------------------------------ preview renders
def render_preview():
    shots = os.path.join(OUT_DIR, 'emote_shots' + SUFFIX)
    os.makedirs(shots, exist_ok=True)
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.render.resolution_x = scene.render.resolution_y = 400
    scene.render.film_transparent = False
    for o in bpy.data.objects:
        if o.type == 'MESH' and (o.name.startswith('WGT') or o.name in ('Animation_Area_Reference', 'Root_Animation_Area',
                                                                          'Ground_Reference', 'Knee') or o.name.startswith('ShapeA')):
            o.hide_render = True
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
    scene.collection.objects.link(cam); scene.camera = cam
    views = {'back34': ((1.9, 2.6, 1.5), (0, 0.1, 0.85)), 'side': ((3.0, 0.3, 1.2), (0, 0.1, 0.9))}
    out = []
    for v, (loc, tgt) in views.items():
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        for f in (1, 9, 17, 25):
            scene.frame_set(f)
            p = os.path.join(shots, '%s_%02d.png' % (v, f))
            scene.render.filepath = p
            bpy.ops.render.render(write_still=True)
            out.append(p)
    bpy.data.objects.remove(cam, do_unlink=True)
    print('SHOTS', out)

render_preview()
if STAGE == 'pose':
    sys.exit(0)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, 'jetpack_emote%s.blend' % SUFFIX))

# ------------------------------------------------------------------ export
# Push each clip into an NLA track named after the clip: NLA_TRACKS export keeps them as two glTF animations
for obj, act in ((arm, act_avatar), (prop, act_prop)):
    ad = obj.animation_data
    track = ad.nla_tracks.new()
    track.name = act.name
    strip = track.strips.new(act.name, FIRST, act)
    strip.action_slot = act.slots[0]
    ad.action = None

if bpy.data.actions.get('Starting_Pose'):
    bpy.data.actions.remove(bpy.data.actions['Starting_Pose'])
for o in list(bpy.data.objects):
    if o not in (arm, prop, fx):
        bpy.data.objects.remove(o, do_unlink=True)

for o in scene.objects:
    o.select_set(True)
vl.objects.active = arm
path = os.path.join(OUT_DIR, 'jetpack_thrust%s_emote.glb' % SUFFIX)
bpy.ops.export_scene.gltf(
    filepath=path,
    export_format='GLB',
    use_selection=True,
    export_def_bones=True,
    export_force_sampling=True,
    export_frame_step=1,
    export_animation_mode='NLA_TRACKS',
    export_animations=True,
    export_anim_slide_to_zero=True,
    export_skins=True,
    export_materials='EXPORT',
    export_cameras=False,
    export_lights=False,
    export_yup=True,
    export_apply=False,
)
print('EXPORTED', path, os.path.getsize(path))
