"""Where everything lives in a reader's card folder. All paths hang off one root.

    cards.toml                 settings (config.py)
    photos/incoming/           new phone photos go here (JPG, PNG or HEIC)
    photos/png/                upright PNG copies of those photos, made by `cards review`
    batches/<name>/            one review: review.csv, review.html, manifest.csv, picker.json, picker/
    images/crop/<stem>.png     first automatic crop of a car photo
    images/final/<stem>.png    the finished card picture (what review.html shows and the card uses)
    images/print/<stem>.png    a sharpened copy of the final picture for printing
    images/ocr/<stem>.png      the zoomed lettering the OCR read, to check a misread
    data/cars.csv              approved cars (fleet.py)
    data/locos.csv             approved locomotives (fleet.py)
    output/                    printable .docx sheets

Paths stored in CSV files are relative to the root, with forward slashes, so a folder can move.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import FILE_NAME


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / FILE_NAME

    @property
    def incoming(self) -> Path:
        return self.root / "photos" / "incoming"

    @property
    def converted(self) -> Path:
        return self.root / "photos" / "png"

    @property
    def batches(self) -> Path:
        return self.root / "batches"

    @property
    def crops(self) -> Path:
        return self.root / "images" / "crop"

    @property
    def final(self) -> Path:
        return self.root / "images" / "final"

    @property
    def print_copies(self) -> Path:
        return self.root / "images" / "print"

    @property
    def ocr(self) -> Path:
        return self.root / "images" / "ocr"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def cars_csv(self) -> Path:
        return self.data / "cars.csv"

    @property
    def locos_csv(self) -> Path:
        return self.data / "locos.csv"

    @property
    def output(self) -> Path:
        return self.root / "output"

    def batch(self, name: str) -> Path:
        return self.batches / name

    def dirs(self) -> list[Path]:
        return [self.incoming, self.converted, self.batches, self.crops, self.final, self.print_copies,
                self.ocr, self.data, self.output]

    def ensure(self) -> None:
        for d in self.dirs():
            d.mkdir(parents=True, exist_ok=True)

    def rel(self, path: Path | None) -> str:
        """A path as stored in CSV: relative to the root when inside it, '' for None."""
        if path is None:
            return ""
        path = Path(path)
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def resolve(self, stored: str) -> Path | None:
        """The inverse of ``rel``."""
        if not stored:
            return None
        path = Path(stored)
        return path if path.is_absolute() else self.root / path


def find_root(start: Path | None = None) -> Path:
    """The nearest folder at or above ``start`` holding cards.toml."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / FILE_NAME).is_file():
            return folder
    raise SystemExit(f"No {FILE_NAME} here or above {here}. Run `cards init` in your card folder first.")
