# Settings: cards.toml

`cards init` writes `cards.toml` in the card folder. Edit it, then run the next `cards` command. Every key has a default, so a short file works. A key the file does not know is refused with its name, so a typo is caught.

## railroad

| Key | Default | What it changes |
|-----|---------|-----------------|
| `name` | `"My Railroad"` | The railroad's name, set by `cards init --name`. For your own reference; the card does not print it. |
| `short_name` | `"MRR"` | A short form, set by `cards init --short`. Printed in bold at the top left of every card when there is no logo. |
| `logo` | `""` | A PNG in the card folder, e.g. `"logo.png"`. It prints at the top left of every card, 0.56 in wide. Use a square image. Blank, or a file that is missing, prints `short_name` there instead. |
| `form` | `"Form CC-1    Rev A"` | The small line at the foot of every card. Put your own form number and revision here. |

## sheet

| Key | Default | What it changes |
|-----|---------|-----------------|
| `preset` | `"poker-3x3"` | The card stock. The only preset is `poker-3x3`: nine 2.5 x 3.5 in cards on US Letter. See `printing.md`. |
| other keys | from the preset | Measurements in inches that replace the preset's. See "Other card stock" below. |

## roads

| Key | Default | What it changes |
|-----|---------|-----------------|
| `known` | `[]` | Your fleet's reporting marks, e.g. `["NW", "BO"]`. Marks not in the list get the `road-not-in-fleet` flag. An empty list turns that flag off. The OCR also prefers a `marks number` pair whose marks are listed. |
| `display` | `{}` | How marks print on the card, e.g. `{ NW = "N&W" }`. The key must equal the marks in the row's `reporting_marks` column, letter for letter. Marks with no entry print as they are. |
| `aliases` | `{}` | Misreads and spellings to fix, e.g. `{ "N&W" = "NW", NOW = "NW" }`. Applied to every reading, and to the roster id: the reading is upper-cased, looked up here, and has its spaces removed. Write keys in upper case. |
| `context` | `{}` | A word printed on the car that names the road, e.g. `{ BALTIMORE = "BO" }`. When the word is in the lettering and a 4 to 6 digit number stands beside it (not a weight), the OCR takes that road and number. |

## car_types

| Key | Default | What it changes |
|-----|---------|-----------------|
| `aliases` | `Boxcar` = `Box Car`, `Flatcar` = `Flat Car`, `Tank` = `Tank Car`, `Coal` = `Hopper` | Spellings that become another type name. Applied to the title on the card and when `cards fill` matches cars by type. A single word ending in `car` is split anyway (`Boxcar` prints as `Box Car`). The title prints in capitals. |

## descriptions

The description line on a card reads `<color> · <type> · <length>'`. A rule changes the type word for the cars it matches. The first matching rule wins. With no rules, the type prints as it is.

```toml
[[descriptions]]
type = "Hopper"                  # the car type the rule applies to
classes = ["LO"]                 # matches when the car class is one of these
words = ["covered", "cement"]    # or when any of these is in the car's note
label = "Cov Hopper"             # prints in place of the type
```

A rule needs `type` and `label`; `classes` and `words` are optional and nothing else is accepted. Words match in lower case, in the note typed on the review page (`cards records` keeps it as the car's notes). A description typed into a car's `description` field replaces the whole line, rule and all. With nothing known, the line prints a dash.

A locomotive's line is its `description`, or `<builder> · <model> · <length>'` when that is empty.

## review

| Key | Default | What it changes |
|-----|---------|-----------------|
| `blur_threshold` | `600.0` | A photo whose sharpness score is below this gets the `blurry` flag. The score is on the page next to each photo. Lower the number when good photos are flagged. |
| `flag_words` | `[]` | Words or phrases that must never print. A photo whose OCR text or description holds one gets the `flag-word` flag. Whole words only, any case. |

## locos

| Key | Default | What it changes |
|-----|---------|-----------------|
| `model_words` | EMD, ALCO, LOCOMOTIVE, DIESEL, HORSEPOWER, GP, SD, SW, RS, FA, FB | Words that make a car row look like a locomotive (`maybe-loco`). Words of three letters or more match as whole words. Shorter ones, such as `GP`, match only when 1 or 2 digits follow (`GP38`), so marks like `NW 32800` do not trip it. |
| `default_type` | `"Diesel"` | The `loco_type` given to a locomotive when `cards records` first adds it. |

## Example: a railroad with two roads

```toml
[railroad]
name = "Valley Central"
short_name = "VC"
logo = "logo.png"
form = "Form VC-1    Rev B"

[roads]
known = ["NW", "BO"]
display = { NW = "N&W", BO = "B&O" }
aliases = { "N&W" = "NW", NOW = "NW", "B&O" = "BO" }
context = { BALTIMORE = "BO" }

[car_types]
aliases = { Boxcar = "Box Car", Coal = "Hopper" }

[[descriptions]]
type = "Hopper"
words = ["covered"]
label = "Cov Hopper"

[review]
blur_threshold = 450.0
flag_words = ["sample"]
```

Cars read as `N&W` or `NOW` become `NW`, print as `N&W`, and have the roster id `NW` plus the number.

## Other card stock

Put measurements, in inches, under `[sheet]` after the preset. They replace the preset's values; any you leave out keep the preset's.

| Key | Meaning |
|-----|---------|
| `page_w`, `page_h` | Paper size |
| `margin_top`, `margin_bottom`, `margin_left`, `margin_right` | Space before the first slot |
| `slot_w`, `slot_h` | One card's slot |
| `columns`, `rows` | Slots across and down |

Page and slot sizes, `columns` and `rows` must be above zero; margins may be zero. Values must be plain numbers. An unknown name or a bad value stops the command with a message.

A wider slot widens the card and a taller slot makes the picture taller. The card's art is drawn for the poker slot, so check any change on paper.

To set up other stock, for example 2.5 x 3.5 in cards on a sheet with different margins:

1. Measure the sheet's slot width, slot height and margins in inches.
2. Add them to `[sheet]`:

   ```toml
   [sheet]
   preset = "poker-3x3"
   margin_top = 0.5
   margin_left = 0.75
   slot_w = 2.5
   slot_h = 3.5
   ```

3. Run `cards print --calibrate`, print `output/calibration.docx` on plain paper at 100%, and hold it against the stock over a window or light. The outlines must sit on the cards.
4. Change the numbers and repeat until they do. Then run `cards print`.
