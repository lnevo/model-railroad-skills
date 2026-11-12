# The photo check

The photo check is a second reading of every photo, made by looking at the picture rather than running OCR. It catches misread marks and numbers, and car rows that are really locomotives. It only suggests. It never changes a field or a status; the reader decides.

## Run it with the photo-reader agent

1. Open `batches/<name>/review.csv` and list the photos. Split them into groups of about ten.
2. Start one `photo-reader` run per group. Give each run:
   - the batch folder (`batches/<name>`) and the card folder, which is two levels above it;
   - the photo names, each with its `image` path from `review.csv` (relative to the card folder).
3. Each run returns only JSON, one entry per photo, keyed by the photo name:

   ```json
   {"IMG_0001.jpg": {"marks": "CSXT", "number": "379808", "type": "Hopper", "note": ""}}
   ```

   - `marks`: the reporting marks as printed, with `&` kept.
   - `number`: the road number as printed, digits only.
   - `type`: what the car is, such as Box Car, Hopper, Gondola, Tank Car, Caboose, or Locomotive.
   - `note`: anything the reader should know, or empty. Lettering too small to read, a digit in doubt, a crop that cuts the car.
4. Merge the answers from all runs into one JSON object and save it, for example as `batches/<name>/ai.json`.
5. Run:

   ```
   cards ai-notes BATCH batches/<name>/ai.json
   ```

   The command prints the photos that disagree with the OCR. It stops without changing anything if the file names a photo that is not in the batch.

Run the check before `cards approve`: approve refuses while a pending row has no photo-check note. `cards approve BATCH --no-ai` skips the check.

## What the command does with the answers

It stores `ai_marks`, `ai_number`, `ai_type` and `ai_note` on each row. A row with an empty note gets the note `reviewed`. Then it sets flags:

| Flag | Set when |
|------|----------|
| `ai-disagrees` | the marks or the number read differs from the row's fields. Case, spaces and punctuation are ignored. |
| `ai-says-loco` | the type is locomotive, diesel, engine, switcher, electric or steam on a row that is a car. |
| `ai-says-car` | the type is anything else on a row that is a locomotive. |

A field the agent left empty because it could not read it also counts as different from a filled field. Check those by eye.

Running `ai-notes` again for the same photos replaces their notes and flags.

## Marks printed differently from the marks the railroad uses

Photos show what is printed on the car. If the railroad uses other marks for it, for example `CSXT` printed and `CSX` used, set the used marks in the fields (on the page or with `cards fill --set reporting_marks=CSX`). The photo check keeps the printed reading, so every one of those rows shows `ai-disagrees`. That one difference is expected. Look at the number and the type on those rows instead.

## Platforms without sub-agents

Where the agent cannot start the `photo-reader` agent, the main agent does the same reading itself:

1. Read `review.csv`. For each photo, open the image in the `image` column and look at it closely.
2. Write down marks, number, type and note as above, before looking at the OCR columns. Reading the OCR first pulls the reading toward it. Read what is printed; leave a field empty and say why in the note rather than guess a digit.
3. Do about ten photos at a time, then merge the entries into the same single JSON file and run `cards ai-notes`.

On either path, show the reader the rows with `ai-disagrees`, `ai-says-loco` or `ai-says-car`, and do not edit their fields from the check.
