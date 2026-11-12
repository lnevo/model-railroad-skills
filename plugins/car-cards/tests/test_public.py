"""The plugin is public: no private names, addresses or oversized fixtures."""
import os
import re
import unittest
from pathlib import Path

from helpers import PLUGIN, PHOTOS

TEXT = {".py", ".md", ".toml", ".txt", ".json", ".html", ".csv", ".js", ".css", ""}


def public_files():
    for path in sorted(PLUGIN.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and ".venv" not in path.parts \
                and path.suffix in TEXT:
            yield path


def banned_words() -> list[str]:
    words = [w.strip() for w in os.environ.get("OPS_BANNED_TERMS", "").split(",") if w.strip()]
    listing = Path(os.environ.get("OPS_BANNED_WORDS_FILE",
                                  Path.home() / ".config" / "model-railroad-skills" / "banned_words.txt")).expanduser()
    if listing.is_file():
        words += [w.strip() for w in listing.read_text().splitlines() if w.strip() and not w.startswith("#")]
    return words


class Public(unittest.TestCase):
    def test_no_addresses_or_hosts(self):
        pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|[\w.+-]+@[\w-]+\.[\w.-]+|\b[\w-]+\.(?:local|lan|internal)\b")
        for path in public_files():
            self.assertIsNone(pattern.search(path.read_text(errors="replace")), str(path))

    def test_no_banned_words(self):
        words = banned_words()
        if not words:
            self.skipTest("no banned words: set OPS_BANNED_TERMS or OPS_BANNED_WORDS_FILE")
        banned = re.compile("|".join(map(re.escape, words)), re.I)
        for path in public_files():
            if path.name == "test_public.py":
                continue
            found = banned.search(path.read_text(errors="replace"))
            self.assertIsNone(found, f"{path}: {found and found.group(0)}")

    def test_fixture_photos_are_small(self):
        photos = sorted(PHOTOS.glob("*.jpg"))
        self.assertEqual([p.name for p in photos], ["flatcar.jpg", "hopper.jpg", "loco.jpg"])
        for p in sorted((PHOTOS.parent).rglob("*")):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                self.assertLess(p.stat().st_size, 120_000, p.name)


if __name__ == "__main__":
    unittest.main()
