"""The railroad's settings: one ``cards.toml`` in the card folder, made by ``cards init``.

Every value has a default here, so a short file works. ``load`` merges the file over the
defaults; a key the file does not know is refused, so a typo is caught rather than ignored.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FILE_NAME = "cards.toml"

TEMPLATE = '''# Settings for your car and locomotive cards. Edit, then run the next cards command.
# Only change what you need: every key has a default.

[railroad]
name = "{name}"            # your railroad
short_name = "{short_name}"     # printed at the top left of each card when there is no logo
logo = ""                  # a square PNG beside this file, e.g. "logo.png"; it takes the short name's place
form = "Form CC-1    Rev A" # small print at the foot of each card

[sheet]
preset = "poker-3x3"       # nine 2.5 x 3.5 in cards on US Letter; see the printing reference

[roads]
known = []                 # your fleet's reporting marks, e.g. ["NW", "BO"]; marks not listed are flagged
display = {{}}               # how marks print on the card, e.g. {{ NW = "N&W", BO = "B&O" }}
aliases = {{}}               # misreads and spellings to fix, e.g. {{ "N&W" = "NW", NOW = "NW" }}
context = {{}}               # words on the car that name the road, e.g. {{ BALTIMORE = "BO" }}

[car_types]
aliases = {{ Boxcar = "Box Car", Flatcar = "Flat Car", Tank = "Tank Car", Coal = "Hopper" }}  # how a typed type prints

# Descriptions print as "<color> · <type> · <length>'". A rule changes the type label for
# cars that match it; the first matching rule wins. Leave the list empty to use the type as is.
# [[descriptions]]
# type = "Hopper"
# classes = ["LO"]              # the car class on the sheet
# words = ["covered", "cement"]  # any of these in the description or note
# label = "Cov Hopper"

[review]
blur_threshold = 600.0     # photos sharper than this pass; lower it if good photos are flagged blurry
flag_words = []            # words that must never print; a photo whose text holds one is flagged

[locos]
model_words = ["EMD", "ALCO", "LOCOMOTIVE", "DIESEL", "HORSEPOWER", "GP", "SD", "SW", "RS", "FA", "FB"]
default_type = "Diesel"
'''

DEFAULTS: dict = {
    "railroad": {"name": "My Railroad", "short_name": "MRR", "logo": "", "form": "Form CC-1    Rev A"},
    "sheet": {"preset": "poker-3x3"},
    "roads": {"known": [], "display": {}, "aliases": {}, "context": {}},
    "car_types": {"aliases": {"Boxcar": "Box Car", "Flatcar": "Flat Car", "Tank": "Tank Car", "Coal": "Hopper"}},
    "descriptions": [],
    "review": {"blur_threshold": 600.0, "flag_words": []},
    "locos": {
        "model_words": ["EMD", "ALCO", "LOCOMOTIVE", "DIESEL", "HORSEPOWER", "GP", "SD", "SW", "RS", "FA", "FB"],
        "default_type": "Diesel",
    },
}
# Sheet keys beyond "preset" are optional overrides of the preset's measurements, in inches
# (layout.SheetSpec field names). They are checked by layout, not here.
OPEN_TABLES = {("sheet",), ("roads", "display"), ("roads", "aliases"), ("roads", "context"), ("car_types", "aliases")}


@dataclass(frozen=True)
class DescriptionRule:
    type: str
    label: str
    classes: tuple[str, ...] = ()
    words: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    root: Path
    railroad_name: str
    short_name: str
    logo: Path | None
    form: str
    sheet: dict
    known_roads: tuple[str, ...]
    road_display: dict[str, str]
    road_aliases: dict[str, str]
    road_context: dict[str, str]
    car_type_aliases: dict[str, str]
    descriptions: tuple[DescriptionRule, ...]
    blur_threshold: float
    flag_words: tuple[str, ...]
    loco_model_words: tuple[str, ...]
    loco_default_type: str
    raw: dict = field(repr=False, default_factory=dict)

    def display_road(self, marks: str) -> str:
        """How a reporting mark prints on a card: the display map, else the mark itself."""
        return self.road_display.get(marks, marks)

    def road_code(self, marks: str) -> str:
        """The canonical mark for a reading: aliases applied, upper case, spaces removed."""
        text = (marks or "").strip().upper()
        aliases = {k.upper(): v for k, v in self.road_aliases.items()}
        return aliases.get(text, text).replace(" ", "")

    def car_type(self, name: str) -> str:
        return self.car_type_aliases.get((name or "").strip(), (name or "").strip())


def _merge(base: dict, over: dict, where: tuple = ()) -> dict:
    out = dict(base)
    for key, value in over.items():
        here = (*where, key)
        if where in OPEN_TABLES:  # free keys: road codes, type names, sheet overrides
            out[key] = value
            continue
        if key not in base:
            raise SystemExit(f"{FILE_NAME}: unknown setting {'.'.join(here)}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise SystemExit(f"{FILE_NAME}: {'.'.join(here)} must be a table")
            out[key] = _merge(base[key], value, here)
        else:
            out[key] = value
    return out


def from_dict(data: dict, root: Path) -> Config:
    raw = _merge(DEFAULTS, data)
    rr, roads, types, review, locos = raw["railroad"], raw["roads"], raw["car_types"], raw["review"], raw["locos"]
    rules = []
    for i, rule in enumerate(raw["descriptions"]):
        extra = set(rule) - {"type", "label", "classes", "words"}
        if extra or not {"type", "label"} <= set(rule):
            raise SystemExit(f"{FILE_NAME}: descriptions rule {i + 1} needs type and label, and takes "
                             f"only classes and words besides")
        rules.append(DescriptionRule(rule["type"], rule["label"], tuple(rule.get("classes", ())),
                                     tuple(w.lower() for w in rule.get("words", ()))))
    logo = (root / rr["logo"]) if rr["logo"] else None
    return Config(
        root=root, railroad_name=rr["name"], short_name=rr["short_name"], logo=logo, form=rr["form"],
        sheet=dict(raw["sheet"]), known_roads=tuple(roads["known"]), road_display=dict(roads["display"]),
        road_aliases=dict(roads["aliases"]), road_context=dict(roads["context"]),
        car_type_aliases=dict(types["aliases"]), descriptions=tuple(rules),
        blur_threshold=float(review["blur_threshold"]), flag_words=tuple(review["flag_words"]),
        loco_model_words=tuple(locos["model_words"]), loco_default_type=locos["default_type"], raw=raw)


def load(root: Path) -> Config:
    path = root / FILE_NAME
    if not path.is_file():
        raise SystemExit(f"No {FILE_NAME} in {root}. Run `cards init` there first.")
    with path.open("rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as err:
            raise SystemExit(f"{path}: {err}") from None
    return from_dict(data, root)


def template(name: str, short_name: str) -> str:
    return TEMPLATE.format(name=name.replace('"', "'"), short_name=short_name.replace('"', "'"))
