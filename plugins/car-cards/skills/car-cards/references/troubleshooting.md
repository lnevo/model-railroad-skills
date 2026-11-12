# Troubleshooting

Each entry is a symptom, then the fix.

## Every OCR field is blank

Tesseract is not installed, or the `tesseract` program is not on the path. Install it (`brew install tesseract`, `apt install tesseract-ocr`, or the Windows installer) and open a new terminal. A batch already made keeps its blanks. For a batch with nothing recorded yet, delete its folder under `batches/` and run `cards review` again. Meanwhile the photo check and the reader's edits fill the fields.

## `O` read as `0`, and similar

The road number goes through a digit fix: `O`, `Q` and `D` become `0`, `I` becomes `1`, `S` becomes `5`, `B` becomes `8`, and then only digits are kept. That fix is for numbers only. Reporting marks are letters and are never changed this way, so a mark with a digit-like letter stays as read.

If a number or a mark is still wrong, fix it on the page. The photo check is a second reading that catches these (`ai-disagrees`).

## Blank OCR on a type of car the reading was not tuned for

The area the OCR reads, and the weight area, were tuned on one kind of car, coal hoppers. Other types may read nothing. The photo check and the reader's edits cover it. A larger, sharper photo helps: in the tests a hopper read correctly at 2400 px wide and not at 1200 px. For a batch of one type, `cards fill` copies details from the best row.

## Weights look wrong, or were copied wrong

The OCR reads the capacity, load limit and light weight stencils, and misreads digits as it does in numbers. `cards fill` copies the best row's values into empty fields of cars of the same road and type, so one misread can spread. Check the weights against a sharp photo before approving, and set them with `cards fill BATCH --set lt_wt_lbs=42600 PHOTO..`, or leave them blank: the card does not print them.

## White-on-black lettering reads nothing

Light lettering on a dark car often reads nothing. Type the marks and number on the page, or take them from the photo check.

## `car_class` is a wrong guess

The OCR guesses a car class (`LO`, `XM`, `HT`) from noise. Blank it unless the class is printed on the car:

```
cards fill BATCH --set car_class=
```

A class is used by `descriptions` rules, so a wrong one can change the type word on the card.

## `crop-review` or `crop-failed`, or a crop that is off-centre or cuts an end

The automatic crop was unsure, or found no car. It was tuned on one backdrop, so a different backdrop can fool it. Fix the photo in *Adjust crop*, then `cards sheet-import`, or run the copied `cards crop BATCH PHOTO X,Y,W,H[,ANGLE]`. See `review-sheet.md`. If every photo in a batch is off, check the set-up in `photos.md` before cutting them one by one.

## `blurry` on a photo that looks sharp

The sharpness score is under `review.blur_threshold` (600 by default). The score is on the page next to the photo. If the good photos score a little below it, lower the threshold in `cards.toml`. Retake photos that are truly soft.

## A locomotive was cut like a freight car

The photo went in as a car. Switch it:

```
cards kind BATCH loco PHOTO
```

This cuts the locomotive picture. Name future locomotive photos `loco_...` or `engine_...`. If the locomotive picture is off, use *Adjust crop*. See `locos.md`.

## The card shows an old picture

A card uses the print copy in `images/print/` only when it is newer than the finished picture in `images/final/`. If a picture was re-cut and the card still looks old, re-cut it again with *Adjust crop* or `cards crop`: a car gets a new finished picture and a new print copy, and a locomotive's print copy is removed. Then run `cards print --all`.

## `number-length`

The road number has a different number of digits from the usual for that road in the batch: the count more than half of that road's cars have. A road with only one car in the batch is not checked. Check the digits against the photo; if the number is right, approve the row (`cards fill BATCH PHOTO --set status=approved`).

## A misread mark, such as `CTET` for `CSXT`

List every mark you use in `roads.known`: a mark that is not in the list gets `road-not-in-fleet`. The photo check also flags it (`ai-disagrees`).

## `ai-disagrees` on every row of one road

The marks printed on the cars are not the marks the railroad uses (for example `CSXT` printed, `CSX` used). The photo check keeps the printed reading. See `ai-check.md`.

## Cards print off the stock

Run `cards print --calibrate`, print `output/calibration.docx` at 100% scale, and compare it with the stock. Set the `[sheet]` overrides in `cards.toml` until the outlines fit (`settings.md`). Check that the print dialog is not scaling the page: use actual size, not *Fit to page*.

## `cards review` says the batch exists

A batch that exists is refused. Use `--batch` with a new name, or, for a batch with nothing recorded, delete its folder under `batches/`.

## `cards records` stops on pending rows

Set each flagged row to approved or rejected on the page and run `cards sheet-import`. Or run `cards records BATCH --allow-pending` to record the approved rows now and leave the rest.

## HEIC photo refused

On Linux and Windows run `pip install pillow-heif` in the card folder's environment, or convert the photo to JPG. On a Mac nothing is needed.
