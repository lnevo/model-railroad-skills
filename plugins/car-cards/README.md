# Car cards

Turn phone photos of your model railroad cars and locomotives into printed car cards. You take the photos; the plugin crops and levels each one, reads the reporting marks and number, and puts every photo on one review page that you check in a browser. Once you approve it, it prints poker-size cards, nine to a US Letter sheet, each with the photo, road name, number and a short description.

**Status: in development.** It is the workflow behind one layout's fleet of cards, made generic: nothing in it knows that railroad.

## Can do

- Crop a side-on photo to the car and level it, ending the crop at the track.
- Read reporting marks, road number and the capacity stencils with Tesseract, including low-contrast lettering such as gold on silver.
- Flag what needs a look: blurry photos, unread marks or numbers, odd number lengths, marks not in your fleet, duplicates, likely locomotives.
- Have the agent check every photo itself (the `photo-reader` agent) and mark where it disagrees with the OCR, without changing anything.
- Let you edit every field on the review page, fix a crop with a drag-and-zoom picker, and bring the edits back with one command.
- Give locomotives an even grey backdrop instead of the freight-car crop.
- Keep your approved cars and locomotives in two plain CSV files.
- Print the cards not yet printed, nine to a sheet, as a Word file, with your logo and form number; print a calibration page to check your stock.

## Can't do

- Read a locomotive's model, builder or DCC address from the photo: you type those in.
- Read lettering it has not been tuned for every time. The OCR window was tuned on one kind of car; other cars may read nothing, and then the photo check and your edits fill the gaps.
- Crop photos taken without a plain backdrop and a piece of track under the car.
- Make waybills, switch lists or train cards, or send cars to an operations program.

## What you need

- An AI coding agent that runs commands on your computer: Claude Code, Cursor or Codex. A chat window is not enough.
- Python 3.11 or newer, and [Tesseract](https://github.com/tesseract-ocr/tesseract) (`brew install tesseract` on a Mac, `apt install tesseract-ocr` on Debian or Ubuntu, the installer on Windows).
- Photos taken the same way each time: side-on at about car height, the car on a short piece of track in front of a plain light backdrop. HEIC photos from an iPhone work on a Mac; elsewhere add `pillow-heif`.
- Card stock. The default is poker-size sticker sheets (2.5 × 3.5 in cards, nine to a Letter page). Other stock works by changing the sheet settings; print the calibration page first.

## Install

### Claude Code

```
claude plugin marketplace add lnevo/model-railroad-skills
claude plugin install car-cards@model-railroad-skills
```

Then open the agent in an empty folder for your cards and ask: *"Use the car-cards skill. Set up a card folder here for my railroad, the [name], then run a first batch from `photos/incoming/` and stop at each stage for me to check."*

### Cursor and Codex

Get a copy of this repository and link the skill:

```
git clone https://github.com/lnevo/model-railroad-skills.git ~/model-railroad-skills
mkdir -p ~/.cursor/skills          # Cursor; for Codex use ~/.agents/skills
ln -s ~/model-railroad-skills/plugins/car-cards/skills/car-cards ~/.cursor/skills/car-cards
```

The skill runs the command at `~/model-railroad-skills/plugins/car-cards/bin/cards`. Neither platform runs the `photo-reader` agent, so the skill does the photo check itself. Neither has been tried on a real agent yet.

## The command

`bin/cards` runs from your card folder and uses its `.venv`. In an empty folder:

```
python3 -m venv .venv
.venv/bin/pip install -r /path/to/plugins/car-cards/requirements.txt
/path/to/plugins/car-cards/bin/cards init --name "Your Railroad" --short YR
```

| Command | Does |
|---|---|
| `cards init` | Writes `cards.toml` and the folders |
| `cards review [--batch NAME]` | Crops and reads new photos in `photos/incoming/`, writes `batches/<name>/review.html` |
| `cards ai-notes BATCH FILE` | Merges the photo check |
| `cards sheet-import BATCH FILE` | Takes the `review.csv` downloaded from the page |
| `cards fill BATCH --set COL=VALUE` | Sets a column on every row and fills gaps from the best row |
| `cards kind BATCH loco PHOTO..` | Switches photos between car and locomotive |
| `cards crop BATCH PHOTO X,Y,W,H[,ANGLE]` | Re-cuts one picture |
| `cards approve BATCH` | Approves the unflagged rows |
| `cards records BATCH [--dry-run]` | Writes approved rows to `data/cars.csv` and `data/locos.csv` |
| `cards locos set ID COL=VALUE..` / `cards locos status` | Locomotive details |
| `cards print [--calibrate] [--all] [--mark-printed]` | Builds `output/cards_<date>.docx` |
| `cards status` | Batches, fleet and cards waiting to print |

On Windows, run `.venv\Scripts\python -m cards` with `PYTHONPATH` set to the plugin folder.

## Settings

`cards.toml` in your card folder: railroad name, logo, form number, sheet preset and measurements, your reporting marks and how they print (`NW` → `N&W`), OCR misreads to fix, car types, description rules, the blur threshold, and words that must never print. Every key has a default. See [`skills/car-cards/references/settings.md`](skills/car-cards/references/settings.md).

## Tests

From this folder, with the requirements installed:

```
python3 -m unittest discover -s tests
```

Tests that read lettering run only when Tesseract is installed. They use three small photos in `tests/fixtures/photos/`.

## License

MIT
