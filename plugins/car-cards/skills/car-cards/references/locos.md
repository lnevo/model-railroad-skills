# Locomotives

A photo gives a locomotive's road and number and its picture. Everything else, the model and the type at least, the reader types in.

## What the photo gives

- **Road and number.** The OCR reads the photo, but it is weak on locomotives. The photo check (`ai-check.md`) is the reliable reading, so compare the two and correct the fields on the page. A car row whose OCR text holds a locomotive word gets `maybe-loco`; the OCR hint is weak, and `ai-says-loco` from the photo check is the better signal.
- **The picture.** See below.

To make a photo a locomotive from the start, name the file `loco_...` or `engine_...`. Otherwise switch it after review with `cards kind BATCH loco PHOTO`.

## The loco picture

A locomotive is not cut like a freight car. The freight-car crop tilts the photo and changes its exposure; a locomotive keeps its own pixels:

1. The program finds the locomotive as the large region that is not backdrop-coloured and cuts a box round it, with room around it and some track below.
2. It replaces the backdrop with a smooth neutral grey gradient, so creases, tape and dark corners disappear, and adds a soft shadow under the track.
3. It writes the finished picture and removes any print copy, so an old freight-style copy cannot win.

If no locomotive is found, the whole photo is used and the row gets the status `review` and the flag `crop-review`. Open the page, click *Adjust crop* and frame the locomotive with the track under it. The picker cuts it with the same clean-up. See `review-sheet.md`.

Look at every locomotive picture by eye.

## Details a photo cannot give

`cards records` adds an approved locomotive to `data/locos.csv` with its marks, number, length and description from the sheet, and the type set to `locos.default_type` (Diesel). It prints what is still missing, for example `new loco NW1776; needs model`.

The columns:

| Column | Notes |
|--------|-------|
| `reporting_marks`, `road_number` | From the photo. Required. |
| `model` | For example `GP38-2`. Required. |
| `loco_type` | For example `Diesel`. Required; filled with the default when the locomotive is added. |
| `builder` | For example `EMD`. |
| `length_ft` | Length in feet. |
| `hp` | Horsepower. |
| `dcc_address` | The decoder address. |
| `description` | Text for the card, replacing the built line. |
| `notes` | Free text. |

The tracking columns (`roster_id`, `photo`, `image`, `batch`, `recorded`, `card_built`, `card_printed`) are filled by the program. `roster_id` is the road marks plus the number with no space.

Set them with the roster id:

```
cards locos set NW1776 model=GP38-2 loco_type=Diesel length_ft=59 builder=EMD
```

- An unknown id or column stops the command and lists what is valid.
- Changing the marks or the number changes the roster id.
- A change marks the card as not built and not printed, so the next `cards print` includes it again.

`cards locos status` lists every locomotive and either `complete` or `needs: model ...`. A locomotive missing a required column is left off the print, with a line naming it. Ask the reader for the model and type of each one before printing.

## What prints on a locomotive card

- The title: `LOCOMOTIVE`.
- The road name: the marks passed through `roads.display`.
- The number.
- The description: the row's own `description`; if that is empty, `<builder> · <model> · <length>'`, leaving out what is missing; a dash if all are empty.
- The picture, and the logo and form line like any card.

`hp`, `dcc_address` and `loco_type` are kept in `data/locos.csv` and do not print.
