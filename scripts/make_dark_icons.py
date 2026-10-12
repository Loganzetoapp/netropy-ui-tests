"""Generate the dark-mode variants of the webapp's logo and module icons.

The originals in webapp/static/ are the real product artwork: most have a
solid white background baked in, and all use a dark navy line color that
nearly vanishes on the dashboard's dark surface. For each one this writes
a "-dark" sibling (apposite-logo-dark.png, icons/dark/<name>.png) with:

- the white background converted to transparency ("color to alpha"
  against white, so anti-aliased edges blend cleanly instead of leaving
  a white halo), and
- navy/blue ink and neutral-gray text lifted to a light tint of the same
  hue, so the line art reads on dark. Teal/green accents get a smaller
  lift, enough to read without losing the brand color.

The page shows the right variant per theme in CSS (.img-light/.img-dark
in styles.css), so re-run this after adding or replacing an icon:

    .venv/bin/python scripts/make_dark_icons.py

Needs Pillow (installed in .venv alongside Playwright).
"""
import colorsys
from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"

# Minimum HLS lightness in dark mode for blue ink / gray text.
BLUE_MIN_L = 0.72
GRAY_MIN_L = 0.78
TEAL_MIN_L = 0.52
# Near-white gray pixels (faint drop shadows/edges in the originals) under
# this alpha are dropped; lifting them would turn them into visible lines.
GRAY_SPECK_ALPHA = 80


def _unmatte_white(r, g, b, a):
    # Smallest alpha that reproduces this pixel when composited over white.
    alpha = max(255 - r, 255 - g, 255 - b) / 255
    if alpha == 0:
        return 0, 0, 0, 0
    out = [round(255 - (255 - c) / alpha) for c in (r, g, b)]
    return (*out, round(alpha * a))


def _lift(r, g, b):
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    hue = h * 360
    if s < 0.15:
        l = max(l, GRAY_MIN_L)
    elif 195 <= hue <= 260:
        l = max(l, BLUE_MIN_L)
    elif 130 <= hue < 195:
        l = max(l, TEAL_MIN_L)
    else:
        return r, g, b
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))


def make_dark(src: Path, dst: Path) -> None:
    im = Image.open(src).convert("RGBA")
    px = []
    for r, g, b, a in im.getdata():
        r, g, b, a = _unmatte_white(r, g, b, a)
        if a < GRAY_SPECK_ALPHA and max(r, g, b) - min(r, g, b) < 40:
            a = 0
        if a:
            r, g, b = _lift(r, g, b)
        px.append((r, g, b, a))
    im.putdata(px)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, optimize=True)
    print(f"wrote {dst.relative_to(STATIC.parent.parent)}")


def main() -> None:
    make_dark(STATIC / "apposite-logo.png", STATIC / "apposite-logo-dark.png")
    for icon in sorted((STATIC / "icons").glob("*.png")):
        make_dark(icon, STATIC / "icons" / "dark" / icon.name)


if __name__ == "__main__":
    main()
