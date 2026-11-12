"""The CSV columns every module shares. Fixed before the modules were written: change with care.

review.csv (one per batch, batches/<name>/review.csv): one row per photo.
data/cars.csv and data/locos.csv: the approved fleet, written by `cards records`.
"""
from __future__ import annotations

# ---- review.csv
REVIEW_COLUMNS = [
    "photo",            # file name in photos/incoming/ (the key; never edited)
    "kind",             # car | loco
    "image",            # finished card picture, relative to the root ('' if processing failed)
    "crop",             # crop picker box "X,Y,W,H[,ANGLE]" on the levelled view; '' = automatic crop
    "reporting_marks",  # as printed on the car (OCR, then the reader's edits)
    "road_number",
    "car_type",
    "car_class",        # the AAR class only when printed on the car; OCR guesses are noisy
    "color",
    "length_ft",
    "capy_lbs",
    "ld_lmt_lbs",
    "lt_wt_lbs",
    "built",
    "description",      # card description override; '' = built from color, type and length
    "roster_id",        # derived: road code + number, no space ('' until both are known)
    "ocr_text",         # first 400 characters the OCR read
    "crop_status",      # ok | review | failed
    "blur",             # image.blur_score of the finished picture, as text
    "ai_marks",         # the photo-reader agent's reading; it never changes the fields above
    "ai_number",
    "ai_type",
    "ai_note",          # 'reviewed' when the agent had nothing to add
    "flags",            # ';'-joined reasons to look (FLAGS below)
    "status",           # STATUSES below
    "note",             # free text; a processing error is stored here
]
# Fields the reader may edit on review.html (and with `cards fill`).
EDIT_FIELDS = ["reporting_marks", "road_number", "car_type", "car_class", "color", "length_ft",
               "capy_lbs", "ld_lmt_lbs", "lt_wt_lbs", "built", "description", "note"]
# Fields image + ocr fill on the first pass (ocr.read returns exactly these keys).
OCR_FIELDS = ["reporting_marks", "road_number", "car_type", "car_class", "capy_lbs", "ld_lmt_lbs",
              "lt_wt_lbs", "built", "ocr_text"]

PENDING, APPROVED, REJECTED, RECORDED = "pending", "approved", "rejected", "recorded"
STATUSES = (PENDING, APPROVED, REJECTED, RECORDED)

FLAGS = (
    "crop-review",          # the automatic crop was unsure: check it, use Adjust crop
    "crop-failed",          # no crop at all
    "process-failed",       # the photo could not be read; see note
    "blurry",               # blur under review.blur_threshold
    "no-marks", "no-number",
    "number-length",        # number length differs from others of the same marks
    "road-not-in-fleet",    # marks not in roads.known (only when that list is set)
    "same-id-as-<photo>",   # two photos give the same roster id
    "already-recorded",     # the roster id is already in cars.csv or locos.csv with a picture
    "flag-word",            # the OCR text holds one of review.flag_words
    "maybe-loco",           # the OCR text looks like a locomotive's
    "ai-says-loco", "ai-says-car", "ai-disagrees",
)

MANIFEST_COLUMNS = ["photo", "kind", "roster_id", "outcome", "recorded"]

# ---- fleet (data/cars.csv, data/locos.csv)
COMMON_FLEET = ["roster_id", "reporting_marks", "road_number"]
CARD_TRACKING = ["photo", "image", "batch", "recorded", "card_built", "card_printed", "notes"]
CAR_COLUMNS = [*COMMON_FLEET, "car_type", "car_class", "color", "length_ft", "capy_lbs", "ld_lmt_lbs",
               "lt_wt_lbs", "built", "description", *CARD_TRACKING]
LOCO_COLUMNS = [*COMMON_FLEET, "model", "builder", "loco_type", "length_ft", "hp", "dcc_address",
                "description", *CARD_TRACKING]
# A loco card needs these before it prints; `cards locos status` lists what is missing.
LOCO_REQUIRED = ["reporting_marks", "road_number", "model", "loco_type"]
