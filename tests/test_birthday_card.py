"""Tests for the birthday card renderer.

The important one is the placement rule: the cake may never rise above
FACE_SAFE_TOP, because that is the only thing protecting the face (there is no
face detection by design).
"""
import datetime

import pytest
from PIL import Image, ImageChops

import birthday_card as bc


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def solid_pfp(colour=(40, 90, 160, 255), size=256):
    return Image.new("RGBA", (size, size), colour)


def gradient_pfp(size=256):
    im = Image.new("RGBA", (size, size))
    px = im.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (x * 255 // size, y * 255 // size, 128, 255)
    return im


def write_gif(path, frames=3, size=64, duration=70):
    imgs = []
    for i in range(frames):
        im = Image.new("RGB", (size, size), (10 + i * 40, 60, 200 - i * 30))
        imgs.append(im.convert("P", palette=Image.Palette.ADAPTIVE))
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=duration, loop=0, disposal=2)
    return path


# ------------------------------------------------------------------
# The placement rule
# ------------------------------------------------------------------

@pytest.mark.parametrize("size", [128, 256, 512])
def test_decoration_never_rises_above_the_face_safe_line(size):
    """The decoration's top edge must stay below the band, whatever the art."""
    for sprite_path in [*bc.cupcake_assets(), bc.DEFAULT_CAKE_ASSET]:
        cake = bc.fit_cake(size, bc.load_cake_sprite(sprite_path, 256))
        _, y = bc.cake_position(size, cake.width, cake.height)
        assert y >= int(size * bc.FACE_SAFE_TOP)


@pytest.mark.parametrize("size", [128, 256, 512])
def test_decoration_is_mostly_in_frame(size):
    """Mostly visible, with only part of the bottom edge clipped."""
    for sprite_path in [*bc.cupcake_assets(), bc.DEFAULT_CAKE_ASSET]:
        cake = bc.fit_cake(size, bc.load_cake_sprite(sprite_path, 256))
        _, y = bc.cake_position(size, cake.width, cake.height)
        visible = size - y
        frac = visible / cake.height
        assert 0.70 <= frac <= 1.0
        # ... and it never floats above the bottom edge
        assert y + cake.height >= size


@pytest.mark.parametrize("size", [128, 256, 512])
def test_decoration_sits_in_the_left_corner(size):
    sprite = bc.load_cake_sprite(bc.cupcake_assets()[0], 256)
    cake = bc.fit_cake(size, sprite)
    x, _ = bc.cake_position(size, cake.width, cake.height)
    assert x == int(size * bc.CAKE_MARGIN_X)
    assert x < (size - cake.width) // 2


def test_cake_position_never_leaves_the_frame():
    size = 512
    x, _ = bc.cake_position(size, 400, 100)   # wide sprite
    assert 0 <= x <= size - 400
    x2, _ = bc.cake_position(size, size, 100)
    assert x2 == 0


def test_fit_cake_targets_the_visible_fraction():
    size = 512
    sprite = bc.load_cake_sprite(bc.DEFAULT_CAKE_ASSET, 256)
    cake = bc.fit_cake(size, sprite)
    budget = size - int(size * bc.FACE_SAFE_TOP)
    assert abs(cake.height - budget / bc.CAKE_VISIBLE_FRAC) <= 1


def test_no_vignette_or_scrim_by_default():
    """The edge-darkening gradients were removed on request."""
    assert bc.ADD_SCRIM is False
    card = bc.render_card(solid_pfp((200, 200, 200, 255)), "al", size=256)
    # bottom-left corner is PFP only; a scrim would darken it
    r, g, b, _ = card.getpixel((2, 253))
    assert r > 180 and g > 180 and b > 180


# ------------------------------------------------------------------
# Composition
# ------------------------------------------------------------------

@pytest.mark.parametrize("size", [128, 256])
def test_render_card_returns_square_rgba(size):
    card = bc.render_card(solid_pfp(), "alice", size=size)
    assert card.size == (size, size)
    assert card.mode == "RGBA"


def test_render_card_works_on_non_square_pfp():
    wide = Image.new("RGBA", (400, 200), (200, 30, 30, 255))
    card = bc.render_card(wide, "alice", size=128)
    assert card.size == (128, 128)


def test_fit_square_centre_crops():
    wide = Image.new("RGBA", (400, 200), (0, 0, 0, 255))
    out = bc.fit_square(wide, 100)
    assert out.size == (100, 100)


def test_render_card_draws_title_ink_in_the_top_band():
    card = bc.render_card(solid_pfp((20, 20, 20, 255)), "alice", size=256)
    top = card.crop((0, 0, 256, int(256 * 0.30))).convert("RGB")
    colours = {c for _, c in top.getcolors(maxcolors=1 << 20)}
    # title is rainbow coloured + white outline, so the band is far from plain
    assert len(colours) > 20


def test_long_username_does_not_raise_and_stays_in_frame():
    card = bc.render_card(solid_pfp(), "everygoddamnusernameistaken", size=256)
    assert card.size == (256, 256)


def test_draw_arc_text_handles_empty_and_spaces():
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 255))
    bc.draw_arc_text(img, "     ")
    assert img.size == (128, 128)


# ------------------------------------------------------------------
# Asset handling
# ------------------------------------------------------------------

def test_custom_cake_path_is_used(tmp_path):
    custom = tmp_path / "cake.png"
    Image.new("RGBA", (100, 60), (0, 255, 0, 255)).save(custom)
    sprite = bc.load_cake_sprite(custom, 200)
    assert sprite.width == 200
    assert sprite.height == 120


def test_missing_asset_falls_back_to_the_drawn_cake(tmp_path):
    card = bc.render_card(solid_pfp(), "alice", size=128,
                          cake_path=tmp_path / "nope.png")
    assert card.size == (128, 128)


def test_load_cake_sprite_trims_empty_border(tmp_path):
    padded = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    padded.paste(Image.new("RGBA", (100, 50), (255, 0, 0, 255)), (50, 75))
    p = tmp_path / "padded.png"
    padded.save(p)
    sprite = bc.load_cake_sprite(p, 100)
    assert sprite.width == 100
    assert sprite.height == 50


# ------------------------------------------------------------------
# I/O: static vs animated
# ------------------------------------------------------------------

def test_render_file_writes_a_still_webp_when_cycling_is_off(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "COLOUR_CYCLE", False)
    pfp = tmp_path / "pfp.png"
    solid_pfp().save(pfp)
    out = bc.render_file(pfp, "alice", tmp_path / "card.png", size=128)
    assert out.exists()
    im = Image.open(out)
    assert not getattr(im, "is_animated", False)
    assert im.size == (128, 128)


def test_static_pfp_gets_a_looping_webp_when_colours_cycle(tmp_path):
    pfp = tmp_path / "pfp.png"
    solid_pfp().save(pfp)
    out = bc.render_file(pfp, "alice", tmp_path / "card.gif", size=128)
    im = Image.open(out)
    assert getattr(im, "is_animated", False) is True
    plan, tick = bc._uniform_plan([bc.CYCLE_MS] * bc.CYCLE_FRAMES)
    assert im.n_frames == len(plan)
    assert sum(anmf_durations(out)) == bc.CYCLE_MS * bc.CYCLE_FRAMES
    assert anmf_durations(out) == [tick] * len(plan)
    assert im.info.get("loop") == 0


def anmf_durations(path):
    """Per-frame timings straight out of the WebP ANMF chunks.

    Pillow does not expose animated-WebP frame durations on read, so read the
    container: after "ANMF" comes a 4-byte size, then X/Y/W/H (3 bytes each),
    then a 24-bit duration in milliseconds.
    """
    data = open(path, "rb").read()
    out, i = [], 0
    while True:
        j = data.find(b"ANMF", i)
        if j < 0:
            return out
        out.append(int.from_bytes(data[j + 8 + 12: j + 8 + 15], "little"))
        i = j + 8


def test_render_file_preserves_pfp_frame_timing(tmp_path):
    pfp = write_gif(tmp_path / "pfp.gif", frames=3, duration=70)
    out = bc.render_file(pfp, "alice", tmp_path / "card.gif", size=128)
    im = Image.open(out)
    assert getattr(im, "is_animated", False) is True
    assert out.suffix == ".webp"
    durs = anmf_durations(out)
    # 70ms is slower than MIN_TEXT_FPS allows, so it is subdivided into ticks,
    # but the total must be untouched.
    assert len(set(durs)) == 1
    assert sum(durs) == 210
    assert im.n_frames == len(durs)


def test_cycle_frame_count_divides_the_palette_so_the_loop_is_seamless():
    assert bc.CYCLE_FRAMES % len(bc.TITLE_PALETTE) == 0


def test_animated_frames_are_not_identical(tmp_path):
    """If every output frame matched, the animation was lost in composition."""
    pfp = write_gif(tmp_path / "pfp.gif", frames=3, size=64)
    out = bc.render_file(pfp, "alice", tmp_path / "card.gif", size=128)
    im = Image.open(out)
    im.seek(0)
    first = im.convert("RGB").copy()
    im.seek(1)
    second = im.convert("RGB")
    assert first.tobytes() != second.tobytes()


def test_animated_frame_cap_is_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "MAX_ANIM_FRAMES", 4)
    pfp = write_gif(tmp_path / "pfp.gif", frames=10, size=32)
    out = bc.render_file(pfp, "alice", tmp_path / "card.gif", size=96)
    assert Image.open(out).n_frames == 4


def test_render_bytes_returns_webp_for_static_when_cycling():
    import io
    buf = io.BytesIO()
    solid_pfp().save(buf, format="PNG")
    payload, ext = bc.render_bytes(buf.getvalue(), "alice", size=96)
    assert ext == ".webp"
    assert Image.open(io.BytesIO(payload)).format == "WEBP"
    assert getattr(Image.open(io.BytesIO(payload)), "is_animated", False)


def test_render_bytes_returns_still_webp_for_static_when_cycling_is_off(monkeypatch):
    import io
    monkeypatch.setattr(bc, "COLOUR_CYCLE", False)
    buf = io.BytesIO()
    solid_pfp().save(buf, format="PNG")
    payload, ext = bc.render_bytes(buf.getvalue(), "alice", size=96)
    assert ext == ".webp"
    still = Image.open(io.BytesIO(payload))
    assert still.format == "WEBP"
    assert still.size == (96, 96)
    assert not getattr(still, "is_animated", False)


def test_render_bytes_returns_webp_for_animated(tmp_path):
    pfp = write_gif(tmp_path / "p.gif", frames=2, size=32)
    payload, ext = bc.render_bytes(pfp.read_bytes(), "alice", size=96)
    assert ext == ".webp"
    assert getattr(Image.open(__import__("io").BytesIO(payload)), "is_animated", False)


# ------------------------------------------------------------------
# Random cupcake selection
#
# The shipped asset is a 2x2 grid: four cupcakes, one file each. One is picked
# per card, and the pick must NOT be re-rolled per animated frame.
# ------------------------------------------------------------------

def test_cupcakes_are_available():
    assets = bc.cupcake_assets()
    assert len(assets) >= 4, [p.name for p in assets]
    for p in assets:
        assert p.suffix == ".png"


def test_pick_food_returns_a_cupcake():
    import random
    rng = random.Random(1)
    picks = {bc.pick_food(rng) for _ in range(40)}
    assert picks
    assert picks.issubset(set(bc.cupcake_assets()))


def test_pick_food_is_random_across_the_set():
    import random
    rng = random.Random(7)
    picks = {bc.pick_food(rng) for _ in range(200)}
    assert len(picks) == len(bc.cupcake_assets())


def test_pick_food_falls_back_to_cake_without_cupcakes(monkeypatch, tmp_path):
    monkeypatch.setattr(bc, "CUPCAKE_DIR", tmp_path / "empty")
    assert bc.pick_food() == bc.DEFAULT_CAKE_ASSET


def test_food_is_chosen_once_per_card(tmp_path, monkeypatch):
    """An animated card must not re-roll the cupcake for every frame."""
    calls = []
    real = bc.pick_food

    def spy(rng=None):
        calls.append(1)
        return real(rng)

    monkeypatch.setattr(bc, "pick_food", spy)
    pfp = write_gif(tmp_path / "pfp.gif", frames=4, size=32)
    bc.render_file(pfp, "alice", tmp_path / "card.gif", size=96)
    assert len(calls) == 1


def test_animated_card_keeps_the_same_cupcake_on_every_frame(tmp_path):
    """The decoration region must be identical across frames, or it flickers."""
    from PIL import ImageChops

    # Pin the decoration, otherwise this test picks a different cupcake than
    # the card did and compares two unrelated sprites.
    fixed = bc.cupcake_assets()[0]
    pfp = write_gif(tmp_path / "pfp.gif", frames=3, size=64)
    out = bc.render_file(pfp, "alice", tmp_path / "card.gif", size=128,
                         cake_path=fixed)

    base_w = int(128 * bc.CAKE_WIDTH_FRAC)
    sprite = bc.fit_cake(128, bc._sprite_for(str(fixed), 0, base_w))
    x, y = bc.cake_position(128, sprite.width, sprite.height)
    box = (x, y, x + sprite.width, y + sprite.height)
    opaque = sprite.getchannel("A").point(lambda v: 255 if v > 200 else 0)

    im = Image.open(out)
    im.seek(0)
    prev = im.convert("RGB").crop(box)
    for i in range(1, im.n_frames):
        im.seek(i)
        cur = im.convert("RGB").crop(box)
        delta = ImageChops.multiply(
            ImageChops.difference(prev, cur).convert("L"), opaque)
        assert delta.getextrema()[1] <= 40, f"frame {i} decoration changed"


def test_cupcakes_get_no_candle_by_default(monkeypatch):
    """ADD_CANDLE is off: the shipped cupcakes are used bare."""
    monkeypatch.setattr(bc, "CAKE_ANGLE", 0.0)  # isolate the candle from the tilt
    bc._sprite_for.cache_clear()
    path = bc.cupcake_assets()[0]
    raw = bc.load_cake_sprite(path, 200)
    sprite = bc._sprite_for(str(path), 0, 200)
    assert bc.ADD_CANDLE is False
    assert sprite.height == raw.height


def test_candle_can_be_switched_back_on(monkeypatch):
    """The candle code still works when ADD_CANDLE is enabled."""
    monkeypatch.setattr(bc, "CAKE_ANGLE", 0.0)
    path = bc.cupcake_assets()[0]
    raw = bc.load_cake_sprite(path, 200)
    monkeypatch.setattr(bc, "ADD_CANDLE", True)
    bc._sprite_for.cache_clear()
    sprite = bc._sprite_for(str(path), 0, 200)
    assert sprite.width == raw.width
    assert sprite.height >= raw.height


def test_no_shadow_or_glow_by_default():
    """Shadow and glow were removed on request; keep them off."""
    assert bc.ADD_SHADOW is False
    assert bc.ADD_GLOW is False


def test_frosting_top_finds_the_mass_not_the_topper():
    """The candle insertion point must be the frosting, not the topper."""
    path = bc.cupcake_assets()[0]
    sprite = bc.load_cake_sprite(path, 200)
    y = bc._frosting_top(sprite)
    assert 0 < y < sprite.height * 0.8



# ------------------------------------------------------------------
# Title wrapping
#
# A long username on one arc forces the type down to ~16px at 512. Past
# MIN_TITLE_PX it must wrap to a second arc rather than shrink to nothing.
# ------------------------------------------------------------------

def test_short_username_uses_a_single_arc(monkeypatch):
    calls = []
    monkeypatch.setattr(bc, "draw_arc_text",
                        lambda img, text, **kw: calls.append(text))
    img = Image.new("RGBA", (256, 256), (10, 10, 10, 255))
    bc.draw_title(img, "Happy Birthday", "cd3333")
    assert calls == ["Happy Birthday cd3333"]


def test_long_username_wraps_to_a_second_arc(monkeypatch):
    calls = []
    monkeypatch.setattr(bc, "draw_arc_text",
                        lambda img, text, **kw: calls.append((text, kw)))
    img = Image.new("RGBA", (256, 256), (10, 10, 10, 255))
    bc.draw_title(img, "Happy Birthday", "everygoddamnusernameistaken")
    assert [c[0] for c in calls] == ["Happy Birthday", "everygoddamnusernameistaken"]
    assert calls[1][1].get("font_scale") == bc.SECOND_LINE_SCALE


def test_wrapped_lines_stay_above_the_readable_floor():
    long_name = "everygoddamnusernameistaken"
    scale = 512 * 3
    combined = bc._fitted_font(f"Happy Birthday {long_name}", scale).size / scale
    assert combined < bc.MIN_TITLE_FRAC  # this is why it wraps

    line1 = bc._fitted_font("Happy Birthday", scale).size / scale
    line2 = bc._fitted_font(long_name, scale,
                            base_frac=0.108 * bc.SECOND_LINE_SCALE).size / scale
    assert line1 >= bc.MIN_TITLE_FRAC
    assert line2 >= bc.MIN_TITLE_FRAC


# ------------------------------------------------------------------
# Title colour cycling
# ------------------------------------------------------------------

def test_palette_phase_shifts_the_title_colours():
    img_a = Image.new("RGBA", (256, 256), (10, 10, 10, 255))
    img_b = Image.new("RGBA", (256, 256), (10, 10, 10, 255))
    bc.draw_arc_text(img_a, "Happy Birthday", hue_shift=0.0)
    bc.draw_arc_text(img_b, "Happy Birthday", hue_shift=60.0)

    title_box = (0, 0, 256, int(256 * 0.20))
    diff = ImageChops.difference(img_a.convert("RGB").crop(title_box),
                                 img_b.convert("RGB").crop(title_box))
    assert diff.getbbox() is not None  # a different phase paints different hues


def test_cycling_frames_actually_differ(tmp_path):
    pfp = tmp_path / "pfp.png"
    solid_pfp().save(pfp)
    out = bc.render_file(pfp, "alice", tmp_path / "card.gif", size=128)
    im = Image.open(out)
    frames = []
    for i in range(im.n_frames):
        im.seek(i)
        frames.append(im.convert("RGB").copy())
    assert any(
        ImageChops.difference(frames[0], frames[i]).getbbox() is not None
        for i in range(1, len(frames))
    )


def _mean_title_colour(img, size=512):
    band = img.convert("RGB").crop((0, 0, size, int(size * 0.21)))
    lit = [c for c in band.get_flattened_data() if sum(c) > 420]
    return tuple(sum(c[i] for c in lit) / len(lit) for i in range(3))


def test_hue_actually_rotates_between_frames():
    """Reordering a fixed palette is invisible; the hue must genuinely move."""
    means = []
    for step in range(bc.CYCLE_FRAMES):
        img = Image.new("RGBA", (512, 512), (20, 20, 26, 255))
        bc.draw_title(img, "Happy Birthday", "sleepnow2",
                      hue_shift=360.0 * step / bc.CYCLE_FRAMES)
        means.append(_mean_title_colour(img))

    deltas = [
        max(abs(a - b) for a, b in zip(means[i], means[i + 1]))
        for i in range(len(means) - 1)
    ]
    assert min(deltas) > 10, means


def test_hue_rotation_returns_to_the_start_for_a_seamless_loop():
    first = _rotate = bc._rotate_hue((92, 178, 255, 255), 0)
    full = bc._rotate_hue((92, 178, 255, 255), 360)
    assert first == full


# ------------------------------------------------------------------
# Hue speed follows wall-clock time, not frame count
# ------------------------------------------------------------------

def test_hue_schedule_advances_with_elapsed_time_not_frames():
    """A 40ms-per-frame GIF must not strobe just because it has more frames."""
    fast = bc._hue_schedule([40] * 10)      # 400ms total
    slow = bc._hue_schedule([100] * 4)      # 400ms total
    assert len(fast) == 10 and len(slow) == 4
    # Both reach the same hue at the same wall-clock moment.
    assert abs(fast[0]) < 1e-9 and abs(slow[0]) < 1e-9
    # More frames spread the same turn over finer steps, so the final frame sits
    # closer to a complete turn.
    assert fast[-1] > slow[-1]


def test_hue_schedule_returns_to_the_start_at_loop_end():
    for durations in ([70, 70, 70], [40] * 33, [110] * 6, [100, 200, 50]):
        hues = bc._hue_schedule(durations)
        total = sum(durations)
        # the last frame's step, advanced by its own duration, wraps to 0
        turns = max(1, round(total / bc.COLOUR_PERIOD_MS))
        period = total / turns
        assert abs(((hues[-1] + 360.0 * durations[-1] / period) % 360.0)) < 1e-6


# ------------------------------------------------------------------
# Uniform frame grid (holds duplicated into ticks)
# ------------------------------------------------------------------

def test_uniform_plan_duplicates_holds_without_losing_time():
    durations = [120] * 4 + [30] * 44          # 480 + 1320 = 1800ms
    plan, tick = bc._uniform_plan(durations)
    assert tick == 30
    assert len(plan) * tick == sum(durations)
    # each source frame appears exactly duration/tick times
    for idx, d in enumerate(durations):
        assert plan.count(idx) == d // tick


def test_uniform_plan_leaves_an_already_uniform_gif_alone():
    durations = [60] * 33
    plan, tick = bc._uniform_plan(durations)
    assert tick == 60
    assert plan == list(range(33))


def test_uniform_plan_keeps_total_time_for_irregular_timings():
    durations = [100, 30, 170]
    plan, tick = bc._uniform_plan(durations)
    assert len(plan) * tick == sum(durations)


def test_uniform_plan_respects_the_frame_cap():
    # 300 frames of 10ms each: must not emit 300 frames, and must stay near the
    # original 3000ms total (subsampling this far is approximate by nature).
    durations = [10] * 300
    plan, tick = bc._uniform_plan(durations)
    assert len(plan) <= bc.MAX_ANIM_FRAMES
    assert abs(len(plan) * tick - sum(durations)) <= sum(durations) * 0.05


# ------------------------------------------------------------------
# Minimum text frame rate
# ------------------------------------------------------------------

def test_slow_gif_is_subdivided_so_text_does_not_jerk():
    """3 frames at 200ms would step the colour 120 degrees at a time."""
    plan, tick = bc._uniform_plan([200, 200, 200])
    assert tick <= bc.MAX_TICK_MS
    assert len(plan) == 12
    assert len(plan) * tick == 600
    assert len({plan.count(i) for i in set(plan)}) == 1


def test_tick_never_exceeds_the_minimum_fps():
    for durations in ([200] * 3, [110] * 6, [500] * 2, [70] * 3):
        _, tick = bc._uniform_plan(durations)
        assert tick <= bc.MAX_TICK_MS or sum(durations) < bc.MAX_TICK_MS


def test_wrapped_lines_are_separated_but_tight():
    """Regression, both directions: line 2 first tucked itself behind line 1,
    then the fix over-corrected into a gap wide enough to read as a hole.

    Row-band scanning cannot judge this, because an arc leaves ink in most rows
    somewhere across the width. Measure column by column instead.
    """
    greeting, name = "Happy Birthday", "everygoddamnusernameistaken"
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    line1, _ = bc._arc_line(canvas, greeting)
    line2, _ = bc._arc_line(canvas, name, font_scale=bc.SECOND_LINE_SCALE)
    e1 = bc._column_extents(line1)
    e2 = bc._column_extents(line2)
    dy = bc._wrap_offset(greeting, name, 512)

    gaps = [(e2[x][0] + dy) - e1[x][1] for x in set(e1) & set(e2)]
    assert gaps, "no shared columns to measure"
    assert min(gaps) >= 2, f"lines collide: {min(gaps)}px"
    assert min(gaps) <= 0.03 * 512, f"gap too wide: {min(gaps)}px"


def test_render_bytes_never_touches_the_filesystem(tmp_path, monkeypatch):
    """Cards are generated for a post and dropped; nothing is stored."""
    import io
    import tempfile as _tempfile

    monkeypatch.setattr(_tempfile, "tempdir", str(tmp_path))
    before = set(tmp_path.rglob("*"))

    buf = io.BytesIO()
    solid_pfp().save(buf, format="PNG")
    payload, ext = bc.render_bytes(buf.getvalue(), "alice", size=96)

    assert ext == ".webp" and payload
    after = set(tmp_path.rglob("*"))
    assert after == before, f"render_bytes left files behind: {after - before}"
