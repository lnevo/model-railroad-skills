# The review sheet

`cards review` writes `batches/<name>/review.html` and `review.csv`. Open `review.html` in a browser. It holds one block per photo. Look at the pictures first: cut-off ends, a border at the bottom, tilt.

A batch that already exists is refused. To redo one that has nothing recorded yet, delete its folder under `batches/` and run `cards review` again, or pass `--batch` with a new name for the new photos.

## What each block shows

- The finished card picture.
- The photo name, its kind (car or loco), the roster id (road marks plus number, or `?`), and the sharpness score (`blur`).
- The flags, or `ok` when there are none.
- A status menu: `pending`, `approved` or `rejected`. The block's border shows it: amber pending, green approved, red rejected, blue recorded.
- An input for each field: reporting marks, road number, car type, car class, color, length ft, capy lbs, ld lmt lbs, lt wt lbs, built, description and note.
- An *Adjust crop* button.

A recorded row is read-only and has no *Adjust crop*.

## Flags

A flag is a reason to look, not an error.

| Flag | Means |
|------|-------|
| `crop-review` | The automatic crop was unsure. Check it; use *Adjust crop*. |
| `crop-failed` | No car was found. The picture is a loose box in the middle of the photo. |
| `process-failed` | The photo could not be read. The reason is in the note. |
| `blurry` | Sharpness is under `review.blur_threshold`. |
| `no-marks`, `no-number` | The OCR found no reporting marks, or no road number. |
| `number-length` | The number has a different digit count from most cars of the same road in the batch (needs two or more cars of that road). |
| `road-not-in-fleet` | The marks are not in `roads.known` (only when that list is set). |
| `same-id-as-<photo>` | Two photos in the batch give the same roster id. |
| `already-recorded` | The roster id is already in the fleet with a picture. |
| `flag-word` | The OCR text or description holds a word from `review.flag_words`. |
| `maybe-loco` | The OCR text, or the car type, looks like a locomotive's. |
| `ai-says-loco` | The photo check calls a car row a locomotive. |
| `ai-says-car` | The photo check calls a locomotive row something else. |
| `ai-disagrees` | The photo check read other marks or another number than the fields hold. |

`sheet-import`, `fill`, `kind` and `crop` work the flags out again. `cards ai-notes` redoes only the three `ai-` flags. `cards approve` approves only rows with no flags.

## Edit on the page

Type in any field. Change a row's status with its menu. Nothing is saved to the card folder from the page. Click *Download review.csv*, then run:

```
cards sheet-import BATCH ~/Downloads/review.csv
```

`sheet-import` takes only the editable fields, the status and the crop from the file. Flags, roster ids and the photo-check columns are worked out again for every row, approved rows included. A recorded row is left as it was. The command refuses a file from another batch, and a status other than pending, approved or rejected.

Edits stay in the browser between visits, for this batch on this computer. Download before switching browsers.

After a `cards` command rewrites the page, a field the reader changed keeps the reader's value, unless the command changed that same field: the command came later, so its value shows. A field the reader did not change takes the page's new value, so a `cards fill` or `cards ai-notes` shows up without clearing anything.

## Adjust crop

Click *Adjust crop* on a block.

- Drag the photo to move it. Scroll, or use the zoom slider, to zoom.
- The angle slider straightens the photo.
- *Shape* changes the frame's width to height. The frame is the card picture's shape, so what the frame shows is what the card shows.
- *Automatic crop* goes back to the program's box.
- *Use this crop* keeps the box and previews it on the block as `new crop ... (applied by cards sheet-import)`. Download the sheet and run `cards sheet-import`.
- *Copy command* copies `cards crop BATCH PHOTO X,Y,W,H[,ANGLE]`. Run it to cut that one photo now.
- *Clear new crop* drops the choice. *Close* or Escape leaves the picker.

`sheet-import` and `cards crop` cut the picture again: a car gets a new final and a new print copy, a locomotive is cut and cleaned to the grey backdrop and loses its print copy. The row's crop status becomes ok, the sharpness score is measured again, and the command asks for a look by eye.

A new crop does not read the lettering again. Correct marks and number by hand.

A batch made without the picker gets it with `cards crop BATCH`. `cards crop BATCH --refresh` rebuilds every view. A recorded photo's crop cannot be changed.

## cards fill

For a batch of one car type, set the common columns in one command:

```
cards fill BATCH --set reporting_marks=XX --set car_type=Hopper
```

- `--set COLUMN=VALUE` sets the column on every pending row, or on the photos named after the batch. `--set COLUMN=` blanks it. The columns are the page's fields and `status`.
- `--set status=approved` (or `rejected`, or `pending`) needs the photos named: it is how to approve a flagged row from the command line. `cards approve` approves the unflagged ones.
- Then each of those cars' empty details are filled from the best row of the same road and car type. Details are car type, car class, color, length, the three weights and the build date. Not the description.
- The best row is the one with the most details filled, then the sharper photo.
- A batch can mix car types, so details never cross from a flat car to a hopper. A row with no marks or no car type is not filled, and a group needs two cars or more.
- Where a row's own reading differs from the best row's, the command prints both and leaves the row alone.

## cards kind

```
cards kind BATCH loco IMG_0007.jpg IMG_0008.jpg
cards kind BATCH car IMG_0009.jpg
```

Switches pending photos between car and locomotive. It cuts the other kind's picture, works out the roster id again, and clears `maybe-loco`, `ai-says-loco` and `ai-says-car`. Rows that are not pending are left alone.

## Next

After corrections, `cards approve BATCH` approves the unflagged rows. The reader sets each flagged row to approved or rejected on the page, and `sheet-import` takes that in.
