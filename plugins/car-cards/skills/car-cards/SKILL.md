---
name: car-cards
description: Turns phone photos of model railroad freight cars and locomotives into printed car cards with the car-cards command. It crops and levels each photo, reads the reporting marks and number, puts every photo on one review page the reader checks in a browser, records the approved cars and locomotives, and prints poker-size cards nine to a sheet. Use when someone wants car cards, equipment cards or rolling stock cards from photos, asks to set up a card folder, run a batch, review or fix crops, check what the lettering says, add locomotive details, print cards or calibrate card stock. Not for waybills, switch lists or train cards.
---

# Car cards from photos

The reader gets a printed card for each car and locomotive: the photo, the road name, the number and a short description, nine poker-size cards to a US Letter sheet. They take the photos; the `cards` command does the cropping, reading and layout; the agent checks what the command read and runs each stage. **Nothing moves to the next stage until the reader approves the one before.** Stop at the end of every stage, say what to look at, and wait.

## Set up once

1. **Python and Tesseract.** Python 3.11 or newer, and Tesseract for reading lettering (`brew install tesseract`, `apt install tesseract-ocr`, or the Windows installer from the Tesseract project). Without Tesseract every OCR field comes back blank and the review falls back on the photo check and the reader's edits.
2. **The card folder.** In an empty folder the reader chooses: `python3 -m venv .venv`, then `.venv/bin/pip install -r <plugin>/requirements.txt`, then `<plugin>/bin/cards init --name "Their Railroad" --short TR`. `<plugin>` is this plugin's folder: two folders above this file, the one holding `bin/` and `cards/`. `bin/cards` uses `./.venv` when it is there. On Windows run `.venv\Scripts\python -m cards` with `PYTHONPATH` set to the plugin folder.
3. **Settings.** `init` writes `cards.toml`. Go through it with the reader: a logo (a square PNG in the card folder; without one the short name prints in its place), the form number in the footer, their reporting marks in `roads.known`, how marks print (`roads.display`, e.g. `NW = "N&W"`), and description rules. Every key has a default; see `references/settings.md`.
4. **Photos.** Read `references/photos.md` with the reader before the first batch. The crop expects a side-on photo on a short piece of track in front of a plain light backdrop. Start with five to ten cars of one type.

## The stages

| Stage | Command | The reader checks |
|-------|---------|-------------------|
| 1. Review | `cards review [--batch NAME]` | crops on `batches/<name>/review.html` |
| 2. Photo check | the `photo-reader` agent, then `cards ai-notes BATCH FILE` | flagged rows |
| 3. Corrections | edits on the page + `cards sheet-import BATCH FILE`, or `cards fill`, `cards kind`, `cards crop` | every row's fields |
| 4. Approve | `cards approve BATCH` | the rows still flagged |
| 5. Records | `cards records BATCH --dry-run`, then without | `data/cars.csv`, `data/locos.csv` |
| 6. Locomotive details | `cards locos set ID model=... loco_type=...`, `cards locos status` | what each loco still needs |
| 7. Print | `cards print --calibrate` once, then `cards print`, then `cards print --mark-printed` | the calibration page, then a test sheet |

1. **Review.** New photos go in `photos/incoming/`. `cards review` crops and levels each one, reads the lettering, measures sharpness, and writes `batches/<date>/review.csv` and `review.html`. A photo whose file name starts `loco_` or `engine_` starts as a locomotive; every other photo starts as a car. Ask the reader to open `review.html` and look at the crops first: cut-off ends, a border at the bottom, tilt. A batch name that exists is refused, and photos already in a batch are skipped: to redo photos that are not recorded yet, delete their batch folder and run `review` again. See `references/review-sheet.md`.
2. **Photo check.** Run the `photo-reader` agent on the batch, about ten photos per agent; give each run the batch folder and its photo names with their `image` paths from `review.csv`, so it reads the pictures before it sees the OCR. Merge the answers into one JSON file (`{photo: {marks, number, type, note}}`), then `cards ai-notes BATCH FILE`. Where there is no such agent, read each picture yourself the same way. The check only suggests: it never changes the OCR fields or the status. See `references/ai-check.md`.
3. **Corrections.** Show the reader the flagged rows. They edit on the page and click *Download review.csv*; then `cards sheet-import BATCH <downloaded file>`. `cards fill BATCH --set car_type=Hopper --set length_ft=40 PHOTO..` sets columns on the named photos (every pending row when none are named), then fills their empty details from the best photo of the same road and car type, so a hopper never takes a flat car's weights. Set each car's own marks and number first. Switch a car to a locomotive with `cards kind BATCH loco PHOTO`: its picture is re-cut round the locomotive with an even grey backdrop. Fix a crop with *Adjust crop* on the page (then `sheet-import`), or `cards crop BATCH PHOTO X,Y,W,H[,ANGLE]`. Do not edit fields from the photo check yourself: the reader decides.
4. **Approve.** `cards approve BATCH` approves every unflagged pending row and refuses while a pending row has no photo-check note (`--no-ai` skips that). The reader sets each flagged row to approved or rejected.
5. **Records.** `cards records BATCH --dry-run` shows what would be written; without it, the approved rows go into `data/cars.csv` and `data/locos.csv` and the batch gets a `manifest.csv`.
6. **Locomotive details.** A photo gives a locomotive's road and number only. Ask the reader for the model (and builder and length, which print on the card; horsepower or DCC address if they want them kept): `cards locos set ID model=GP38-2 builder=EMD length_ft=59`. New locomotives get `locos.default_type` as their type. `cards locos status` lists what each still needs; a loco missing a required field is left off the print. See `references/locos.md`.
7. **Print.** The first time, `cards print --calibrate` writes a page of card outlines to print on plain paper and hold against the reader's stock. Then `cards print` writes every card not yet printed to `output/cards_<date>.docx`. After the reader has printed it and is happy, `cards print --mark-printed`. `--all` rebuilds every card. See `references/printing.md`.

`cards status` shows the batches, the fleet and the cards waiting to print at any time.

## Flags

A flag is a reason for the reader to look, not an error. `crop-review` and `crop-failed` (the automatic crop was unsure or found no car), `process-failed` (the photo could not be read; the reason is in the note), `blurry`, `no-marks`, `no-number`, `number-length` (a different digit count from others of the same marks), `road-not-in-fleet` (marks not in `roads.known`), `same-id-as-<photo>` (twice in the batch), `already-recorded` (the car already has a picture in the fleet), `flag-word` (the text holds a word from `review.flag_words`), `maybe-loco`, `ai-says-loco`, `ai-says-car`, `ai-disagrees`.

## When something goes wrong

`references/troubleshooting.md` covers the common cases: `O` read as `0` and the like, blank OCR on a new car type, a crop that fell back, a locomotive cut like a freight car, an old print copy, marks printed differently from the ones the railroad uses, and cards that print off the stock.

## What it does not do

Waybills, switch lists and train cards; reading a locomotive's model or DCC address from the photo; sending cars to any operations program. The CSV files in `data/` are plain, so the reader can take them elsewhere.
