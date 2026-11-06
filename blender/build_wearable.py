"""Build the jetpack track-suit upper_body wearable for one body shape.

Run headless (one body shape per run):
  Blender --background <dcl-blender-toolkit>/assets/AvatarShape_B.blend --python build_wearable.py -- male   <out_dir>
  Blender --background <dcl-blender-toolkit>/assets/AvatarShape_A.blend --python build_wearable.py -- female <out_dir>

AvatarShape_A.blend holds the female base mesh, AvatarShape_B.blend the male one.

The suit reuses the base upper-body mesh (already skinned to the 62 avatar bones), re-unwrapped and
painted with a texture computed from each texel's rest-pose 3D position. The retro twin-rocket pack
is built from revolved profiles and weighted 100% to Avatar_Spine2 so it stays rigid on the back. A
mount shaped to the back joins the housing to the suit.
"""
import bpy, bmesh, math, os, sys, json
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index('--') + 1:]
SHAPE, OUT_DIR = argv[0], argv[1]
os.makedirs(OUT_DIR, exist_ok=True)

TEX_SUIT = 1024
TEX_PACK = 1024

# --- palette (linear-ish sRGB values written straight into the PNG) -------------------------------
def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])

WHITE = hexc('F4F2EE')
ORANGE = hexc('FF6A1F')
RED_ORANGE = hexc('E8402A')
PEACH = hexc('FFB36B')
CHAR = hexc('2A2730')
METAL = hexc('B9BCC4')
DARK = hexc('141216')

arm_obj = bpy.data.objects['Armature']
body = next(o for o in bpy.data.objects if o.type == 'MESH' and 'uBody' in o.name)

# Delete every other mesh (head, hands, legs, feet, facial masks)
for o in list(bpy.data.objects):
    if o.type == 'MESH' and o != body:
        bpy.data.objects.remove(o, do_unlink=True)

# --- measure the body ---------------------------------------------------------------------------
mw = body.matrix_world
ws = [mw @ v.co for v in body.data.vertices]
BOTTOM = min(w.z for w in ws)
TOP = max(w.z for w in ws if abs(w.x) < 0.15)
BACK_Y = max(w.y for w in ws if abs(w.x) < 0.12 and 1.0 < w.z < 1.42)
ARM_Z = 1.466                      # T-pose arm axis height (Avatar_LeftArm head)
print('BODY', SHAPE, 'bottom', round(BOTTOM, 3), 'top', round(TOP, 3), 'backY', round(BACK_Y, 3))

# --- suit: inflate slightly (puffier sleeves), mark faces as part 0 -------------------------------
bpy.context.view_layer.objects.active = body
for o in bpy.context.selected_objects:
    o.select_set(False)
body.select_set(True)

bm = bmesh.new()
bm.from_mesh(body.data)
bm.normal_update()
inv = mw.inverted()
for v in bm.verts:
    w = mw @ v.co
    push = 0.009 if abs(w.x) > 0.2 else 0.004
    wn = (mw.to_3x3() @ v.normal).normalized()
    v.co = inv @ (w + wn * push)
part_layer = bm.faces.layers.int.new('part')
for f in bm.faces:
    f[part_layer] = 0
    f.material_index = 0
bm.to_mesh(body.data)
bm.free()

# --- jetpack geometry (built in world space, then joined into the body) ---------------------------
# Front face of the pack housing. The furthest-back point of the suit under the housing and tanks is
# 0.1252 m on both bodies, so 0.129 leaves 4 mm. It is the same on both so one thrust emote's flames
# (placed from info_male.json) line up with the nozzles on either body. BACK_Y + 0.012 left 2-10 cm gaps:
# BACK_Y is the furthest-back point of a wider area (up by the shoulders), not of what the pack covers.
PACK_Y0 = 0.129
TANK_R = 0.062
TANK_X = 0.095
TANK_Y = PACK_Y0 + 0.058
SEG = 12

# (radius, z) from tip to nozzle; the last points turn back inward to form a hollow bell
TANK_PROFILE = [(0.0, 1.575), (0.022, 1.555), (0.040, 1.525), (0.054, 1.485), (TANK_R, 1.435),
                (TANK_R, 1.055), (0.055, 1.022), (0.038, 0.997), (0.030, 0.987),
                (0.040, 0.958), (0.049, 0.930), (0.041, 0.930), (0.026, 0.955), (0.0, 0.962)]

P_TANK, P_HOUSING, P_FIN, P_PLATE = 1, 2, 3, 4

def add_revolve(bm, part_layer, profile, cx, cy, part):
    rings = []
    for r, z in profile:
        if r == 0.0:
            rings.append([bm.verts.new((cx, cy, z))])
        else:
            rings.append([bm.verts.new((cx + r * math.cos(2 * math.pi * i / SEG),
                                        cy + r * math.sin(2 * math.pi * i / SEG), z)) for i in range(SEG)])
    for a, b in zip(rings, rings[1:]):
        for i in range(SEG):
            j = (i + 1) % SEG
            if len(a) == 1:
                f = bm.faces.new((a[0], b[j], b[i]))
            elif len(b) == 1:
                f = bm.faces.new((a[i], a[j], b[0]))
            else:
                f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f[part_layer] = part
            f.material_index = 1
            f.smooth = True

def add_box(bm, part_layer, x0, x1, y0, y1, z0, z1, part):
    v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for q in quads:
        f = bm.faces.new([v[i] for i in q])
        f[part_layer] = part
        f.material_index = 1
        f.smooth = False

def add_fin(bm, part_layer, cx, cy, dirx, diry, part):
    """Swept retro fin as a thin prism radiating from the tank wall in direction (dirx, diry)."""
    t = 0.006
    px, py = -diry, dirx                 # perpendicular, for thickness
    prof = [(TANK_R - 0.004, 1.17), (TANK_R + 0.055, 1.045), (TANK_R + 0.058, 0.985), (TANK_R - 0.004, 1.03)]
    side = []
    for s in (-t, t):
        side.append([bm.verts.new((cx + dirx * d + px * s, cy + diry * d + py * s, z)) for d, z in prof])
    a, b = side
    faces = [list(reversed(a)), list(b)] + [[a[i], a[(i + 1) % 4], b[(i + 1) % 4], b[i]] for i in range(4)]
    for fv in faces:
        f = bm.faces.new(fv)
        f[part_layer] = part
        f.material_index = 1
        f.smooth = False

pack_me = bpy.data.meshes.new('JetpackPack')
bm = bmesh.new()
pl = bm.faces.layers.int.new('part')
for sx in (-1, 1):
    cx = sx * TANK_X
    add_revolve(bm, pl, TANK_PROFILE, cx, TANK_Y, P_TANK)
    add_fin(bm, pl, cx, TANK_Y, sx * 1.0, 0.0, P_FIN)                       # outward fin
    add_fin(bm, pl, cx, TANK_Y, sx * 0.5, 0.866, P_FIN)                     # rear fin
add_box(bm, pl, -0.055, 0.055, PACK_Y0, PACK_Y0 + 0.085, 1.07, 1.40, P_HOUSING)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(pack_me)
bm.free()
pack_obj = bpy.data.objects.new('JetpackPack', pack_me)
bpy.context.scene.collection.objects.link(pack_obj)
vg = pack_obj.vertex_groups.new(name='Avatar_Spine2')
vg.add(list(range(len(pack_me.vertices))), 1.0, 'REPLACE')

# --- mount between the pack and the back ---------------------------------------------------------
# The pack is rigid and flat-fronted and the back curves away from it, so from the side it looked
# like it floated off the suit. A block behind the housing gives it a visible attachment point (a
# full-width plate read as too heavy). Its front follows the suit's back (ray-cast on the inflated
# mesh, 5 mm inside it) and copies the skin weights of the nearest suit vertex, so it stays on the
# back when the spine bends. Its back face sits inside the housing, weighted to Avatar_Spine2.
suit_w = [mw @ v.co for v in body.data.vertices]
suit_bvh = BVHTree.FromPolygons(suit_w, [list(p.vertices) for p in body.data.polygons])
suit_kd = KDTree(len(suit_w))
for i, w in enumerate(suit_w):
    suit_kd.insert(w, i)
suit_kd.balance()

def back_surface_y(x, z):
    hit = suit_bvh.ray_cast(Vector((x, 1.0, z)), Vector((0, -1, 0)))[0]
    return hit.y if hit else PACK_Y0

need = max(back_surface_y(x / 100, z / 100) for x in range(-5, 6) for z in range(107, 141))
print('PACK_CLEARANCE housing %.1f mm' % ((PACK_Y0 - need) * 1000))
PLATE_X = [-0.045, 0.0, 0.045]
PLATE_Z = [1.16, 1.24, 1.32]
PLATE_BACK_Y = PACK_Y0 + 0.012
nx, nz = len(PLATE_X), len(PLATE_Z)
ring = ([(0, j) for j in range(nx)] + [(i, nx - 1) for i in range(1, nz)] +
        [(nz - 1, j) for j in range(nx - 2, -1, -1)] + [(i, 0) for i in range(nz - 2, 0, -1)])
plate_me = bpy.data.meshes.new('JetpackPlate')
bm = bmesh.new()
pl = bm.faces.layers.int.new('part')
front = {(i, j): bm.verts.new((x, back_surface_y(x, z) - 0.005, z)) for i, z in enumerate(PLATE_Z) for j, x in enumerate(PLATE_X)}
back = {ij: bm.verts.new((PLATE_X[ij[1]], PLATE_BACK_Y, PLATE_Z[ij[0]])) for ij in ring}
faces = [[front[i, j], front[i, j + 1], front[i + 1, j + 1], front[i + 1, j]] for i in range(nz - 1) for j in range(nx - 1)]
faces += [[front[a], front[b], back[b], back[a]] for a, b in zip(ring, ring[1:] + ring[:1])]
faces.append([back[ij] for ij in reversed(ring)])
for fv in faces:
    f = bm.faces.new(fv)
    f[pl] = P_PLATE
    f.material_index = 1
    f.smooth = False
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.verts.index_update()
front_idx = {v.index: v.co.copy() for v in front.values()}
back_idx = [v.index for v in back.values()]
bm.to_mesh(plate_me)
bm.free()
plate_obj = bpy.data.objects.new('JetpackPlate', plate_me)
bpy.context.scene.collection.objects.link(plate_obj)
groups = {}
for vi, co in front_idx.items():
    _, si, _ = suit_kd.find(co)
    for g in body.data.vertices[si].groups:
        name = body.vertex_groups[g.group].name
        groups.setdefault(name, plate_obj.vertex_groups.new(name=name) if name not in plate_obj.vertex_groups else plate_obj.vertex_groups[name])
        groups[name].add([vi], g.weight, 'REPLACE')
spine2 = plate_obj.vertex_groups.get('Avatar_Spine2') or plate_obj.vertex_groups.new(name='Avatar_Spine2')
spine2.add(back_idx, 1.0, 'REPLACE')

# The base mesh is parented to the armature with an inverse; give the pack and plate the same parenting
for o in (pack_obj, plate_obj):
    o.parent = arm_obj
    o.matrix_parent_inverse = arm_obj.matrix_world.inverted()
    o.matrix_world = o.matrix_world  # keep world placement
    mod = o.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm_obj

# Join the pack and plate into the body object so the wearable is a single skinned mesh
for o in bpy.context.selected_objects:
    o.select_set(False)
pack_obj.select_set(True)
plate_obj.select_set(True)
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = 'Jetpack_uBody'
body.data.name = 'Jetpack_uBody'

# --- materials ----------------------------------------------------------------------------------
def make_mat(name, img):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Linear'
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.6
    bsdf.inputs['Metallic'].default_value = 0.0
    return m

img_suit = bpy.data.images.new('Jetpack_Suit_TX', TEX_SUIT, TEX_SUIT, alpha=False)
img_pack = bpy.data.images.new('Jetpack_Pack_TX', TEX_PACK, TEX_PACK, alpha=False)
body.data.materials.clear()
body.data.materials.append(make_mat('Jetpack_Suit_MAT', img_suit))
body.data.materials.append(make_mat('Jetpack_Pack_MAT', img_pack))
# join() drops the pack's material indices (it had no material slots), so restore them from 'part'
for poly, attr in zip(body.data.polygons, body.data.attributes['part'].data):
    poly.material_index = 1 if attr.value > 0 else 0

# --- UVs: hand-made cylindrical layout ------------------------------------------------------------
# smart_project left 64% of the suit texture empty and cut islands at arbitrary angles, so straight
# stripes crossed the texel grid diagonally and looked stair-stepped in-world. Here the torso, sleeves
# and tanks are unrolled as cylinders, so stripes and bands run along texel rows/columns, and mirrored
# parts (both sleeves, both tanks, all four fins) share one island to double their texel density.
me = body.data
for l in list(me.uv_layers):
    me.uv_layers.remove(l)
uvl = me.uv_layers.new(name='UVMap').data
SLEEVE_R = 0.075                   # reference radius for unrolling the sleeves
TORSO_A, TORSO_B, TORSO_YC = 0.175, 0.14, -0.015   # torso cross-section ellipse

_t = np.linspace(-math.pi, math.pi, 1441)
_ds = np.hypot(TORSO_A * np.cos(_t), TORSO_B * np.sin(_t))
_s = np.concatenate([[0.0], np.cumsum((_ds[1:] + _ds[:-1]) / 2 * np.diff(_t))])
_s -= np.interp(0.0, _t, _s)       # arc length is 0 at the front centre
TORSO_C = _s[-1] - _s[0]

def unwrap_angle(angles):
    """Angles of one face's loops, with the ±pi seam resolved so the face doesn't span the atlas."""
    a = np.array(angles)
    return np.where(a < 0, a + 2 * math.pi, a) if a.max() - a.min() > math.pi else a

prof_len = np.concatenate([[0.0], np.cumsum([math.hypot(r1 - r0, z1 - z0) for (r0, z0), (r1, z1)
                                             in zip(TANK_PROFILE, TANK_PROFILE[1:])])])

def tank_v(r, z):
    i = min(range(len(TANK_PROFILE)), key=lambda k: abs(TANK_PROFILE[k][0] - r) + abs(TANK_PROFILE[k][1] - z))
    return prof_len[i]

R3 = mw.to_3x3()
wco = [mw @ v.co for v in me.vertices]
islands = {}                       # name -> [(loop_index, u, v)] in metres; scale multiplier below
ISLAND_SCALE = {'housing_front': 0.3, 'suit_bottom': 0.6, 'plate_front': 0.1, 'plate_back': 0.3}
part_vals = [a.value for a in me.attributes['part'].data]
for poly in me.polygons:
    loops = list(poly.loop_indices)
    P = [wco[me.loops[l].vertex_index] for l in loops]
    c = mw @ poly.center
    n = (R3 @ poly.normal).normalized()
    part = part_vals[poly.index]
    if part == 0 and abs(c.x) > 0.195:                      # sleeves: unroll around the arm axis
        ph = unwrap_angle([math.atan2(p.y, p.z - ARM_Z) for p in P])
        uv = [(a * SLEEVE_R, abs(p.x)) for a, p in zip(ph, P)]
        name = 'sleeve'
    elif part == 0 and (n.z > 0.6 or (n.z < -0.6 and (abs(c.x) > 0.12 or                 # shoulder tops,
                                                    math.hypot(c.x / TORSO_A, (c.y - TORSO_YC) / TORSO_B) < 0.75))):
        # armpits and inward-turned hems (too close to the torso axis to unroll): planar
        uv = [(p.x, p.y) for p in P]
        name = 'suit_top' if n.z > 0 else 'suit_bottom'
    elif part == 0:                                         # torso: unroll around the ellipse
        t = [math.atan2(p.x / TORSO_A, -(p.y - TORSO_YC) / TORSO_B) for p in P]
        t = unwrap_angle(t) if min(abs(a) for a in t) > math.pi / 2 else np.array(t)   # only back faces cross the seam
        uv = [(float(np.interp(a, _t, _s)) if a <= math.pi else float(np.interp(a - 2 * math.pi, _t, _s)) + TORSO_C, p.z)
              for a, p in zip(t, P)]
        name = 'torso'
    elif part == P_TANK:                                    # both tanks share one island
        cx = math.copysign(TANK_X, c.x)
        ang = [math.atan2(p.x - cx, p.y - TANK_Y) for p in P]           # 0 = facing back, seam toward the body
        rs = [math.hypot(p.x - cx, p.y - TANK_Y) for p in P]
        ring = [a for a, r in zip(ang, rs) if r > 1e-5]
        ring = list(unwrap_angle(ring)) if ring else [0.0]
        it = iter(ring)
        ang = [next(it) if r > 1e-5 else None for r in rs]
        mid = sum(ring) / len(ring)
        uv = [((a if a is not None else mid) * TANK_R, -tank_v(r, p.z)) for a, r, p in zip(ang, rs, P)]
        name = 'tank'
    elif part == P_FIN:                                     # all four fins share one island
        cx = math.copysign(TANK_X, c.x)
        uv = []
        for p in P:
            dx, dy = p.x - cx, p.y - TANK_Y
            d = math.hypot(dx, dy)
            uv.append((d, p.z))
        name = 'fin'
    elif part == P_PLATE:                                   # mounting plate: planar per side, both sides share
        if abs(n.y) > 0.7:
            uv, name = [(p.x, p.z) for p in P], 'plate_back' if n.y > 0 else 'plate_front'
        elif abs(n.x) > 0.7:
            uv, name = [(p.y, p.z) for p in P], 'plate_side'
        else:
            uv, name = [(p.x, p.y) for p in P], 'plate_top' if n.z > 0 else 'plate_bottom'
    else:                                                   # housing box: one island per face
        if abs(n.y) > 0.7:
            uv, name = [(p.x, p.z) for p in P], 'housing_back' if n.y > 0 else 'housing_front'
        elif abs(n.x) > 0.7:
            uv, name = [(p.y, p.z) for p in P], 'housing_side_%s' % ('r' if n.x > 0 else 'l')
        else:
            uv, name = [(p.x, p.y) for p in P], 'housing_top' if n.z > 0 else 'housing_bottom'
    islands.setdefault((poly.material_index, name), []).extend((l, u, v) for l, (u, v) in zip(loops, uv))

def pack_islands(items, margin_px=6, size=1024):
    """Shelf-pack islands into the unit square at the largest uniform scale that fits. The three biggest
    islands may be turned 90 degrees (u/v swapped: stripes stay on the texel grid); the best combination wins."""
    m = margin_px / size
    base = []
    for key, data in items:
        us = [d[1] for d in data]; vs = [d[2] for d in data]
        base.append((key, data, min(us), min(vs), max(us) - min(us), max(vs) - min(vs), ISLAND_SCALE.get(key[1], 1.0)))
    base.sort(key=lambda b: -b[4] * b[5] * b[6] ** 2)

    def place(boxes, k):
        x = y = m
        shelf_h = 0
        out = []
        for key, data, u0, v0, w, h, s, rot in sorted(boxes, key=lambda b: -(b[4] if b[7] else b[5]) * b[6]):
            W, H = (h, w) if rot else (w, h)
            W, H = W * k * s, H * k * s
            if x + W + m > 1:
                x, y = m, y + shelf_h + m
                shelf_h = 0
            if y + H + m > 1 or W + 2 * m > 1:
                return None
            out.append((data, u0, v0, x, y, k * s, rot))
            x += W + m
            shelf_h = max(shelf_h, H)
        return out

    best = (0, None)
    for combo in range(8):
        boxes = [b + (bool(combo >> i & 1) if i < 3 else False,) for i, b in enumerate(base)]
        lo, hi = 0.1, 10.0
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if place(boxes, mid) else (lo, mid)
        if lo > best[0]:
            best = (lo, boxes)
    k, boxes = best
    for data, u0, v0, x, y, ks, rot in place(boxes, k):
        for l, u, v in data:
            du, dv = (u - u0) * ks, (v - v0) * ks
            uvl[l].uv = (x + dv, y + du) if rot else (x + du, y + dv)
    return k

for mat_index, size in ((0, TEX_SUIT), (1, TEX_PACK)):
    k = pack_islands([(key, d) for key, d in islands.items() if key[0] == mat_index], size=size)
    print('UV_DENSITY mat', mat_index, 'texels/m %.0f' % (k * size))

# --- paint textures (see texturing.py), then save PNG copies for reference ------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texturing
G = dict(ARM_Z=ARM_Z, TOP=TOP, BOTTOM=BOTTOM, TANK_X=TANK_X, TANK_Y=TANK_Y, TANK_R=TANK_R)
texturing.build_textures(body, mw, TEX_SUIT, img_suit, img_pack, G)
for img in (img_suit, img_pack):
    img.filepath_raw = os.path.join(OUT_DIR, '%s_%s.png' % (img.name, SHAPE))
    img.file_format = 'PNG'
    img.save()
    img.pack()

# Drop the helper attribute so it is not exported
me.attributes.remove(me.attributes['part'])

# --- report + export ----------------------------------------------------------------------------
tris = sum(len(p.vertices) - 2 for p in me.polygons)
nozzles = [(sx * TANK_X, TANK_Y, 0.930) for sx in (-1, 1)]
info = dict(shape=SHAPE, tris=tris, back_y=BACK_Y, pack_y0=PACK_Y0, tank_x=TANK_X, tank_y=TANK_Y, nozzles=nozzles)
print('WEARABLE_INFO', json.dumps(info))
with open(os.path.join(OUT_DIR, 'info_%s.json' % SHAPE), 'w') as f:
    json.dump(info, f)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, 'jetpack_suit_%s.blend' % SHAPE))

for o in bpy.context.scene.objects:
    o.select_set(o in (arm_obj, body))
bpy.ops.export_scene.gltf(
    filepath=os.path.join(OUT_DIR, 'jetpack_suit_%s.glb' % SHAPE),
    export_format='GLB',
    use_selection=True,
    export_skins=True,
    export_animations=False,
    export_morph=False,
    export_materials='EXPORT',
    export_image_format='JPEG',
    export_jpeg_quality=88,
    export_cameras=False,
    export_lights=False,
    export_yup=True,
    export_apply=False,
)
print('EXPORTED', SHAPE)
