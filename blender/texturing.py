"""Procedural, film-look textures for the jetpack suit and pack (imported by build_wearable.py).

Every texel is supersampled (SS x SS) from its rest-pose 3D position, so region edges are anti-aliased
and details (stitching, rivets, ribbing) are drawn at their real-world size. Colour logic is vectorized
numpy over all samples. After painting, ambient occlusion is baked with Cycles and multiplied in, then a
warm, slightly faded "vintage film stock" grade is applied.
"""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

SS = 3  # supersamples per axis

# --- palette: warm, slightly desaturated, like painted props on period film stock -----------------
def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)

CREAM = hexc('EDE5D3')
ORANGE = hexc('E2601F')
RED = hexc('B5371F')
CHAR = hexc('2F2B2C')
WEB = hexc('3A3533')
METAL = hexc('A9A79F')
CHROME = hexc('D9D6CC')
BRONZE = hexc('8C6A45')
HEAT_BLUE = hexc('4B4A63')
SOOT = hexc('1C1A1A')
GAUGE_FACE = hexc('F1E9D2')
NAVY = hexc('2B3550')
REFLECT = hexc('C9CCCB')
SATIN = hexc('CFCBC2')     # warm satin aluminium for the tank bodies
CAUTION = hexc('E3AE2F')


# --- stencilled text (masks rendered by make_stencils.py) ---------------------------------------
STENCIL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stencils')
_stencils = {}

def stencil(name, s, t):
    """Bilinear lookup of a text mask; s runs left to right, t bottom to top, both in [0, 1]."""
    if name not in _stencils:
        img = bpy.data.images.load(os.path.join(STENCIL_DIR, name + '.png'))
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        _stencils[name] = px.reshape(h, w, 4)[..., 0]
        bpy.data.images.remove(img)
    a = _stencils[name]
    h, w = a.shape
    inside = (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
    x = np.clip(s, 0, 1) * (w - 1)
    y = np.clip(t, 0, 1) * (h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    v = (a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x1] * fx * (1 - fy)
         + a[y1, x0] * (1 - fx) * fy + a[y1, x1] * fx * fy)
    return v * inside


def quilt(a, b, spacing):
    """Diamond quilting on surface coordinates (a, b): 0 on the stitch lines, 1 at the puffed centres."""
    d1 = np.abs(((a + b) / spacing) % 1.0 - 0.5) * 2
    d2 = np.abs(((a - b) / spacing) % 1.0 - 0.5) * 2
    return np.minimum(1 - d1, 1 - d2)


# --- noise ------------------------------------------------------------------------------------------
def _hash(ix, iy, iz):
    v = np.sin(ix * 127.1 + iy * 311.7 + iz * 74.7) * 43758.5453
    return v - np.floor(v)

def vnoise(P, scale):
    """Smooth 3D value noise in [0, 1]; `scale` is the feature size in metres (array per axis allowed)."""
    q = P / scale
    i = np.floor(q)
    f = q - i
    u = f * f * (3 - 2 * f)
    ix, iy, iz = i[:, 0], i[:, 1], i[:, 2]
    out = 0
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1 - u[:, 2]
                out = out + wx * wy * wz * _hash(ix + dx, iy + dy, iz + dz)
    return out

def fbm(P, scale, octaves=3):
    total, amp, norm = 0, 1.0, 0
    for o in range(octaves):
        total = total + amp * vnoise(P + o * 17.3, scale / (2 ** o))
        norm += amp
        amp *= 0.5
    return total / norm

def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

def mix(a, b, t):
    t = np.asarray(t, dtype=np.float32)
    if t.ndim == 1:
        t = t[:, None]
    return a * (1 - t) + b * t

def paint_regions(n, rules, default):
    """First matching rule wins. rules: [(mask, colour, region_id)]. Returns (colours, ids)."""
    col = np.tile(default[0], (n, 1)).astype(np.float32)
    ids = np.full(n, default[1], dtype=np.int32)
    for mask, c, rid in reversed(rules):
        c = np.asarray(c, dtype=np.float32)
        col = np.where(mask[:, None], c if c.ndim == 2 else c[None, :], col)
        ids = np.where(mask, rid, ids)
    return col, ids


# --- rasterize mesh triangles into texel samples --------------------------------------------------
def rasterize(me, mw, mat_index, size):
    """Returns per-sample (pixel_index, position, normal, part) for every triangle of `mat_index`."""
    me.calc_loop_triangles()
    uv = me.uv_layers['UVMap'].data
    part_attr = me.attributes['part'].data
    R = mw.to_3x3()
    co = np.array([(mw @ v.co)[:] for v in me.vertices], dtype=np.float64)
    offs = (np.arange(SS) + 0.5) / SS
    pix, pos, nrm, prt = [], [], [], []
    for tri in me.loop_triangles:
        if tri.material_index != mat_index:
            continue
        uvs = np.array([uv[l].uv[:] for l in tri.loops]) * size
        ps = co[list(tri.vertices)]
        ns = np.array([(R @ Vector(n)).normalized()[:] for n in tri.split_normals])
        x0, y0 = np.floor(uvs.min(0)).astype(int) - 1
        x1, y1 = np.ceil(uvs.max(0)).astype(int) + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        OX, OY = np.meshgrid(offs, offs, indexing='ij')
        sx = (gx[..., None, None] + OX).ravel()
        sy = (gy[..., None, None] + OY).ravel()
        px = np.repeat((gy * size + gx).ravel(), SS * SS)
        (ax, ay), (bx, by), (cx, cy) = uvs
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        w0 = ((by - cy) * (sx - cx) + (cx - bx) * (sy - cy)) / den
        w1 = ((cy - ay) * (sx - cx) + (ax - cx) * (sy - cy)) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not inside.any():
            continue
        W = np.stack([w0[inside], w1[inside], w2[inside]], 1)
        pix.append(px[inside])
        pos.append(W @ ps)
        n = W @ ns
        nrm.append(n / np.linalg.norm(n, axis=1, keepdims=True))
        prt.append(np.full(inside.sum(), part_attr[tri.polygon_index].value, dtype=np.int32))
    return (np.concatenate(pix), np.concatenate(pos).astype(np.float32),
            np.concatenate(nrm).astype(np.float32), np.concatenate(prt))


def resolve(size, pix, col, ids, pos):
    """Average samples per texel; also keep one id and position per texel for image-space passes."""
    n = size * size
    acc = np.zeros((n, 3), dtype=np.float32)
    cnt = np.zeros(n, dtype=np.float32)
    np.add.at(acc, pix, col)
    np.add.at(cnt, pix, 1)
    filled = cnt > 0
    acc[filled] /= cnt[filled, None]
    idmap = np.full(n, -1, dtype=np.int32)
    idmap[pix] = ids
    posmap = np.zeros((n, 3), dtype=np.float32)
    posmap[pix] = pos
    return (acc.reshape(size, size, 3), filled.reshape(size, size), idmap.reshape(size, size),
            posmap.reshape(size, size, 3))


def shift(a, dy, dx, fill):
    out = np.full_like(a, fill)
    ys = slice(max(dy, 0), a.shape[0] + min(dy, 0))
    yd = slice(max(-dy, 0), a.shape[0] + min(-dy, 0))
    xs = slice(max(dx, 0), a.shape[1] + min(dx, 0))
    xd = slice(max(-dx, 0), a.shape[1] + min(-dx, 0))
    out[ys, xs] = a[yd, xd]
    return out

def dilate(mask, valid):
    out = mask.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        out |= shift(mask, dy, dx, False)
    return out & valid

def seams_and_stitches(cols, filled, idmap, posmap, size):
    """Sewn look: a soft shadow where fabric panels meet, plus a dashed topstitch a few mm in."""
    edge = np.zeros_like(filled)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nid = shift(idmap, dy, dx, -1)
        edge |= filled & (nid >= 0) & (nid != idmap)
    rings = [edge]
    for _ in range(5):
        rings.append(dilate(rings[-1], filled))
    shade = np.ones((size, size), dtype=np.float32)
    for k, f in enumerate((0.70, 0.80, 0.90, 0.96)):
        band = rings[k] & ~(rings[k - 1] if k else np.zeros_like(edge))
        shade[band] = np.minimum(shade[band], f)
    stitch_band = rings[5] & ~rings[3]
    P = posmap
    dash = ((P[..., 0] * 0.6 + P[..., 1] * 0.3 + P[..., 2]) / 0.004) % 1.0 < 0.55
    stitch = stitch_band & dash
    cols *= shade[..., None]
    cols[stitch] = cols[stitch] * 0.72 + CREAM * 0.18
    return cols


def fill_gutters(cols, filled, iters=40):
    for _ in range(iters):
        empty = ~filled
        if not empty.any():
            break
        acc = np.zeros_like(cols)
        cnt = np.zeros(filled.shape, dtype=np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                sf = shift(filled, dy, dx, False)
                acc += shift(cols, dy, dx, 0.0) * sf[..., None]
                cnt += sf
        grow = empty & (cnt > 0)
        cols[grow] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
    return cols


def film_grade(cols):
    """Warm, slightly faded period-film look: lifted blacks, softened saturation, warm cast."""
    lum = (cols @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]
    cols = lum + (cols - lum) * 0.88
    cols = cols * 0.95 + 0.025
    cols = cols * np.array([1.02, 1.0, 0.95], dtype=np.float32)
    return np.clip(cols, 0, 1)


# --- suit -----------------------------------------------------------------------------------------
def suit_colors(P, N, part, g):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    n = len(x)
    sleeve = ax > 0.195
    phi = np.arctan2(y, z - g['ARM_Z'])
    front = y < 0
    TOP, BOTTOM = g['TOP'], g['BOTTOM']
    strap = (ax > 0.072) & (ax < 0.104) & ~sleeve & (z > BOTTOM + 0.05)
    cross = front & (z > 1.30) & (z < 1.335) & (ax < 0.104) & ~sleeve
    side = 0.142 - 0.015 * (1.40 - z) / 0.35
    pr = np.hypot(x - 0.048, z - 1.372)
    patch = front & (pr < 0.022) & ~sleeve
    arc = phi * 0.075                                           # metres around the sleeve
    mp_u, mp_v = arc + 0.85 * 0.075, 0.29 - ax                 # mission patch, "up" toward the shoulder
    mission = sleeve & (np.hypot(mp_u, mp_v) < 0.029)
    elbow_pad = sleeve & (np.abs(phi - math.pi / 2) < 0.75) & (np.abs(ax - 0.45) < 0.045)
    reflect = sleeve & (ax > 0.585) & (ax < 0.607)
    tape = front & ~sleeve & (x > -0.07) & (x < -0.016) & (np.abs(z - 1.372) < 0.0105)
    PK0, PK1 = BOTTOM + 0.085, BOTTOM + 0.17
    pocket = front & ~sleeve & (ax > 0.018) & (ax < 0.066) & (z > PK0) & (z < PK1)

    rules = [
        (sleeve & (ax > 0.655), CHAR, 1),                       # knit cuff
        (sleeve & (ax > 0.63), CREAM, 2),
        (reflect, REFLECT, 21),                                 # reflective band
        (mission, NAVY, 22),                                    # mission patch
        (elbow_pad, RED, 23),                                   # quilted elbow pad
        (sleeve & (np.abs(phi) > 0.10) & (np.abs(phi) < 0.36), CREAM, 3),   # racing stripes
        (sleeve & (np.abs(phi) <= 0.10), RED, 4),
        (sleeve & (ax > 0.20) & (ax < 0.24), RED, 5),          # shoulder piping
        (sleeve, ORANGE, 6),
        (z > TOP - 0.035, CHAR, 7),                             # knit collar
        (z < BOTTOM + 0.05, CHAR, 8),                           # knit waistband
        (z < BOTTOM + 0.062, ORANGE, 9),
        (front & strap & (z > 1.235) & (z < 1.27), METAL, 10),  # strap adjusters
        (strap, WEB, 11),
        (cross & (ax < 0.028), METAL, 12),                      # buckle
        (cross, WEB, 13),
        (front & (ax < 0.007), CHAR, 14),                       # zipper
        (patch, CREAM, 19),
        (tape, CHAR, 24),                                       # name tape
        (pocket & (z > PK1 - 0.026), ORANGE, 25),               # pocket flap
        (pocket, CREAM * 0.97, 26),
        (z > 1.415, ORANGE, 15),                                # yoke
        (z > 1.40, RED, 16),
        (ax > side + 0.012, ORANGE, 17),                        # side panels
        (ax > side, RED, 18),
    ]
    col, ids = paint_regions(n, rules, (CREAM, 20))

    # knit ribbing on cuffs, collar and waistband
    rib_cuff = 0.5 + 0.5 * np.sin(phi * 70)
    rib_body = 0.5 + 0.5 * np.sin(np.arctan2(y, x) * 180)
    col[ids == 1] *= (0.82 + 0.18 * rib_cuff[ids == 1])[:, None]
    for rid in (7, 8):
        m = ids == rid
        col[m] *= (0.82 + 0.18 * rib_body[m])[:, None]

    # webbing straps: twill weave + darker worn edges (period kept above ~3 texels so it doesn't alias)
    for rid in (11, 13):
        m = ids == rid
        tw = 0.5 + 0.5 * np.sin((z[m] + ax[m]) * 2 * math.pi / 0.004)
        col[m] *= (0.86 + 0.14 * tw)[:, None]
    m = ids == 11
    edge_d = np.minimum(ax[m] - 0.072, 0.104 - ax[m])
    col[m] *= (0.75 + 0.25 * smooth(0.0, 0.004, edge_d))[:, None]

    # metal hardware: brushed, with bevelled edges
    for rid, (x0, x1, z0, z1) in ((10, (0.072, 0.104, 1.235, 1.27)), (12, (0.0, 0.028, 1.30, 1.335))):
        m = ids == rid
        d = np.minimum.reduce([ax[m] - x0 if x0 > 0 else np.full(m.sum(), 1.0), x1 - ax[m], z[m] - z0, z1 - z[m]])
        bevel = smooth(0.0, 0.004, d)
        brushed = 0.92 + 0.08 * vnoise(P[m] * np.array([1, 1, 1], dtype=np.float32), np.array([0.05, 0.05, 0.0015]))
        col[m] = mix(CHAR * 1.4, CHROME, 0.35 + 0.65 * bevel) * brushed[:, None]

    # zipper: metal teeth on a dark tape
    m = (ids == 14) & (ax < 0.0032) & (((z / 0.0045) % 1.0) < 0.6)
    col[m] = CHROME * 0.85

    # embroidered chest patch: red-orange ring, cream field, orange chevron
    m = ids == 19
    if m.any():
        r = pr[m]
        xx, zz = x[m] - 0.048, z[m] - 1.372
        ring = r > 0.0165
        chev_v = zz + 0.85 * np.abs(xx)
        chevron = (chev_v > -0.002) & (chev_v < 0.005) & (np.abs(xx) < 0.011)
        pc = np.tile(CREAM, (m.sum(), 1))
        pc[ring] = RED
        pc[chevron & ~ring] = ORANGE
        thread = 0.9 + 0.1 * (0.5 + 0.5 * np.sin((xx + zz) * 2 * math.pi / 0.0012))
        pc *= thread[:, None]
        pc[(r > 0.0205)] *= 0.7  # merrowed edge
        col[m] = pc

    # mission patch: navy field, orbit ring, cream rocket with red fins and an orange flame, merrowed edge
    m = ids == 22
    if m.any():
        pu, pv = mp_u[m], mp_v[m]
        r = np.hypot(pu, pv)
        pc = np.tile(NAVY, (m.sum(), 1))
        ca, sa = math.cos(0.45), math.sin(0.45)
        eu, ev = pu * ca + pv * sa, -pu * sa + pv * ca
        orbit = np.abs(np.hypot(eu / 0.019, ev / 0.0075) - 1) < 0.11
        pc[orbit] = mix(pc[orbit], CREAM, 0.8)
        half_w = np.where(pv > 0.006, 0.0042 * np.clip((0.015 - pv) / 0.009, 0, 1), 0.0042)
        body = (np.abs(pu) < half_w) & (pv > -0.009) & (pv < 0.015)
        fins = (pv > -0.011) & (pv < -0.002) & (np.abs(pu) < 0.0042 + (-0.002 - pv) * 0.55) & ~body
        flame = (pv < -0.009) & (pv > -0.02) & (np.abs(pu) < 0.003 * (pv + 0.02) / 0.011)
        pc[flame] = ORANGE
        pc[fins] = RED
        pc[body] = CREAM
        pc[(np.abs(pu) < 0.0016) & (np.abs(pv - 0.004) < 0.0016)] = NAVY * 1.3     # porthole
        for su, sv in ((-0.014, 0.012), (0.015, 0.009), (0.011, -0.014), (-0.016, -0.006), (0.004, 0.021)):
            pc[np.hypot(pu - su, pv - sv) < 0.0017] = CREAM
        pc[r > 0.0245] = ORANGE * 0.85
        pc *= (0.9 + 0.1 * (0.5 + 0.5 * np.sin((pu + pv) * 2 * math.pi / 0.004)))[:, None]
        col[m] = pc

    # quilted elbow pads and shoulder yoke: stitched diamonds, puffed between the stitches
    m = ids == 23
    q = quilt(arc[m], ax[m], 0.022)
    col[m] *= (0.80 + 0.22 * smooth(0.0, 0.5, q))[:, None]
    m = ids == 15
    q = quilt(x[m], z[m] - 0.6 * y[m], 0.03)
    col[m] *= (0.86 + 0.16 * smooth(0.0, 0.5, q))[:, None]

    # reflective tape: bright, slightly glassy, with a faint bead texture
    m = ids == 21
    col[m] *= (0.95 + 0.08 * vnoise(P[m], 0.004))[:, None]

    # name tape: embroidered "PILOT" in cream
    m = ids == 24
    txt = stencil('pilot', (x[m] + 0.066) / 0.046, (z[m] - 1.3635) / 0.017)
    col[m] = mix(col[m], CREAM, txt * 0.9)

    # pocket flaps: snap button
    m = (ids == 25) & (np.hypot(ax - 0.042, z - (PK1 - 0.013)) < 0.0045)
    sd = np.hypot(ax[m] - 0.042, z[m] - (PK1 - 0.013))
    col[m] = mix(CHAR * 1.4, CHROME, smooth(0.0045, 0.0015, sd) * 0.8)

    # fabric: low-frequency mottling, fine weave grain, fold shading on the sleeves
    mott = fbm(P, 0.12)
    grain = vnoise(P, 0.003)
    col *= (0.93 + 0.10 * mott + 0.05 * (grain - 0.5))[:, None]
    elbow = np.exp(-((ax - 0.45) / 0.035) ** 2) * sleeve
    folds = 0.5 + 0.5 * np.sin(phi * 3 + ax * 140)
    col *= (1 - 0.12 * elbow * folds)[:, None]
    # faded tops of the shoulders and a little grime near cuffs and waistband
    col = mix(col, col * 0.9 + 0.08, np.clip(N[:, 2], 0, 1) * 0.35)
    grime = np.clip(np.where(sleeve, (ax - 0.55) / 0.1, (BOTTOM + 0.12 - z) / 0.08), 0, 1) * fbm(P, 0.04)
    col *= (1 - 0.12 * grime)[:, None]
    return col, ids


# --- pack -----------------------------------------------------------------------------------------
P_TANK, P_HOUSING, P_FIN, P_PLATE = 1, 2, 3, 4

def pack_colors(P, N, part, g):
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    n = len(x)
    TANK_X, TANK_Y, TANK_R = g['TANK_X'], g['TANK_Y'], g['TANK_R']
    tx = x - np.sign(x) * TANK_X
    ty = y - TANK_Y
    r = np.hypot(tx, ty)
    th = np.arctan2(ty, tx)
    ang = np.arctan2(tx, ty)                              # 0 = facing the camera behind the wearer
    tank, housing, fin, plate = part == P_TANK, part == P_HOUSING, part == P_FIN, part == P_PLATE
    radial = (N[:, 0] * tx + N[:, 1] * ty) / np.maximum(r, 1e-6)

    rules = [
        (tank & (z < 0.99), METAL, 1),                    # nozzle bell
        (tank & (z < 1.06), CHAR, 2),                     # skirt
        (tank & (z > 1.548), CHROME, 10),                 # polished tip
        (tank & (z > 1.435), ORANGE, 3),                  # nose cone
        (tank & (z > 1.405), RED, 4),
        (tank & (z > 1.30) & (z < 1.335), ORANGE, 5),     # band
        (tank & (z > 1.10) & (z < 1.125), ORANGE, 6),
        (tank, SATIN, 7),
        (fin, ORANGE, 8),
        (housing, METAL, 9),
        (plate, CHAR, 11),                                # padded mount against the back
    ]
    col, ids = paint_regions(n, rules, (SATIN, 7))

    # painted-metal finish: subtle mottling and orange-peel
    paint = (ids >= 2) & (ids <= 8) & (ids != 7)
    col[paint] *= (0.94 + 0.08 * fbm(P[paint], 0.08) + 0.03 * (vnoise(P[paint], 0.003) - 0.5))[:, None]

    # The avatar toon shader ignores glTF metallic/roughness, so the metal is painted in: baked "studio"
    # reflections. On a vertical tank they are streaks along its length, i.e. texel columns in the UVs.
    # The back (ang = 0) is what other players see most, so it stays bright; the dark band sits off to the side.
    streak = np.exp(-((ang - 0.42) / 0.05) ** 2)
    broad = np.exp(-((ang - 0.25) / 0.38) ** 2)
    m = (ids == 7) | (ids == 10)
    a = ang[m]
    env = (0.90 + 0.20 * broad[m] + 0.40 * streak[m]
           + 0.12 * np.exp(-((a + 1.00) / 0.12) ** 2)            # rim from the fill side
           - 0.30 * np.exp(-((a + 0.58) / 0.18) ** 2)            # dark reflected horizon
           - 0.22 * np.exp(-((np.abs(a) - 1.60) / 0.35) ** 2))   # darker toward the silhouette
    env = env + 0.10 * np.clip((z[m] - 1.20) / 0.25, 0, 1)        # sky above, slightly brighter
    brushed = 0.95 + 0.07 * vnoise(P[m], np.array([0.05, 0.05, 0.003]))   # lathe-turned grain
    col[m] *= (env * brushed)[:, None]
    m = (ids >= 3) & (ids <= 6)                                  # clear-coat gloss on the painted parts
    col[m] = col[m] * (0.93 + 0.12 * broad[m])[:, None] + 0.30 * streak[m][:, None]

    # stencilled "FUEL" on each tank, facing back
    m = tank & (np.abs(ang * TANK_R) < 0.046) & (np.abs(z - 1.215) < 0.016)
    txt = stencil('fuel', 0.5 - ang[m] * TANK_R / 0.088, (z[m] - 1.2013) / 0.0275)
    col[m] = mix(col[m], RED * 0.8, txt * 0.95)

    # pinstripes either side of the mid band
    pin = tank & (((z > 1.2925) & (z < 1.2965)) | ((z > 1.3385) & (z < 1.3425)))
    col[pin] = RED

    # vertical weld seams on the tank body and nose
    dth = ((th + math.pi / 4) % (math.pi / 2)) - math.pi / 4
    seam = tank & (z > 1.06) & (np.abs(dth) * r < 0.0007)
    col[seam] *= 0.62

    # rivet rows: dark ring + small highlight
    for zr in (1.068, 1.398, 1.442):
        ang = (th / (2 * math.pi / 24)) % 1.0 - 0.5
        d = np.hypot(ang * (2 * math.pi / 24) * r, z - zr)
        m = tank & (d < 0.0028)
        col[m] = mix(col[m] * 0.55, CHROME, smooth(0.0028, 0.0008, d[m]) * 0.8)

    # nozzle: heat tint from steel to bronze to blued at the lip, soot inside
    m = ids == 1
    t = np.clip((0.99 - z[m]) / 0.06, 0, 1)
    heat = np.where(t[:, None] < 0.5, mix(METAL, BRONZE, t * 2), mix(BRONZE, HEAT_BLUE, (t - 0.5) * 2))
    inner = (radial[m] < 0.0) | (r[m] < 0.040) & (z[m] < 0.965)
    col[m] = np.where(inner[:, None], SOOT * (0.8 + 0.4 * vnoise(P[m], 0.01))[:, None], heat * (0.9 + 0.15 * vnoise(P[m], np.array([0.03, 0.03, 0.002])))[:, None])

    # soot streaks climbing from the nozzles, and chipped paint on exposed edges
    st = tank & (z >= 0.99)
    streak = vnoise(P[st], np.array([0.003, 0.003, 0.06]))
    soot = np.clip((1.16 - z[st]) / 0.12, 0, 1) * (0.5 + 0.5 * streak)
    col[st] = mix(col[st], SOOT, soot * 0.55)
    chip_zone = (tank & (z > 1.0) & ((np.abs(z - 1.435) < 0.012) | (z > 1.52) | (np.abs(z - 1.06) < 0.01))) | (fin & (r > TANK_R + 0.04))
    chips = chip_zone & (vnoise(P, 0.004) > 0.80)
    col[chips] = METAL * 0.9

    # fins: worn darker trailing edge, red tips, a rivet row along the root
    m = fin
    col[m] *= (1 - 0.25 * smooth(TANK_R + 0.03, TANK_R + 0.058, r[m]))[:, None]
    col[m & (z < 1.0)] = RED * 0.9
    rz = ((z - 1.0) / 0.022) % 1.0 - 0.5
    d = np.hypot(r - (TANK_R + 0.009), rz * 0.022)
    m = fin & (z > 1.03) & (z < 1.15) & (d < 0.0026)
    col[m] = mix(col[m] * 0.55, CHROME, smooth(0.0026, 0.0008, d[m]) * 0.8)

    # housing: brushed aluminium, darker panel edges, screws, vent slats and the fuel gauge
    m = housing
    brushed = 0.88 + 0.12 * vnoise(P[m], np.array([0.06, 0.06, 0.0009]))
    col[m] = METAL * brushed[:, None]
    back = m & (N[:, 1] > 0.7)
    edge_d = np.minimum.reduce([0.055 - np.abs(x), z - 1.07, 1.40 - z])
    col[back] *= (0.8 + 0.2 * smooth(0.0, 0.006, edge_d[back]))[:, None]
    for sx in (-0.045, 0.045):
        for sz in (1.083, 1.387):
            d = np.hypot(x - sx, z - sz)
            s = back & (d < 0.004)
            col[s] = mix(CHAR, CHROME, smooth(0.004, 0.001, d[s]) * 0.7)
            slot = s & (np.abs(x - sx) < 0.0006)
            col[slot] = CHAR
    vent = back & (z > 1.12) & (z < 1.24) & (np.abs(x) < 0.04)
    f = ((z - 1.12) / 0.02) % 1.0
    col[vent] = mix(SOOT, METAL * 0.85, smooth(0.15, 0.9, f[vent]))
    gr = np.hypot(x, z - 1.31)
    gang = np.arctan2(x, z - 1.31)
    gauge = back & (gr < 0.034)
    gc = np.tile(GAUGE_FACE, (n, 1))
    tick = (np.abs(((gang / (math.pi / 6)) + 0.5) % 1.0 - 0.5) < 0.06) & (gr > 0.021) & (gr < 0.027)
    gc[tick] = CHAR
    red_zone = (gang > 1.6) & (gang < 2.5) & (gr > 0.023) & (gr < 0.027)
    gc[red_zone] = RED
    needle_w = 0.0016 * (1 - gr / 0.026)
    needle = (np.abs(np.sin(gang - 0.6)) * gr < needle_w) & (np.cos(gang - 0.6) > 0) & (gr < 0.026)
    gc[needle] = RED * 0.9
    gc[gr < 0.0035] = CHAR
    bezel = gr > 0.029
    gc[bezel] = mix(CHAR, CHROME, 0.5 + 0.5 * np.cos(gang - 2.4))[bezel]
    glare = ~bezel & (np.abs(gr - 0.019) < 0.003) & (gang < -0.3) & (gang > -1.4)
    gc[glare] = gc[glare] * 0.6 + 0.4
    col[gauge] = gc[gauge]

    # caution plate under the vents, and hazard stripes on top of the housing
    lab = back & (np.abs(x) < 0.036) & (z > 1.088) & (z < 1.106)
    col[lab] = CAUTION
    edge = lab & ((np.abs(x) > 0.0335) | (z < 1.0905) | (z > 1.1035))
    col[edge] = CHAR
    txt = stencil('caution', (0.032 - x[lab]) / 0.064, (z[lab] - 1.0915) / 0.011)
    col[lab] = mix(col[lab], CHAR, txt * 0.95)
    top = housing & (N[:, 2] > 0.7)
    hz = ((x[top] + y[top]) / 0.016) % 1.0
    col[top] = mix(CAUTION, CHAR, smooth(0.46, 0.54, hz) * (1 - smooth(0.96, 1.0, hz)))

    # mount: dark padded nylon, quilted every 3 cm with darker stitch lines
    m = plate
    col[m] = CHAR * (1.15 + 0.12 * fbm(P[m], 0.03))[:, None]
    q = ((z[m] - 1.16) / 0.03) % 1.0
    col[m] *= (0.8 + 0.2 * smooth(0.0, 0.25, q) * smooth(1.0, 0.75, q))[:, None]

    col *= (0.96 + 0.06 * fbm(P, 0.05))[:, None]
    return col, ids


# --- AO bake ----------------------------------------------------------------------------------------
def bake_ao(obj, images_by_mat, samples=48, distance=0.12):
    """Bake ambient occlusion into one image per material slot (returns {mat_index: HxWx3 array})."""
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    if scene.world is None:
        scene.world = bpy.data.worlds.new('World')
    scene.world.light_settings.distance = distance
    scene.render.bake.margin = 16
    targets = {}
    for mi, img in images_by_mat.items():
        mat = obj.data.materials[mi]
        node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = img
        for nd in mat.node_tree.nodes:
            nd.select = False
        node.select = True
        mat.node_tree.nodes.active = node
        targets[mi] = node
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='AO')
    out = {}
    for mi, img in images_by_mat.items():
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        out[mi] = px.reshape(h, w, 4)[..., :3]
        obj.data.materials[mi].node_tree.nodes.remove(targets[mi])
    return out


def build_textures(obj, mw, size, suit_img, pack_img, g):
    me = obj.data
    results = {}
    for mi, fn, seams in ((0, suit_colors, True), (1, pack_colors, False)):
        pix, P, N, part = rasterize(me, mw, mi, size)
        col, ids = fn(P, N, part, g)
        cols, filled, idmap, posmap = resolve(size, pix, col, ids, P)
        if seams:
            cols = seams_and_stitches(cols, filled, idmap, posmap, size)
        results[mi] = (cols, filled)
    ao_imgs = {mi: bpy.data.images.new('AO_%d' % mi, size, size, alpha=False, float_buffer=True) for mi in results}
    ao = bake_ao(obj, ao_imgs)
    for mi, img in ((0, suit_img), (1, pack_img)):
        cols, filled = results[mi]
        a = np.clip(ao[mi], 0, 1).mean(axis=2)
        strength = 0.5 if mi == 0 else 0.55
        cols = cols * (1 - strength + strength * a ** 1.3)[..., None]
        cols = film_grade(cols)
        cols = fill_gutters(cols, filled)
        rgba = np.concatenate([cols, np.ones((size, size, 1), dtype=np.float32)], axis=2)
        img.pixels.foreach_set(rgba.ravel())
        img.update()
    for img in ao_imgs.values():
        bpy.data.images.remove(img)
