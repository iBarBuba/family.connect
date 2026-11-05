#!/usr/bin/env python3
"""Draw the two subscription images App Store Connect takes (1024x1024).

    python3 ios/scripts/make-subscription-images.py

Writes ios/docs/subscription/promo-monthly.png and promo-yearly.png: the app
icon's blue, a white house holding the icon's family (the subscription
screen's own "house" — Host Your Family), and a calendar that tells the two
apart without a word: ONE month on the monthly, TWELVE on the yearly. No
text, no price and no period in figures, because App Store Connect shows the
display name and the price beside the image, in the customer's language.

Square, full bleed, RGB with no alpha channel: Apple masks the corners itself
and refuses an image with transparency. Needs Pillow.
"""
import pathlib

from PIL import Image, ImageChops, ImageDraw

SIZE = 1024
SCALE = 4  # drawn at 4096 and scaled down, for clean edges
S = SIZE * SCALE

# Sampled from AppIcon.png: the top and bottom of its gradient.
TOP = (0x09, 0x5C, 0xB0)
BOTTOM = (0x0B, 0x4E, 0x9C)
WHITE = (255, 255, 255)

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "subscription"


def px(v: float) -> int:
    return round(v * SCALE)


def gradient() -> Image.Image:
    column = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        column.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    return column.resize((S, S))


def rounded_polygon(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]],
                    radius: float, fill) -> None:
    """A CONVEX polygon with every corner rounded to `radius`, exactly: the
    polygon moved in by the radius, then swept by a disc of it."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
    sign = 1 if area > 0 else -1
    lines = []
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        nx, ny = -dy / length * sign, dx / length * sign  # inward
        lines.append(((x0 + nx * radius, y0 + ny * radius), (dx, dy)))
    inner = []
    for (a, da), (b, db) in zip(lines[-1:] + lines[:-1], lines):
        # Where the moved edge before this corner meets the moved edge after it.
        cross = da[0] * db[1] - da[1] * db[0]
        t = ((b[0] - a[0]) * db[1] - (b[1] - a[1]) * db[0]) / cross
        inner.append((a[0] + da[0] * t, a[1] + da[1] * t))
    draw.polygon([(px(x), px(y)) for x, y in inner], fill=fill)
    # Each edge's band, as an exact quadrilateral: a thick line's ends do not
    # meet the corner discs cleanly.
    for (x0, y0), (x1, y1) in zip(inner, inner[1:] + inner[:1]):
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        nx, ny = dy / length * sign * radius, -dx / length * sign * radius  # outward
        draw.polygon([(px(x0), px(y0)), (px(x1), px(y1)),
                      (px(x1 + nx), px(y1 + ny)), (px(x0 + nx), px(y0 + ny))], fill=fill)
    for x, y in inner:
        draw.ellipse([px(x - radius), px(y - radius), px(x + radius), px(y + radius)], fill=fill)


# The house: walls 150-754, eaves at 420, the ridge at (452, 150), floor 820.
HOUSE = [(150, 820), (150, 420), (452, 150), (754, 420), (754, 820)]
CHIMNEY = (612, 196, 688, 360)
# The calendar, over the house's lower right corner, and its two rings.
BADGE = (680, 640, 940, 900)
RINGS = [(BADGE[0] + 74, BADGE[1] - 24, BADGE[0] + 74 + 24, BADGE[1] + 28),
         (BADGE[2] - 74 - 24, BADGE[1] - 24, BADGE[2] - 74, BADGE[1] + 28)]
GAP = 16


def house_mask() -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    rounded_polygon(d, HOUSE, 30, 255)
    # The chimney, so it reads as a house at a glance and not as an arrow.
    # Its foot is inside the roof, so only its top two corners show.
    d.rounded_rectangle([px(v) for v in CHIMNEY], radius=px(16), fill=255)
    return mask


def family(canvas: Image.Image) -> None:
    """The icon's three figures, in blue on the house."""
    d = ImageDraw.Draw(canvas)
    blue = TOP

    def person(cx: float, head_y: float, head_r: float, body_w: float,
               body_top: float, bottom: float, colour) -> None:
        d.ellipse([px(cx - head_r), px(head_y - head_r), px(cx + head_r), px(head_y + head_r)],
                  fill=colour)
        d.rounded_rectangle([px(cx - body_w / 2), px(body_top), px(cx + body_w / 2), px(bottom)],
                            radius=px(body_w / 2), fill=colour)
        # The bottom is cut square, as in the icon.
        d.rectangle([px(cx - body_w / 2), px(body_top + body_w / 2), px(cx + body_w / 2),
                     px(bottom)], fill=colour)

    bottom = 760
    person(336, 476, 50, 176, 562, bottom, blue)
    person(568, 476, 50, 176, 562, bottom, blue)
    # The child stands in front, parted from the two by a white ring.
    ring = 12
    person(452, 582, 40 + ring, 128 + ring * 2, 636 - ring, bottom + 1, WHITE)
    person(452, 582, 40, 128, 636, bottom, blue)


def calendar(months: int) -> tuple[Image.Image, Image.Image]:
    """The calendar badge and its mask, both full canvas."""
    x0, y0, x1, y1 = BADGE
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([px(x0), px(y0), px(x1), px(y1)], radius=px(40), fill=255)
    for ring in RINGS:
        md.rounded_rectangle([px(v) for v in ring], radius=px(12), fill=255)
    layer = Image.new("RGB", (S, S), WHITE)
    d = ImageDraw.Draw(layer)
    # The header band, under the rings.
    band = Image.new("L", (S, S), 0)
    ImageDraw.Draw(band).rounded_rectangle([px(x0), px(y0), px(x1), px(y0 + 104)], radius=px(40),
                                           fill=255)
    ImageDraw.Draw(band).rectangle([px(x0), px(y0 + 60), px(x1), px(y0 + 64)], fill=255)
    layer.paste(TOP, mask=band)
    d.rectangle([px(x0), px(y0 + 64), px(x1), px(y0 + 104)], fill=WHITE)
    for ring in RINGS:
        d.rounded_rectangle([px(v) for v in ring], radius=px(12), fill=WHITE)
    # The body: one month, or twelve.
    inner = (x0 + 32, y0 + 92, x1 - 32, y1 - 32)
    if months == 1:
        d.rounded_rectangle([px(v) for v in inner], radius=px(20), fill=TOP)
    else:
        cols, rows, gap = 4, 3, 12
        w = (inner[2] - inner[0] - gap * (cols - 1)) / cols
        h = (inner[3] - inner[1] - gap * (rows - 1)) / rows
        for r in range(rows):
            for c in range(cols):
                left = inner[0] + c * (w + gap)
                top = inner[1] + r * (h + gap)
                d.rounded_rectangle([px(left), px(top), px(left + w), px(top + h)],
                                    radius=px(9), fill=TOP)
    return layer, mask


def gap_mask() -> Image.Image:
    """What the house gives up for the badge: one rounded outline GAP clear
    of the badge AND its rings. Cutting round each ring separately left a
    sliver of wall standing between them."""
    mask = Image.new("L", (S, S), 0)
    x0, y0, x1, y1 = BADGE
    top = min(ring[1] for ring in RINGS)
    ImageDraw.Draw(mask).rounded_rectangle(
        [px(x0 - GAP), px(top - GAP), px(x1 + GAP), px(y1 + GAP)], radius=px(40 + GAP), fill=255)
    return mask


def draw(months: int) -> Image.Image:
    canvas = gradient()
    house = ImageChops.subtract(house_mask(), gap_mask())
    badge, badge_mask = calendar(months)
    figures = Image.new("RGB", (S, S), WHITE)
    family(figures)
    canvas.paste(figures, mask=house)
    canvas.paste(badge, mask=badge_mask)
    return canvas.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for months, name in ((1, "promo-monthly.png"), (12, "promo-yearly.png")):
        image = draw(months).convert("RGB")
        image.save(OUT / name, dpi=(72, 72), optimize=True)
        print(OUT / name, image.size, image.mode)


if __name__ == "__main__":
    main()
