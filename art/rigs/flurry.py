"""FLURRY the snow leopard: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 small rounded ears; MH2 heavy sleepy eyelids; MH3 open ring rosettes on back and limbs; MH4 a tail thicker
than her arm and longer than she is tall, usually carried in her mouth (idle) ; MH5 big paws.  Height 0.70.
Special (SPEC_V2 section 8): she lets the tail drop and it thumps on the floor.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres them.
"""
from __future__ import annotations

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, line, lerp, mix, outlined, path,
                   pose, ribbon, rotate, sparkle, sticker, sym, translate)
from lib2d.chibi import eye, figure, open_mouth, w_mouth
from lib2d.geom import along, bezier

CHAR_ID = "flurry"
HEIGHT = 0.70
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Flurry)
COAT = "#e9e2d0"
SHADE = "#cfc6b0"
ROS = "#5b514c"       # rosette rings
ROS_C = "#8a7f76"     # rosette centres
BELLY = "#fbf8ef"
NOSE = "#c98f8f"
EYES = "#8fb3b0"
# derived
INK = mix(ROS, "#2a2628", 0.45)
EAR_IN = mix(NOSE, BELLY, 0.55)
IRIS_LO = mix(EYES, ROS, 0.4)
LID = mix(SHADE, ROS_C, 0.25)
MOUTH_IN = mix(INK, NOSE, 0.4)
TONGUE = "#ee7fa6"

W = 3.4
HEAD_Y = 272.0

DEFAULTS = {"bob": 0.0, "ear_l": 0.0, "ear_r": 0.0, "eyes": "open", "lid": 0.5, "mouth": "tail",
            "drop": 0.0, "corner": 0.0, "tilt": 0.0, "squash": 0.0, "hop": 0.0, "thump": 0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


def _ring(x, y, r, rot=0.0):
    """MH3: an open rosette: a lighter centre inside a broken dark ring."""
    return g(circle(x, y, r * 0.62, fill=ROS_C),
             circle(x, y, r, fill="none", stroke=ROS, stroke_width=max(2.0, r * 0.36),
                    stroke_dasharray="%g %g" % (r * 1.5, r * 0.7), transform=rotate(rot, x, y)))


# ------------------------------------------------------------------ head  (MH1, MH2)

HEAD_HALF = [(0, -58), (32, -56), (54, -42), (64, -18), (65, 6), (58, 26), (40, 42), (0, 50)]
EAR = [(24, -50), (28, -72), (44, -84), (58, -72), (62, -46)]
EAR_INNER = [(33, -56), (36, -70), (45, -76), (53, -68), (54, -54)]


def _ear(side, extra):
    shape = path(blob(EAR if side > 0 else _mx(EAR)), fill=COAT)
    inner = path(blob(EAR_INNER if side > 0 else _mx(EAR_INNER)), fill=EAR_IN)
    back = path(blob([(side * 26, -88), (side * 66, -88), (side * 66, -60), (side * 50, -78)]), fill=ROS)
    tf = rotate(side * extra, side * 42, -50)
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, back, inner)), transform=tf)


def _mouth(p):
    m = p["mouth"]
    if m == "tail":       # the tail end is held across the mouth; only the corners of the cheeks show
        return g([path("M%g 27 Q%g 33 %g 37" % (s * 15, s * 19, s * 15), fill="none", stroke=INK,
                       stroke_width=2.2, stroke_linecap="round") for s in (-1, 1)])
    if m == "w":
        return w_mouth(0, 27, 8.0, 3.6, ink=INK, width=2.3, philtrum=4.0)
    big = m == "open"
    return g(open_mouth(0, 28, 7.0 if big else 5.0, 6.5 if big else 4.0, ink=INK, inner=MOUTH_IN, tongue=TONGUE,
                        width=2.2),
             w_mouth(0, 27, 8.0, 3.0, ink=INK, width=2.3, philtrum=4.0))


def _head(p):
    skull = path(blob(sym(HEAD_HALF)), fill=COAT)
    muzzle = blob(sym([(0, 6), (16, 8), (30, 20), (26, 38), (0, 48)]))
    marks = [path(blob([(-90, 30), (0, 44), (90, 30), (90, 90), (-90, 90)]), fill=SHADE),
             path(blob([(44, -50), (80, -30), (80, 40), (50, 30), (58, 0)]), fill=SHADE),
             path(muzzle, fill=BELLY),
             [circle(x, y, r, fill=ROS) for (x, y, r) in ((0, -42, 3.6), (-12, -36, 2.8), (12, -36, 2.8),
                                                         (-50, -8, 2.6), (50, -8, 2.6), (-54, 6, 2.2),
                                                         (54, 6, 2.2))],
             _ring(-34, -36, 6.5, 30), _ring(34, -36, 6.5, -60)]
    eyes = [eye(s * 26, -6, 13.0, 12.0, ink=INK, lid_fill=LID, iris=EYES, iris_lo=IRIS_LO, pupil=INK,
                lid=p["lid"], arch=0.25, state=p["eyes"]) for s in (-1, 1)]       # MH2: heavy straight lids
    nose = blob([(-7, 13), (0, 12), (7, 13), (4, 19), (0, 21), (-4, 19)])
    face = detail(clip(skull, marks), eyes, _mouth(p),
                  path(nose, fill=NOSE, stroke=INK, stroke_width=1.8, stroke_linejoin="round"),
                  [line(s * 34, 22 + 6 * k, s * 56, 20 + 9 * k, stroke=SHADE, stroke_width=1.5) for s in (-1, 1)
                   for k in (0, 1)])
    tf = "%s %s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 50),
                       "translate(0 50) scale(%g) translate(0 -50)" % HS)
    return g(_ear(-1, p["ear_l"]), _ear(1, p["ear_r"]), outlined(skull, ink=INK, width=W), face, _tail_front(p),
             transform=tf)


# ------------------------------------------------------------------ body, arms, big paws  (MH3, MH5)

BODY_HALF = [(0, 314), (30, 318), (46, 340), (54, 382), (53, 424), (46, 454), (28, 466), (0, 468)]
FOOT = [(2, 465), (6, 450), (26, 443), (47, 449), (54, 463), (46, 472), (26, 474), (9, 472)]


def _body(p):
    bob = p["bob"]
    pts = [(x, y + bob * max(0.0, (440.0 - y) / 90.0)) for x, y in BODY_HALF]
    body = path(blob(sym(pts)), fill=COAT)
    feet = [path(blob(FOOT), fill=COAT), path(blob(_mx(FOOT)), fill=COAT)]
    belly = blob(sym([(0, 334), (24, 342), (32, 390), (26, 438), (0, 452)]))
    marks = [path(blob([(36, 304), (70, 320), (70, 472), (36, 472), (48, 400)]), fill=SHADE),
             path(belly, fill=BELLY),
             _ring(-44, 408, 8.0, 10), _ring(46, 430, 7.0, 70), _ring(-40, 444, 6.0, 40), _ring(44, 386, 6.5, 0)]
    foot_marks = [path(blob([(s * 4, 468), (s * 26, 470), (s * 56, 466), (s * 56, 478), (s * 4, 478)]), fill=SHADE)
                  for s in (-1, 1)]
    toes = [line(s * x, 464, s * x, 471.5, stroke=INK, stroke_width=2.0) for s in (-1, 1) for x in (19.0, 33.0)]
    return g(outlined(body, feet, ink=INK, width=W), detail(clip(body, marks), clip(feet, foot_marks), toes))


def _arm(side, p):
    bob = p["bob"]
    sh, hand = (side * 44, 344 + bob), (side * 54, 392 + bob * 0.4)
    arm = path(capsule(sh, hand, 12.0, 11.5), fill=COAT)
    paw = ellipse(hand[0] + side * 1, hand[1] + 10, 16.0, 15.0, fill=COAT)       # MH5: big paws
    rings = [_ring(sh[0] + side * 3, sh[1] + 18, 6.0, 20 * side), _ring(hand[0] - side * 1, hand[1] - 12, 4.8, 0)]
    toes = [line(hand[0] + side * 1 + dx, hand[1] + 18, hand[0] + side * 1 + dx, hand[1] + 24, stroke=INK,
                 stroke_width=1.8) for dx in (-5.5, 5.5)]
    return g(outlined(arm, paw, ink=INK, width=W), detail(clip(arm, rings), toes))


# ------------------------------------------------------------------ tail  (MH4)

TAIL_W = [22.0, 32.0, 34.0, 33.0, 31.0, 29.0]
N = 14
HS = 1.12             # head scale about the neck point (0, 50) of the head frame


def _h2c(pt, p):
    """Head-frame point -> canvas (ignoring the small tilt)."""
    return (pt[0] * HS, HEAD_Y + p["bob"] + 50 + (pt[1] - 50) * HS)


def _front(p):
    """The end of the tail in the head frame: over her cheek and across the mouth (corner = 1: at the corner)."""
    c = p["corner"]
    return bezier((76, 20), (60, 28 + 6 * c), (30, 30 + 8 * c), (lerp(-24, 18, c), lerp(32, 42, c)), N)


def _spine(p):
    """Full canvas spine, blending the held tail (drop = 0) with the tail on the floor (drop = 1)."""
    j = _h2c((76, 20), p)
    up = bezier((30, 446), (118, 474), (128, 360), j, N) + [_h2c(q, p) for q in _front(p)[1:]]
    down = (bezier((30, 446), (66, 464), (100, 458), (132, 452), N)
            + bezier((132, 452), (156, 448), (176, 448), (196, 452), N)[1:])
    t = max(0.0, min(1.0, p["drop"]))
    n = len(up)
    out = []
    for i, (a, b) in enumerate(zip(up, down)):
        u = i / float(n - 1)
        x, y = lerp(a[0], b[0], t), lerp(a[1], b[1], t)
        y -= 50.0 * u * t * (1 - t) * 2           # mid-fall the end swings out in an arc
        x += 70.0 * u * t * (1 - t) * 2
        out.append((x, y))
    return out


def _rings(spine, ts, r, flip=1):
    out = []
    for k, t in enumerate(ts):
        (x, y), _ = along(spine, t)
        out.append(_ring(x + (3 if k % 2 else -3) * flip, y + (-3 if k % 2 else 3), r, 37 * k))
    return out


def _tail(p):
    """Back part (behind the body): the whole tail once dropped, else root to the cheek."""
    held = p["drop"] < 0.5
    spine = _spine(p)
    if held:
        spine = spine[:N]
        widths = TAIL_W[:4]
    else:
        widths = TAIL_W
    shape = path(ribbon(spine, widths), fill=COAT)
    shade = path(ribbon([(x, y + 9) for x, y in spine], [8, 12, 14, 12]), fill=SHADE)
    rings = _rings(spine, (0.22, 0.45, 0.68, 0.9) if held else (0.15, 0.3, 0.45, 0.6, 0.75), 6.4)
    tip = []
    if not held:          # the darker end of the tail shows once it is out of her mouth
        (x, y), _ = along(spine, 0.97)
        tip.append(circle(x, y, 13, fill=ROS_C))
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, shade, rings, tip)))


def _tail_front(p):
    """In the head frame: the end of the tail coming over the cheek into her mouth."""
    if p["drop"] >= 0.5:
        return []
    spine = _front(p)
    w = 31.0 / HS
    shape = path(ribbon(spine, [w, w * 0.97, w * 0.94]), fill=COAT)
    shade = path(ribbon([(x, y + 8) for x, y in spine], [8, 10, 8]), fill=SHADE)
    end = []
    (x, y), _ = along(spine, 0.97)
    end.append(circle(x, y, 10, fill=ROS_C))
    return g(outlined(shape, ink=INK, width=W / HS), detail(clip(shape, shade, _rings(spine, (0.3, 0.62), 5.6), end)))


def _thump(p):
    if not p["thump"]:
        return []
    x, y = 200.0, 446.0
    out = []
    for a, r0, r1 in ((-150, 18, 32), (-110, 20, 34), (-70, 18, 30)):
        import math
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        out.append(line(CX + x - 4 + c * r0, y + s * r0, CX + x - 4 + c * r1, y + s * r1, stroke=INK,
                        stroke_width=3.2))
    return out


SPARKLES = {1: [(-96, 210, 9, BELLY), (92, 190, 7, EYES)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_tail(p), _body(p), _arm(-1, p), _arm(1, p), _head(p)], p)
    return sticker(fig, extras, _thump(p), ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    # slow sleepy breathing, tail end held in her mouth, one ear drifting
    "idle": anim([pose(REST), pose(REST, bob=1.6, squash=0.01, ear_l=-5), pose(REST, bob=0.8, lid=0.56)],
                 fps=3, loop=True),
    # she talks round the tail: it drops a little while her mouth is open
    # she mumbles round the tail, holding it in the corner of her mouth
    "talk": anim([pose(REST, mouth="open_s", corner=1.0, tilt=-2.0), pose(REST, mouth="w", corner=1.0, tilt=-1.0)],
                 fps=6, loop=True),
    "blink": anim([pose(REST, eyes="closed")], fps=8, loop=False),
    # special: she lets the tail drop and it thumps
    "special": anim([pose(REST, mouth="open", corner=1.0, lid=0.4),
                     pose(REST, mouth="open_s", drop=0.7, lid=0.35),
                     pose(REST, mouth="w", drop=1.0, squash=0.02, thump=1, lid=0.3)], fps=6, loop=False),
}
