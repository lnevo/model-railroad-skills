# Printing

`cards print` writes a Word file of cards, nine to a US Letter page. Print a test on plain paper before the stock.

## The poker-3x3 preset

The default stock is a poker-size sticker sheet, three cards across and three down.

| Measurement | Inches |
|-------------|--------|
| Page | 8.5 x 11 |
| Slot (one card) | 2.560 x 3.540 |
| Top margin | 0.140 |
| Bottom margin | 0.070 |
| Left margin | 0.290 |
| Right margin | 0.250 |
| Columns x rows | 3 x 3 |

Each card is drawn inside its slot, with a rounded outline. For other stock, see the end of `settings.md`.

## 1. Calibrate once

```
cards print --calibrate
```

This writes `output/calibration.docx`: nine slot outlines with their sizes, and the page size and margins in the middle slot. It changes no card.

Print it on plain paper at 100% scale (see below), then hold it against the stock over a window. The outlines must sit on the cards. If they do not, change the `[sheet]` measurements in `cards.toml`, print again, and repeat.

## 2. Print the cards

```
cards print
```

This builds `output/cards_<date>.docx` with every car and locomotive whose card is not yet printed, cars first and locomotives after them. It lists each card and whether it has a picture. A locomotive missing a required detail is skipped with a line naming what it needs (`locos.md`). With no cards waiting, it says so and writes nothing.

To rebuild every card, printed or not:

```
cards print --all
```

Run the command again after a change and the file is rewritten under the same name for that day.

## 3. Print the file

Open the `.docx` in Word, LibreOffice or Pages. In the print dialog:

- Paper: US Letter.
- Scale: actual size, 100%. Turn off *Fit to page*, *Shrink to fit* and any scaling option.

Print one sheet on plain paper first. Hold it against the stock. Then print on the stock.

## 4. Mark the cards printed

When the reader is happy with the print:

```
cards print --mark-printed
```

It marks every card that was built and not yet marked. The next `cards print` leaves those cards out. If the print was not good, do not run it; fix the problem and run `cards print` again.

## What is on a card

- Top left: the logo from `railroad.logo`, if set.
- Top right: a boxed title, the car type in capitals, or `LOCOMOTIVE`.
- The picture.
- Three lines: road name, number, description.
- The foot: the form line from `railroad.form`.

A card with no road or number prints `?`. A card with no picture prints without one, and `cards print` says `no picture` for it.

## Which picture a card uses

The card uses the finished picture in `images/final/`. It uses the sharpened print copy in `images/print/` only when that copy is newer than the finished picture. A re-cut writes both for a car, so the copy is the sharpened one; for a locomotive the print copy is removed, so the finished picture is used.

Pictures are shrunk to print resolution (600 dots per inch at the card's picture width) when the file is built, so the sheet stays a few megabytes.
