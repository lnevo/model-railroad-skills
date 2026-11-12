"""Reading reporting marks, number and weights with Tesseract (pytesseract).

Ported from the source pipeline's process_car_images.py: the band OCR, the colour-difference OCR
(gold on silver lettering), the digit fix for O/0 and friends, and the stencil parsing. Road names
come only from cfg (roads.aliases, roads.context, roads.known), never from code.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from ._img_detect import detect_car_bbox
from .config import Config
from .paths import Paths
from .schema import OCR_FIELDS

# Where the big lettering sits on a finished car picture, as fractions (left, top, right, bottom) of
# the picture: the left-centre of the car side, as tuned on a set of coal hoppers.
LETTERING_WINDOW = (0.15, 0.24, 0.42, 0.62)
# The load-limit and light-weight stencil, read from the blue channel.
WEIGHT_WINDOW = (0.22, 0.60, 0.42, 0.84)
MASK_SCALES = (0.45, 0.35, 0.28)

WEIGHT_LABELS = re.compile(
    r"(CAPY|LD\s*LMT|LT\s*WT|LY\s*WT|LIGHT\s*WT|LOAD\s*LIMIT|CU\s*FT|CUFT|CAPACITY)\s*",
    re.I,
)

# Words and OCR noise that look like reporting marks but are not.
INVALID_MARKS = {
    "LT", "WT", "LTWT", "LYWT", "LD", "LMT", "LDLMT", "CAPY", "NEW", "BLT",
    "WI", "LR", "MJ", "LIKE", "LIGHT", "LOAD", "LRWT", "LY", "LO", "EXW", "EW",
}


def available() -> bool:
    """True when pytesseract imports and the tesseract program runs."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def digits(text: str) -> str:
    """Letters OCR mistakes for digits (O Q D -> 0, I l -> 1, S -> 5, B -> 8), then digits only."""
    table = str.maketrans("OQDIlSB", "0001158")
    return re.sub(r"\D", "", text.upper().translate(table))


def _is_weight_context(text: str, number: str) -> bool:
    for m in re.finditer(re.escape(number), text):
        start = max(0, m.start() - 35)
        snippet = text[start: m.end() + 5]
        if WEIGHT_LABELS.search(snippet):
            return True
    return False


def _valid_marks(marks: str) -> bool:
    mk = _norm(marks)
    return bool(mk) and mk not in INVALID_MARKS and not any(
        bad in mk for bad in ("LTWT", "LDLMT", "LIGHT", "LOAD"))


def _ocr_band(img: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[str, Image.Image]:
    """OCR the car-side band; return text and the upscaled OCR zoom image."""
    import pytesseract

    x0, y0, x1, y1 = bbox
    W, H = img.size
    pad_x = int(0.06 * (x1 - x0))
    pad_y = int(0.10 * (y1 - y0))
    rx0 = max(0, x0 - pad_x)
    ry0 = max(0, y0 - pad_y)
    rx1 = min(W, x1 + pad_x)
    ry1 = min(H, y1 + pad_y)
    band = img.crop((rx0, ry0, rx1, ry1))
    band = ImageOps.grayscale(band)
    band = band.point(lambda p: 255 if p > 175 else (0 if p < 110 else p))
    zoom = band.resize((band.width * 3, band.height * 3), Image.LANCZOS)

    # Reporting marks sit on the left third: OCR that band separately too.
    split = max(1, int(band.width * 0.42))
    left = band.crop((0, 0, split, band.height))
    left_zoom = left.resize((left.width * 4, left.height * 4), Image.LANCZOS)
    left_text = pytesseract.image_to_string(left_zoom, config="--psm 6")

    text = pytesseract.image_to_string(zoom, config="--psm 6")
    text = f"{left_text} {text}"
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text, zoom


def _ocr_mask(window: Image.Image, scale: float) -> str:
    """Read stencilled lettering as solid black on white, from its colour not its tone.

    Gold-on-silver lettering has almost no brightness contrast, so plain OCR reads
    noise. The red-minus-blue difference isolates it cleanly.
    """
    import pytesseract

    a = np.asarray(window.convert("RGB")).astype(int)
    diff = a[..., 0] - a[..., 2]
    thr = max(15.0, float(np.percentile(diff, 97)) * scale)
    img = Image.fromarray(np.where(diff > thr, 0, 255).astype("uint8"))
    img = img.filter(ImageFilter.MedianFilter(3))
    img = ImageOps.expand(img.resize((img.width * 2, img.height * 2)), border=30, fill=255)
    return pytesseract.image_to_string(img, config="--psm 6")


def ocr_lettering(crop: Image.Image, window: tuple[float, float, float, float] = LETTERING_WINDOW) -> dict:
    """Read reporting marks, road number and weights from a finished car crop.

    ``window`` is the part of the picture to read, as fractions (left, top, right, bottom); the
    default is the left-centre of the car side, where the big lettering sat on the cars this was
    tuned on. Returns only what it read; an empty dict means no luck.
    """
    import pytesseract

    W, H = crop.size
    out: dict[str, str] = {}
    left, top, right, bottom = window
    win = crop.crop((int(W * left), int(H * top), int(W * right), int(H * bottom)))
    for scale in MASK_SCALES:
        lines = [ln.strip() for ln in _ocr_mask(win, scale).upper().split("\n") if ln.strip()]
        for i, line in enumerate(lines[:-1]):
            marks = re.sub(r"[^A-Z]", "", line)
            number = digits(lines[i + 1])
            if 3 <= len(marks) <= 5 and len(number) >= 4:
                out.update(reporting_marks=marks, road_number=number, ocr_text=" ".join(lines))
                break
        if out:
            break
    blue = ImageOps.autocontrast(crop.convert("RGB").split()[2], cutoff=1)
    l2, t2, r2, b2 = WEIGHT_WINDOW
    wt = blue.crop((int(W * l2), int(H * t2), int(W * r2), int(H * b2)))
    wt = wt.resize((wt.width * 3, wt.height * 3), Image.LANCZOS)
    text = pytesseract.image_to_string(wt, config="--psm 6").upper()
    m = re.search(r"LD\s*LMT\D{0,6}(\d{6})", text)
    if m:
        out["ld_lmt_lbs"] = m.group(1)
    m = re.search(r"(?:LT|LIGHT)\s*WT\D{0,6}(\d{5})", text)
    if m:
        out["lt_wt_lbs"] = m.group(1)
    return out


def _parse_markings(text: str) -> dict:
    """Weights, build date and car class from stencil text (upper case)."""
    out: dict[str, str] = {}
    m = re.search(r"CAPY\s*([0-9,]+)", text)
    if m:
        out["capy_lbs"] = m.group(1).replace(",", "")
    m = re.search(r"LD\s*LMT\s*([0-9,]+)", text)
    if m:
        out["ld_lmt_lbs"] = m.group(1).replace(",", "")
    m = re.search(r"(?:LT|LIGHT)\s*WT\s*([0-9,]+)", text)
    if m:
        out["lt_wt_lbs"] = m.group(1).replace(",", "")
    for pat in (r"NEW\s*([0-9-]+)", r"BLT\s*([0-9-]+)", r"BUILT\s*([0-9-]+)"):
        m = re.search(pat, text)
        if m:
            out["built"] = m.group(1)
            break
    m = re.search(r"\b(LO|XM|GB|HT|F3|HTS)\b", text)
    if m:
        out["car_class"] = m.group(1)
    return out


# `marks number` shapes, tried in this order; each returns (marks, number) for a match. The split
# number goes first, or the plain pattern would take "XYZ 600" and leave "409" behind.
def _two_part(m):  # "K S 123" style: marks split by a space
    return f"{m.group(1)} {m.group(2)}", m.group(3)


def _plain(m):
    return m.group(1), m.group(2)


def _three_three(m):  # "XYZ 600 409": number split in two
    return m.group(1), f"{m.group(2)}{m.group(3)}"


MARK_PATTERNS = (
    (r"\b([A-Z&]{2,4})\s+(\d{3})\s+(\d{3})\b", _three_three),
    (r"\b([A-Z]{1,4})\s+([A-Z]{1,2})\s+(\d{2,6})\b", _two_part),
    (r"\b([A-Z&]{2,6})\s+(\d{2,6})\b", _plain),
)


def _find_road_mark(text: str, cfg: Config) -> tuple[str, str]:
    """Reporting marks and road number from OCR text, or ('', '').

    A word listed in roads.context (BALTIMORE -> BO) names the road when a 4 to 6 digit number
    stands on the car; otherwise the first valid `marks number` pair wins, but a pair whose mark
    is in roads.known beats one that is not. Marks go through roads.aliases.
    """
    for word, mark in cfg.road_context.items():
        if re.search(re.escape(word.upper()), text):
            for m in re.finditer(r"(?<![0-9])(\d{4,6})(?![0-9])", text):
                if not _is_weight_context(text, m.group(1)):
                    return cfg.road_code(mark), m.group(1)
    known = {cfg.road_code(k) for k in cfg.known_roads}
    first: tuple[str, str] | None = None
    for pat, take in MARK_PATTERNS:
        for m in re.finditer(pat, text):
            marks, number = take(m)
            if not _valid_marks(marks) or _is_weight_context(text, number):
                continue
            found = (cfg.road_code(marks), number)
            if not known or found[0] in known:
                return found
            first = first or found
    return first or ("", "")


def read(photo_png: Path, final_png: Path | None, paths: Paths, cfg: Config) -> dict:
    """Read one photo. Returns exactly schema.OCR_FIELDS as strings ('' when not found); writes the
    zoomed lettering to paths.ocr/<stem>.png. With no Tesseract, every field is ''."""
    result = {k: "" for k in OCR_FIELDS}
    if not available():
        return result
    photo_png = Path(photo_png)
    with Image.open(photo_png) as im:
        image = im.convert("RGB")
    text, zoom = _ocr_band(image, detect_car_bbox(image))
    paths.ocr.mkdir(parents=True, exist_ok=True)
    zoom.save(paths.ocr / f"{photo_png.stem}.png")
    parsed = _parse_markings(text)
    marks, number = _find_road_mark(text, cfg)
    if final_png is not None and Path(final_png).is_file():
        with Image.open(final_png) as im:
            read_ = ocr_lettering(im.convert("RGB"))
        if read_.get("reporting_marks"):  # the colour read of the finished crop beats the general OCR
            marks, number = cfg.road_code(read_["reporting_marks"]), read_["road_number"]
            text = f"{read_.get('ocr_text', '')} {text}"
        parsed.update({k: v for k, v in read_.items() if k in ("ld_lmt_lbs", "lt_wt_lbs")})
    result.update({k: parsed.get(k, "") for k in OCR_FIELDS if k not in ("reporting_marks", "road_number", "ocr_text")})
    result.update(reporting_marks=marks, road_number=number, ocr_text=text[:400].replace("\n", " "))
    return result
