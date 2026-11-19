"""Birthday card renderer.

Composites a birthday card from a user's profile picture:

    - the PFP fills the frame (centre-cropped square)
    - a birthday cupcake sits low in the frame, in front of the user, chosen at
      random from assets/cupcakes/ (falls back to assets/birthday_cake.png, then
      to a procedurally drawn cake)
    - "Happy Birthday <name>" is set on a rainbow arc across the top

Design constraint: no face detection and no AI. Instead the decoration is
*bounded* geometrically. Its top edge may never sit above ``FACE_SAFE_TOP`` of
the frame, and its size is derived from the visible fraction that fits below
that line. Avatars are normally cropped tight on the head with the face in the
upper-middle, so staying below the line keeps the face clear without ever
locating it.
"""

from __future__ import annotations

import colorsys
import io
import math
import random
from functools import lru_cache, reduce
from math import gcd
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

RESAMPLE = Image.Resampling.LANCZOS
ROTATE_RESAMPLE = Image.Resampling.BICUBIC

# --- Tunables ---------------------------------------------------------------

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_CAKE_ASSET = ASSETS_DIR / "birthday_cake.png"
CUPCAKE_DIR = ASSETS_DIR / "cupcakes"

CARD_SIZE = 512

# The hard rule: the cake's highest pixel may never sit above this fraction of
# the frame height. 0.70 clears eyes, nose, mouth and most chins on a tight head
# crop.
FACE_SAFE_TOP = 0.70
# Sitting in the lower-left corner, slightly larger: more of the bottom is
# clipped so the sprite can be bigger while its top stays on the face-safe line.
CAKE_VISIBLE_FRAC = 0.78    # fraction of the sprite inside the band
CAKE_ALIGN_X = "left"       # left | centre | right
CAKE_MARGIN_X = 0.04        # gap from the aligned edge, fraction of width
CAKE_ANGLE = -9.0           # tilt in degrees; negative = top leans right (into the frame)
CAKE_WIDTH_FRAC = 0.86      # hard cap on width, for very wide art

# Decoration extras. Both off: the shipped cupcakes read fine bare, and Geoffery
# asked for no candle and no shadow.
ADD_CANDLE = False
ADD_SHADOW = False
ADD_GLOW = False
# Edge-darkening gradients. Off: Geoffery called them vignetting. The title keeps
# its dark outer outline, which carries legibility on bright avatars instead.
ADD_SCRIM = False

# Curved title: bubbly face, rainbow letters, white inner + dark outer outline.
TITLE_TOP_FRAC = 0.050
TITLE_MAX_WIDTH_FRAC = 0.47  # half-width from centre
ARC_RADIUS_FRAC = 1.55  # gentle arc, keeps per-glyph rotation small
TITLE_PALETTE = (
    (255, 92, 96, 255),
    (255, 171, 64, 255),
    (255, 225, 90, 255),
    (126, 214, 86, 255),
    (92, 178, 255, 255),
    (198, 132, 255, 255),
)
TITLE_OUTLINE_INNER = (235, 246, 255, 255)   # neon ring
TITLE_OUTLINE_OUTER = (38, 26, 32, 255)
TITLE_STROKE_INNER = 0.035  # as a fraction of font size, so long names stay legible
TITLE_STROKE_OUTER = 0.085

# Soft scrims so white text and the cake read against any PFP.
TOP_SCRIM_MAX = 108
BOTTOM_SCRIM_MAX = 130
SCRIM_DEPTH = 0.30

# Animated PFPs: uniform frame grid. Holds are duplicated into whole ticks so
# timing is preserved exactly and the title shimmer keeps advancing during a
# hold instead of stalling for its duration. MIN_TEXT_FPS subdivides slow GIFs
# further, so a 3-frame/200ms PFP doesn't jerk the colour 120 degrees a step.
MAX_ANIM_FRAMES = 96
UNIFORM_FRAMES = True
UNIFORM_MIN_MS = 20
MIN_TEXT_FPS = 16
MAX_TICK_MS = 1000.0 / MIN_TEXT_FPS

# Title colours drift one step per frame so the lettering shimmers. Static
# PFPs get a short looping animation instead of a still to carry it.
COLOUR_CYCLE = True
CYCLE_FRAMES = 6          # must divide TITLE_PALETTE evenly or the loop jumps
CYCLE_MS = 110
# One full hue turn every COLOUR_PERIOD_MS. Animated PFPs are timed against
# this in milliseconds, not per frame, so a 40ms-per-frame GIF doesn't strobe
# while a 100ms one crawls.
COLOUR_PERIOD_MS = CYCLE_FRAMES * CYCLE_MS

# All output is WebP: true colour, so no palette quantisation, and animated
# WebP carries the colour cycle far smaller than an equivalent GIF.
WEBP_QUALITY = 90
WEBP_METHOD = 4

FONT_CANDIDATES = (
    ASSETS_DIR / "fonts" / "RubikBubbles-Regular.ttf",
    ASSETS_DIR / "fonts" / "BubblegumSans-Regular.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
)

_MASTER_W = 1024  # cake is drawn at this width, then scaled down


# --- Fonts ------------------------------------------------------------------


@lru_cache(maxsize=32)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)  # type: ignore[return-value]


def _probe():
    """Disposable draw context, used only for text measurement."""
    return ImageDraw.Draw(Image.new("L", (1, 1)))


# --- Cake sprite ------------------------------------------------------------


@lru_cache(maxsize=4)
def _cake_master() -> Image.Image:
    """Draw the cake once at master resolution.

    Cached deliberately: the sprinkle layout is random, and every GIF frame must
    show the *same* cake or the animation will shimmer.
    """
    W, H = _MASTER_W, 660
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    SPONGE = (150, 32, 32, 255)
    SPONGE_MID = (170, 42, 42, 255)
    SPONGE_DARK = (116, 20, 20, 255)
    CREAM = (255, 246, 233, 255)
    FROSTING = (255, 253, 249, 255)
    FROSTING_SHADE = (232, 224, 212, 255)
    BOARD = (198, 203, 212, 255)

    cx = W // 2

    def tier(l, r, t, b, cap, drip_step, drip_w, band_t, band_h):
        """One cake tier: sponge, cream band, dark base, frosting cap + drips."""
        radius = int((r - l) * 0.055)
        d.rounded_rectangle([l, t, r, b], radius=radius, fill=SPONGE)
        # vertical shading so the cylinder reads as round, not flat
        d.rounded_rectangle([l, t, l + (r - l) * 0.18, b], radius=radius, fill=SPONGE_MID)
        d.rounded_rectangle([l, t + band_t, r, t + band_t + band_h], fill=CREAM)
        d.rectangle([l, b - 22, r, b], fill=SPONGE_DARK)
        # frosting cap, with a shaded underside
        d.ellipse([l, t - cap // 2, r, t + cap], fill=FROSTING)
        d.ellipse([l, t + cap * 0.30, r, t + cap], fill=FROSTING_SHADE)
        d.ellipse([l, t - cap // 2, r, t + cap * 0.62], fill=FROSTING)
        for i, x in enumerate(range(l + drip_step // 3, r - drip_w, drip_step)):
            h = int(drip_w * (1.15 if i % 2 == 0 else 0.7))
            d.rounded_rectangle([x, t + cap - drip_w // 2, x + drip_w, t + cap + h],
                                radius=drip_w // 2, fill=FROSTING)

    # --- cake board ---
    d.ellipse([60, 600, W - 60, 652], fill=BOARD)
    d.ellipse([60, 608, W - 60, 640], fill=(228, 232, 238, 255))

    # --- bottom tier ---
    tier(150, W - 150, 380, 620, cap=78, drip_step=98, drip_w=52, band_t=84, band_h=70)

    # --- top tier ---
    tier(290, W - 290, 214, 392, cap=66, drip_step=80, drip_w=46, band_t=62, band_h=52)

    # --- sprinkles on the top cap ---
    rng = random.Random(20261119)
    sprinkle_colours = [
        (226, 70, 70, 255), (250, 204, 72, 255), (88, 172, 226, 255),
        (255, 255, 255, 255), (138, 208, 130, 255), (234, 132, 192, 255),
    ]
    top_l, top_r, top_t, cap2 = 290, W - 290, 214, 66
    for _ in range(52):
        sx = rng.uniform(top_l + 26, top_r - 26)
        sy = top_t + 8 + rng.uniform(0, 1) ** 0.7 * cap2 * 0.52
        r = rng.uniform(4.5, 7.5)
        d.ellipse([sx - r, sy - r * 0.78, sx + r, sy + r * 0.78],
                  fill=rng.choice(sprinkle_colours))

    # --- candles: varied spacing and height so it isn't robotic ---
    candles = [
        (cx - 168, 118, (212, 56, 56, 255)),
        (cx - 74, 140, (242, 172, 64, 255)),
        (cx + 40, 108, (84, 166, 106, 255)),
        (cx + 150, 130, (228, 110, 172, 255)),
    ]
    flame_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flame_layer)
    for x, tall, colour in candles:
        body_bot = top_t + 14
        body_top = body_bot - tall
        w = 22
        d.rounded_rectangle([x - w // 2, body_top, x + w // 2, body_bot],
                            radius=7, fill=colour)
        # wax highlight
        d.rounded_rectangle([x - w // 2 + 3, body_top + 6, x - w // 2 + 7, body_bot - 6],
                            radius=3, fill=(255, 255, 255, 70))
        # wick
        d.rectangle([x - 2, body_top - 14, x + 2, body_top], fill=(58, 48, 44, 255))
        # flame: glow, body, hot core
        fd.ellipse([x - 27, body_top - 64, x + 27, body_top - 6], fill=(255, 184, 62, 115))
        fd.ellipse([x - 15, body_top - 50, x + 15, body_top - 8], fill=(255, 200, 80, 255))
        fd.ellipse([x - 6, body_top - 38, x + 6, body_top - 18], fill=(255, 250, 220, 255))
    img.alpha_composite(flame_layer.filter(ImageFilter.GaussianBlur(2.5)))

    return img.crop(img.getbbox())


@lru_cache(maxsize=8)
def cake_sprite(width: int) -> Image.Image:
    """The drawn cake scaled to ``width`` px."""
    master = _cake_master()
    height = max(1, round(master.height * width / master.width))
    return master.resize((width, height), RESAMPLE)


def load_cake_sprite(path: str | Path, width: int) -> Image.Image:
    """Use a custom transparent PNG instead of the drawn cake."""
    src = Image.open(path).convert("RGBA")
    bbox = src.getbbox()
    if bbox:
        src = src.crop(bbox)
    height = max(1, round(src.height * width / src.width))
    return src.resize((width, height), RESAMPLE)


CANDLE_COLOURS = (
    (255, 86, 96), (255, 196, 72), (120, 206, 140),
    (96, 172, 255), (200, 136, 255), (255, 140, 200),
)


def _frosting_top(sprite: Image.Image) -> int:
    """Row where the frosting mass starts.

    The sprite's topmost pixels are the decorative topper (a flower, a party
    hat, a sign on a stick), not the frosting. Inserting the candle at a fixed
    offset from the top therefore makes it float in mid-air. Instead, find the
    first row that is substantially wide, which is where the frosting actually
    begins, whatever the crop or padding happens to be.
    """
    alpha = sprite.getchannel("A")
    w, h = sprite.size
    counts = []
    for y in range(h):
        hist = alpha.crop((0, y, w, y + 1)).histogram()
        counts.append(sum(hist[201:]))
    peak = max(counts) if counts else 0
    if peak <= 0:
        return h // 3
    threshold = peak * 0.5
    for y, count in enumerate(counts):
        if count >= threshold:
            return y
    return h // 3


def _add_candle(sprite: Image.Image, seed: str) -> Image.Image:
    """Put a lit candle in the frosting of a cupcake sprite.

    The shipped cupcakes have decorative toppers but no candle, and a birthday
    cupcake without one cannot be blown out. The candle is baked into the sprite
    rather than drawn at composite time so that the face-safe placement maths
    sees the real height including the flame: otherwise the flame pokes above
    FACE_SAFE_TOP and into the face.
    """
    w, h = sprite.size
    frosting_y = _frosting_top(sprite)

    body_h = max(6, round(h * 0.30))
    flame_h = max(5, round(h * 0.12))
    # sink the base a little into the frosting
    sink = max(2, int((h - frosting_y) * 0.18))
    # Only add canvas above the sprite if the candle would actually poke out of
    # it. A tall topper means the candle can sit entirely inside the sprite.
    pad = max(0, (body_h + flame_h + 4) - (frosting_y + sink))

    canvas = Image.new("RGBA", (w, h + pad), (0, 0, 0, 0))
    canvas.alpha_composite(sprite, (0, pad))

    rng = random.Random(seed)
    colour = rng.choice(CANDLE_COLOURS)
    d = ImageDraw.Draw(canvas)

    cw = max(3, round(w * 0.078))
    # offset to one side so it doesn't fight the cupcake's own topper
    cx = int(w * 0.5 + w * 0.20)
    cx = max(cw, min(cx, w - cw))

    # sink the base a little into the frosting
    sink = max(2, int((h - frosting_y) * 0.18))
    body_bottom = pad + frosting_y + sink
    body_top = body_bottom - body_h
    d.rounded_rectangle([cx - cw // 2, body_top, cx + cw // 2, body_bottom],
                        radius=max(1, cw // 3), fill=colour + (255,))
    stripe = max(2, cw // 3)
    for y in range(body_top + stripe, body_bottom - 1, stripe * 2):
        d.rectangle([cx - cw // 2, y, cx + cw // 2, min(y + stripe, body_bottom)],
                    fill=(255, 255, 255, 240))
    # wick
    d.rectangle([cx - 1, body_top - 3, cx + 1, body_top], fill=(62, 52, 46, 255))

    # flame: warm glow, body, hot core
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    fw = max(4, round(w * 0.13))
    top_y = body_top - 3
    gd.ellipse([cx - fw, top_y - flame_h, cx + fw, top_y + fw * 0.4],
               fill=(255, 186, 64, 140))
    gd.ellipse([cx - fw * 0.55, top_y - flame_h * 0.85, cx + fw * 0.55, top_y + fw * 0.15],
               fill=(255, 214, 96, 255))
    gd.ellipse([cx - fw * 0.22, top_y - flame_h * 0.55, cx + fw * 0.22, top_y],
               fill=(255, 250, 225, 255))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(max(1, w // 40))))
    return canvas


@lru_cache(maxsize=24)
def _sprite_for(path_str: str, mtime: float, width: int) -> Image.Image:
    """Cached sprite load, with a candle added to cupcakes.

    An animated PFP renders up to 48 frames; without this the same PNG is
    re-read, re-resized and re-candled every frame.
    """
    sprite = load_cake_sprite(path_str, width)
    if ADD_CANDLE and Path(path_str).parent == CUPCAKE_DIR:
        sprite = _add_candle(sprite, seed=Path(path_str).name)
    if CAKE_ANGLE and Path(path_str).parent == CUPCAKE_DIR:
        # Tilt before the placement maths ever sees the sprite, so the size and
        # the face-safe clamp are computed from the rotated bounding box rather
        # than the upright one. Re-crop afterwards: expand=True pads the corners
        # with transparency, which would otherwise waste the size budget.
        sprite = sprite.rotate(CAKE_ANGLE, resample=Image.Resampling.BICUBIC,
                               expand=True)
        bbox = sprite.getbbox()
        if bbox:
            sprite = sprite.crop(bbox)
    return sprite


def cupcake_assets() -> list[Path]:
    """Every cupcake cutout on disk."""
    if not CUPCAKE_DIR.is_dir():
        return []
    return sorted(p for p in CUPCAKE_DIR.glob("*.png") if p.is_file())


def pick_food(rng: random.Random | None = None) -> Path | None:
    """Choose the decoration for ONE card: a random cupcake, else the cake.

    Call this once per card, never per frame. Re-rolling inside the frame loop
    makes an animated PFP flip between cupcakes every frame.
    """
    options = cupcake_assets()
    if options:
        return (rng or random).choice(options)
    return DEFAULT_CAKE_ASSET if DEFAULT_CAKE_ASSET.exists() else None


def fit_cake(size: int, cake: Image.Image) -> Image.Image:
    """Scale the decoration so CAKE_VISIBLE_FRAC of it fits below the safe line.

    The face-safe band fixes the visible height, so the sprite is scaled to be
    slightly taller than that band. The overhang is what gets clipped off the
    bottom edge. CAKE_WIDTH_FRAC caps the result for very wide art.
    """
    budget = max(1, size - int(size * FACE_SAFE_TOP))
    target_h = max(1, round(budget / CAKE_VISIBLE_FRAC))
    target_w = max(1, round(target_h * cake.width / cake.height))

    cap = int(size * CAKE_WIDTH_FRAC)
    if target_w > cap:
        target_w = cap
        target_h = max(1, round(cake.height * cap / cake.width))
    return cake.resize((target_w, target_h), RESAMPLE)


def cake_position(size: int, cake_w: int, cake_h: int) -> tuple[int, int]:
    """Top-left corner: aligned left, bottom slightly clipped.

    The top is pinned to the face-safe line when the sprite is taller than the
    band; anything shorter just sits on the bottom edge. The horizontal clamp is
    applied after the alignment so the guarantee holds for any sprite width.
    """
    line = int(size * FACE_SAFE_TOP)
    budget = size - line
    y = line if cake_h > budget else size - cake_h

    margin = int(size * CAKE_MARGIN_X)
    if CAKE_ALIGN_X == "left":
        x = margin
    elif CAKE_ALIGN_X == "right":
        x = size - cake_w - margin
    else:
        x = (size - cake_w) // 2
    x = max(0, min(x, size - cake_w))
    return x, y


# --- PFP prep ---------------------------------------------------------------


def fit_square(pfp: Image.Image, size: int) -> Image.Image:
    """Centre-crop to square and resize, keeping alpha."""
    pfp = pfp.convert("RGBA")
    side = min(pfp.width, pfp.height)
    left = (pfp.width - side) // 2
    top = (pfp.height - side) // 2
    return pfp.crop((left, top, left + side, top + side)).resize((size, size), RESAMPLE)


@lru_cache(maxsize=4)
def _scrim(size: int) -> Image.Image:
    """Black gradient, strongest at the top and bottom edges."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = layer.load()
    assert px is not None
    depth = max(1, int(size * SCRIM_DEPTH))
    for y in range(depth):
        top_a = int(TOP_SCRIM_MAX * (1 - y / depth))
        bot_a = int(BOTTOM_SCRIM_MAX * (1 - y / depth))
        yy = size - 1 - y
        for x in range(size):
            if top_a > 0:
                px[x, y] = (0, 0, 0, top_a)
            if bot_a > 0:
                px[x, yy] = (0, 0, 0, bot_a)
    return layer


# --- Curved title -----------------------------------------------------------


def _safe_paste(dst: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """alpha_composite, but clipped to the destination instead of raising."""
    sx0, sy0 = max(0, -x), max(0, -y)
    dx0, dy0 = max(0, x), max(0, y)
    w = min(src.width - sx0, dst.width - dx0)
    h = min(src.height - sy0, dst.height - dy0)
    if w <= 0 or h <= 0:
        return
    dst.alpha_composite(src.crop((sx0, sy0, sx0 + w, sy0 + h)), (dx0, dy0))


def _rotate_hue(colour, degrees: float):
    """Shift a colour's hue, keeping saturation and value."""
    r, g, b = (c / 255 for c in colour[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + degrees / 360.0) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


def _layout(text: str, font: ImageFont.FreeTypeFont, stroke_w: int):
    """Return (per-char advances, total width, tracking) for one font.

    Glyph tiles are wider than their advance (they carry padding for the
    outline), so a glyph can paint over its neighbour. Bubblegum Sans is the
    worst offender: the "t" crossbar overhangs its advance, and the following
    glyph's white ring erases it, turning "Birthday" into "Birlhday". Computing
    the worst overhang in the run and adding that much tracking keeps every
    glyph's ink clear of the next glyph's stroke.
    """
    probe = _probe()
    widths = [probe.textlength(ch, font=font) for ch in text]
    overhang = 0
    for ch, w in zip(text, widths):
        box = font.getbbox(ch)
        if box:
            overhang = max(overhang, box[2] - w)
    tracking = max(0, math.ceil(overhang)) + stroke_w
    total = sum(widths) + tracking * max(0, len(text) - 1)
    return widths, total, tracking


def _fitted_font(text: str, size: int, base_frac: float = 0.108) -> ImageFont.FreeTypeFont:
    """Largest font size whose text (plus tracking) fits the arc budget.

    Binary search rather than stepping down a pixel at a time: a long name
    needed ~130 full layout passes per call, which dominated render time once
    every frame redrew the title.
    """
    radius = size * ARC_RADIUS_FRAC
    max_half = size * TITLE_MAX_WIDTH_FRAC
    span_max = 2 * math.asin(min(1.0, max_half / radius))
    max_arc = radius * span_max

    lo, hi = 9, max(10, int(size * base_frac))
    best = 9
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _font(mid)
        stroke_w = max(2, round(font.size * TITLE_STROKE_OUTER))
        _, total, _ = _layout(text, font, stroke_w)
        if total <= max_arc:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return _font(best)


MIN_TITLE_FRAC = 0.039      # ~20px at 512; below this the title wraps instead
SECOND_LINE_SCALE = 0.66
SECOND_LINE_GAP_FRAC = 0.008   # tightest ink-to-ink gap, as a fraction of width


def _arc_line(img: Image.Image, text: str, font_scale: float = 1.0,
              hue_shift: float = 0.0):
    """Draw one arced line onto a scratch layer and report where its ink landed.

    Positioning a second line from font metrics alone does not work: the run is
    arced, so its lowest ink is at the line ends rather than at the apex, and how
    far that dips depends on the string. Measuring the rendered ink is exact.
    """
    scratch = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_arc_text(scratch, text, font_scale=font_scale, hue_shift=hue_shift)
    return scratch, scratch.getbbox()


def _column_extents(layer: Image.Image) -> dict[int, tuple[int, int]]:
    """First and last inked row for each column.

    A single bbox is not enough to place two arced lines: the run dips at the
    ends, so the tightest gap is somewhere in the middle of the width, not at
    the bounding box edges.
    """
    w, h = layer.size
    box = layer.getbbox()
    if box is None:
        return {}
    out = {}
    for x in range(box[0], box[2]):
        b = layer.crop((x, 0, x + 1, h)).getbbox()
        if b:
            out[x] = (b[1], b[3] - 1)
    return out


@lru_cache(maxsize=64)
def _wrap_offset(greeting: str, username: str, width: int) -> int:
    """Vertical offset that puts line 2 just under line 1's lowest ink.

    Cached because the layout is identical for every frame of a card and
    measuring per-column extents is the expensive part.
    """
    canvas = Image.new("RGBA", (width, width), (0, 0, 0, 0))
    line1, _ = _arc_line(canvas, greeting)
    line2, _ = _arc_line(canvas, username, font_scale=SECOND_LINE_SCALE)
    e1, e2 = _column_extents(line1), _column_extents(line2)

    shared = set(e1) & set(e2)
    if not shared:
        return 0

    # Both lines are drawn at the same top edge, so at offset 0 they overlap.
    # The offset needed is set by the column where line 1 reaches lowest while
    # line 2 sits highest: push past that by the target gap.
    overlap = max(e1[x][1] - e2[x][0] for x in shared)
    target = max(2, round(width * SECOND_LINE_GAP_FRAC))
    return overlap + target


def draw_title(img: Image.Image, greeting: str, username: str,
               hue_shift: float = 0.0) -> None:
    """Draw the greeting and username across the top.

    A long username on one line forces the type down to ~16px at 512, which is
    legible but cramped. Past MIN_TITLE_FRAC it drops to a second arc instead,
    so "Happy Birthday" keeps its size and the name stays readable.

    The threshold is a fraction of the card, not an absolute pixel count, so a
    256px card wraps on exactly the same names a 512px card does.
    """
    combined = f"{greeting} {username}"
    size_frac = _fitted_font(combined, img.width * 3).size / (img.width * 3)

    if size_frac >= MIN_TITLE_FRAC:
        draw_arc_text(img, combined, hue_shift=hue_shift)
        return

    line1, box1 = _arc_line(img, greeting, hue_shift=hue_shift)
    line2, box2 = _arc_line(img, username, font_scale=SECOND_LINE_SCALE,
                            hue_shift=hue_shift)

    if box1 is None or box2 is None:
        _safe_paste(img, line1, 0, 0)
        _safe_paste(img, line2, 0, 0)
        return

    dy = _wrap_offset(greeting, username, img.width)
    _safe_paste(img, line1, 0, 0)
    _safe_paste(img, line2, 0, dy)


def draw_arc_text(
    img: Image.Image,
    text: str,
    top_frac: float = TITLE_TOP_FRAC,
    palette=TITLE_PALETTE,
    inner=TITLE_OUTLINE_INNER,
    outer=TITLE_OUTLINE_OUTER,
    stroke_inner: float = TITLE_STROKE_INNER,
    stroke_outer: float = TITLE_STROKE_OUTER,
    supersample: int = 3,
    font_scale: float = 1.0,
    hue_shift: float = 0.0,
) -> None:
    """Set ``text`` along a rainbow arc across the top of ``img``.

    Each glyph is rendered on its own tile, rotated to the arc tangent, then
    pasted. The whole layer is built at ``supersample``x and downsampled at the
    end: per-glyph rotation and integer paste coordinates otherwise leave the
    baseline visibly stepped at 512px.
    """
    size = img.width
    S = size * supersample

    font = _fitted_font(text, S, base_frac=0.108 * font_scale)
    # Stroke widths scale with the type. Fixed pixel strokes swallow the glyphs
    # once a long username forces the font down, which reads as a white blob.
    stroke_w = max(2, round(font.size * stroke_outer))
    w_in = max(1, round(font.size * stroke_inner))
    widths, total, tracking = _layout(text, font, stroke_w)

    radius = S * ARC_RADIUS_FRAC
    cx = S / 2
    apex_y = S * top_frac + font.size * 0.85
    cy = apex_y + radius

    ascent, descent = font.getmetrics()
    pad = stroke_w * 2 + 8 * supersample
    tile_h = ascent + descent + pad

    # Only the top band can hold glyphs, so supersample just that strip: a full
    # S x S layer is ~3x the pixels and the resize dominated the per-frame cost
    # once the title started animating.
    theta_max = min(math.pi * 0.49, (total / 2) / radius)
    lowest = cy - radius * math.cos(theta_max)
    band_h = int(min(S, lowest + tile_h + 4 * supersample))
    band_h = max(16, band_h)
    layer = Image.new("RGBA", (S, band_h), (0, 0, 0, 0))
    # Draw on the baseline, left-aligned at the advance origin (anchor "ls").
    # "ms" would centre on the glyph's ink box instead, which drifts from the
    # advance width and makes the run look skewed as errors accumulate.
    baseline_y = pad / 2 + ascent

    cursor = -total / 2
    drawn = 0
    for ch, w in zip(text, widths):
        if ch.strip():
            theta = (cursor + w / 2) / radius
            x = cx + radius * math.sin(theta)
            y = cy - radius * math.cos(theta)

            # Reordering a fixed palette barely reads on screen, so rotate the
            # hue per frame: CYCLE_FRAMES frames cover a full turn, which makes
            # the loop seamless and the colour change obvious.
            colour = _rotate_hue(palette[drawn % len(palette)], hue_shift)
            drawn += 1

            # tile is advance width + symmetric padding, so its centre IS the
            # advance centre and pasting at (x, y) lands exactly on the arc.
            tile_w = max(8, int(math.ceil(w)) + pad * 2)
            tile_h2 = max(8, tile_h)
            tile = Image.new("RGBA", (tile_w, tile_h2), (0, 0, 0, 0))
            td = ImageDraw.Draw(tile)
            # pass 1: fat dark outline; pass 2: white ring + coloured face.
            # Two passes give the sticker look Pillow's single stroke can't.
            td.text((pad, baseline_y), ch, font=font, fill=outer,
                    stroke_width=stroke_w, stroke_fill=outer, anchor="ls")
            td.text((pad, baseline_y), ch, font=font, fill=colour,
                    stroke_width=w_in, stroke_fill=inner, anchor="ls")
            tile = tile.rotate(-math.degrees(theta), resample=ROTATE_RESAMPLE, expand=True)
            _safe_paste(layer, tile,
                        int(x - tile.width / 2), int(y - tile.height / 2))
        cursor += w + tracking

    img.alpha_composite(
        layer.resize((size, max(1, round(band_h / supersample))), RESAMPLE)
    )


# --- Card assembly ----------------------------------------------------------


def _cake_shadow(cake: Image.Image, size: int, offset=(0, 5)) -> Image.Image:
    """Blurred silhouette halo that separates the cake from the PFP.

    A pure drop shadow is useless here because the cake is pinned to the bottom
    edge, so anything cast downward falls outside the frame. A near-symmetric
    halo darkens the PFP just around the cake's silhouette instead, which is
    what actually reads as depth.
    """
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    alpha = cake.getchannel("A").point(lambda v: int(v * 0.80))
    blob = Image.new("RGBA", cake.size, (0, 0, 0, 0))
    blob.putalpha(alpha)
    shadow.alpha_composite(blob, (offset[0], offset[1]))
    return shadow.filter(ImageFilter.GaussianBlur(max(8, size // 38)))


def _cake_glow(cake_w: int, top_y: int, size: int) -> Image.Image:
    """Warm halo behind the visible part of the cake, as if the candles light it.

    A dark silhouette shadow is invisible on a dark PFP (and a light one on a
    light PFP). A warm glow shows on both, and sells the cake as a light source
    standing in front of the person rather than a pasted sticker.
    """
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    w = int(cake_w * 1.25)
    h = max(64, int((size - top_y) * 2.1))
    x = (size - w) // 2
    y = size - h
    ImageDraw.Draw(glow).ellipse([x, y, x + w, y + h], fill=(255, 186, 108, 58))
    return glow.filter(ImageFilter.GaussianBlur(max(12, size // 22)))


def render_card(
    pfp: Image.Image,
    username: str,
    size: int = CARD_SIZE,
    cake_path: str | Path | None = None,
    title: str | None = None,
    debug_safe_line: bool = False,
    hue_shift: float = 0.0,
    draw_text: bool = True,
) -> Image.Image:
    """Composite one birthday card frame."""
    card = fit_square(pfp, size)
    if ADD_SCRIM:
        card.alpha_composite(_scrim(size))

    base_w = int(size * CAKE_WIDTH_FRAC)
    asset = Path(cake_path) if cake_path else pick_food()
    if asset is not None and asset.exists():
        cake = _sprite_for(str(asset), asset.stat().st_mtime, base_w)
    else:
        cake = cake_sprite(base_w)
    cake = fit_cake(size, cake)

    x, y = cake_position(size, cake.width, cake.height)

    if ADD_GLOW:
        card.alpha_composite(_cake_glow(cake.width, y, size))
    if ADD_SHADOW:
        card.alpha_composite(_cake_shadow(cake, size), (x, y))
    card.alpha_composite(cake, (x, y))

    if draw_text:
        if title:
            draw_arc_text(card, title, hue_shift=hue_shift)
        else:
            draw_title(card, "Happy Birthday", username, hue_shift=hue_shift)

    if debug_safe_line:
        d = ImageDraw.Draw(card)
        band = int(size * FACE_SAFE_TOP)
        d.line([(0, band), (size, band)], fill=(255, 64, 64, 200), width=2)

    return card


# --- I/O --------------------------------------------------------------------


def _frame_durations(src: Image.Image, count: int) -> list[int]:
    durations = []
    for i in range(count):
        src.seek(i)
        durations.append(int(src.info.get("duration", 80)) or 80)
    return durations


def _tick_size(base: int) -> int:
    """Finest exact tick, but never coarser than MIN_TEXT_FPS allows.

    A 200ms frame is fine for a slide show and awful for moving text: the colour
    would jump 120 degrees per step. Subdividing it into 50ms ticks adds frames
    without touching the picture, because the same pose simply repeats.
    """
    if base <= MAX_TICK_MS:
        return base
    for div in range(int(MAX_TICK_MS), 0, -1):
        if base % div == 0:
            return div
    return base


def _uniform_plan(durations: list[int]) -> tuple[list[int], int]:
    """Resample variable frame timings onto a constant interval.

    Source GIFs mix frame lengths: a pose held for 120ms next to 30ms frames.
    That makes any per-frame animation uneven, because a held frame samples one
    step and then sits still. Duplicating each frame into whole ticks fixes it:
    the picture is unchanged (a hold is still the same pose for its full length)
    but the title can advance one tick at a time throughout.

    Returns (source index per output frame, tick length in ms).
    """
    if not durations:
        return [], 0

    total = sum(durations)
    # Indices back into the original frame list; subsampling below rewrites them.
    origin = list(range(len(durations)))
    subsampled = len(durations) > MAX_ANIM_FRAMES
    if subsampled:
        # More source frames than we would ever emit: thin them out first, which
        # is where a very long GIF starts approximating rather than exact.
        step = len(durations) / MAX_ANIM_FRAMES
        keep = [int(i * step) for i in range(MAX_ANIM_FRAMES)]
        durations = [durations[i] for i in keep]
        origin = keep

    base = reduce(gcd, durations) or UNIFORM_MIN_MS
    tick = _tick_size(base)
    counts = [max(1, d // tick) for d in durations]

    # Too many ticks: coarsen onto a multiple of the base that still divides
    # every frame, so the total stays exact.
    mult = 1
    while sum(counts) > MAX_ANIM_FRAMES and base * (mult + 1) <= max(durations):
        mult += 1
        cand = base * mult
        if all(d % cand == 0 for d in durations):
            tick = cand
            counts = [max(1, d // cand) for d in durations]

    plan = [i for i, c in enumerate(counts) for _ in range(c)]

    if len(plan) > MAX_ANIM_FRAMES:
        # Last resort for pathological sources: thin the ticks themselves and
        # stretch the tick to keep the loop the same length.
        step = len(plan) / MAX_ANIM_FRAMES
        plan = [plan[int(i * step)] for i in range(MAX_ANIM_FRAMES)]
        subsampled = True

    if subsampled or len(plan) * tick != total:
        # Rescale the tick so the whole loop keeps its original length.
        tick = max(1, round(total / max(1, len(plan))))

    return [origin[i] for i in plan], tick


def _hue_schedule(durations: list[int]) -> list[float]:
    """Hue in degrees for each frame, derived from wall-clock time.

    One palette step per frame makes the cycle speed depend on the source GIF's
    frame rate: 40ms frames strobe through a full rainbow in a quarter second
    while 100ms frames crawl. Timing against COLOUR_PERIOD_MS instead keeps the
    cycle the same speed on any PFP.

    The number of turns is rounded to a whole number so the palette returns to
    its starting hue at the end of the loop; otherwise every repeat jumps.
    """
    total = sum(durations) or COLOUR_PERIOD_MS
    turns = max(1, round(total / COLOUR_PERIOD_MS))
    period = total / turns
    hues, elapsed = [], 0.0
    for d in durations:
        hues.append(360.0 * (elapsed / period))
        elapsed += d
    return hues


def _build_frames(
    src: Image.Image,
    username: str,
    size: int,
    asset: Path | None,
    debug_safe_line: bool = False,
) -> tuple[list[Image.Image], list[int]]:
    """Render every output frame of a card, in memory.

    Shared by the file and bytes entry points so a caller that only needs to
    upload the image never touches the filesystem.
    """
    frames = getattr(src, "n_frames", 1)
    animated = bool(getattr(src, "is_animated", False)) and frames > 1

    if not animated and not COLOUR_CYCLE:
        return [render_card(src, username, size=size, cake_path=asset,
                            debug_safe_line=debug_safe_line).convert("RGB")], []

    if animated:
        durations = _frame_durations(src, frames)
        if UNIFORM_FRAMES:
            # Holds become repeated frames on one grid, so timing is preserved
            # and the shimmer advances evenly instead of stalling on a hold.
            plan, tick = _uniform_plan(durations)
            sources = plan
            out_durations = [tick] * len(plan)
        else:
            # Evenly sample if the GIF is long, keeping the loop intact.
            indices = list(range(frames))
            if frames > MAX_ANIM_FRAMES:
                step = frames / MAX_ANIM_FRAMES
                indices = [int(i * step) for i in range(MAX_ANIM_FRAMES)]
            sources = indices
            out_durations = [durations[i] for i in indices]
    else:
        # Static PFP: loop the title colours instead of the PFP. Same grid rule,
        # so the text never animates slower than MIN_TEXT_FPS.
        plan, tick = _uniform_plan([CYCLE_MS] * CYCLE_FRAMES)
        sources = plan
        out_durations = [tick] * len(plan)

    hues = _hue_schedule(out_durations)

    rgb_frames: list[Image.Image] = []
    if animated:
        # A duplicated frame is the same picture, so composite its base once and
        # only redraw the title per tick.
        last_src: int | None = None
        cached_base: Image.Image | None = None
        for src_index, hue in zip(sources, hues):
            if cached_base is None or src_index != last_src:
                src.seek(src_index)
                cached_base = render_card(
                    src, username, size=size, cake_path=asset,
                    debug_safe_line=debug_safe_line, draw_text=False,
                )
                last_src = src_index
            frame = cached_base.copy()
            draw_title(frame, "Happy Birthday", username, hue_shift=hue)
            rgb_frames.append(frame.convert("RGB"))
    else:
        # The PFP and cupcake are identical in every frame, so composite the
        # base once and only redraw the shimmering title per frame.
        base = render_card(src, username, size=size, cake_path=asset,
                           debug_safe_line=debug_safe_line, draw_text=False)
        for hue in hues:
            frame = base.copy()
            draw_title(frame, "Happy Birthday", username, hue_shift=hue)
            rgb_frames.append(frame.convert("RGB"))

    return rgb_frames, out_durations


def _save_webp(frames: list[Image.Image], durations: list[int], out) -> None:
    """Write frames as (possibly animated) WebP to a path or file object."""
    if len(frames) == 1:
        frames[0].save(out, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
        return
    frames[0].save(
        out, "WEBP", save_all=True, append_images=frames[1:],
        duration=durations, loop=0, quality=WEBP_QUALITY, method=WEBP_METHOD,
    )


def render_file(
    pfp_path: str | Path,
    username: str,
    out_path: str | Path,
    size: int = CARD_SIZE,
    cake_path: str | Path | None = None,
    debug_safe_line: bool = False,
) -> Path:
    """Render to disk as WebP, preserving PFP animation."""
    src = Image.open(pfp_path)
    out_path = Path(out_path).with_suffix(".webp")

    # Resolve the decoration ONCE for the whole card so every frame of an
    # animated PFP shows the same cupcake.
    asset = Path(cake_path) if cake_path else pick_food()

    frames, durations = _build_frames(src, username, size, asset, debug_safe_line)
    _save_webp(frames, durations, out_path)
    return out_path


def render_bytes(
    pfp_bytes: bytes,
    username: str,
    size: int = CARD_SIZE,
    cake_path: str | Path | None = None,
) -> tuple[bytes, str]:
    """Render from raw PFP bytes entirely in memory.

    Returns (payload, extension). Nothing is written to disk: the birthday post
    generates the card, uploads it, and lets it go, so no card ever outlives the
    message it was made for.
    """
    src = Image.open(io.BytesIO(pfp_bytes))
    asset = Path(cake_path) if cake_path else pick_food()

    frames, durations = _build_frames(src, username, size, asset)
    buf = io.BytesIO()
    _save_webp(frames, durations, buf)
    return buf.getvalue(), ".webp"
