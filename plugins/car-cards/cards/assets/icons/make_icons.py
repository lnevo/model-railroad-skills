"""Draw the three card icons (tracks, number sign, pencil, each in a circle) with Pillow.

Black line art on a transparent ground, 96 px square. Run `python make_icons.py` here to
rewrite the PNGs; they are drawn at 4x and reduced so the lines are smooth.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 96
SCALE = 4
W = SIZE * SCALE
LINE = 5 * SCALE  # stroke width at 4x
BLACK = (0, 0, 0, 255)


def _canvas():
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 4 * SCALE
    d.ellipse([m, m, W - m, W - m], outline=BLACK, width=LINE)
    return img, d


def _p(x: float, y: float) -> tuple[float, float]:
    """A point on a 0-100 grid, in canvas pixels."""
    return x * W / 100, y * W / 100


def tracks() -> Image.Image:
    img, d = _canvas()
    # two rails running away from the viewer, with ties across them
    for y, left, right in ((72, 30, 70), (62, 34, 66), (53, 38, 62), (45, 41, 59), (38, 43.5, 56.5)):
        d.line([_p(left, y), _p(right, y)], fill=BLACK, width=int(LINE * 0.6))
    d.line([_p(27, 80), _p(43, 30)], fill=BLACK, width=LINE)
    d.line([_p(73, 80), _p(57, 30)], fill=BLACK, width=LINE)
    return img


def number() -> Image.Image:
    img, d = _canvas()
    d.line([_p(42, 24), _p(36, 76)], fill=BLACK, width=LINE)
    d.line([_p(64, 24), _p(58, 76)], fill=BLACK, width=LINE)
    d.line([_p(27, 40), _p(76, 40)], fill=BLACK, width=LINE)
    d.line([_p(24, 60), _p(73, 60)], fill=BLACK, width=LINE)
    return img


def pencil() -> Image.Image:
    img, d = _canvas()
    # a pencil on the diagonal: body, ferrule line, and the sharpened tip
    body = [_p(60, 24), _p(72, 36), _p(40, 68), _p(28, 56)]
    d.polygon(body, outline=BLACK, width=LINE)
    d.line([_p(54, 30), _p(66, 42)], fill=BLACK, width=int(LINE * 0.7))
    tip = [_p(28, 56), _p(40, 68), _p(25, 75)]
    d.polygon(tip, outline=BLACK, width=LINE)
    return img


ICONS = {"railroad.png": tracks, "number.png": number, "pencil.png": pencil}


def main() -> None:
    here = Path(__file__).resolve().parent
    for name, draw in ICONS.items():
        draw().resize((SIZE, SIZE), Image.LANCZOS).save(here / name, optimize=True)


if __name__ == "__main__":
    main()
