"""Shared test helpers: a fresh card folder in a temp dir, and the fixture photos."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
FIXTURES = PLUGIN / "tests" / "fixtures"
PHOTOS = FIXTURES / "photos"  # flatcar.jpg, hopper.jpg (CSXT 379808, gold on silver), loco.jpg (CSX 2121)
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from cards import config  # noqa: E402
from cards.paths import Paths  # noqa: E402


def tesseract() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


NEEDS_TESSERACT = unittest.skipUnless(tesseract(), "Tesseract is not installed")


class CardFolder(unittest.TestCase):
    """A test with self.paths and self.cfg for a new card folder, removed afterwards."""

    toml = ""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cards-test-"))
        self.paths = Paths(self.tmp)
        self.paths.ensure()
        self.paths.config.write_text(config.template("Test Valley Railroad", "TVR") + self.toml)
        self.cfg = config.load(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def photo(self, name: str, as_name: str | None = None) -> Path:
        """Copy a fixture photo into photos/incoming/ and return its path there."""
        dest = self.paths.incoming / (as_name or name)
        shutil.copy(PHOTOS / name, dest)
        return dest
