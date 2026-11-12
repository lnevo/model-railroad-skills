"""Builder 3b. review.html: one card per photo, editable fields, status, Adjust crop (picker.page_parts)
and a "Download review.csv" button. Edits are kept in the browser until downloaded; the reader then
runs `cards sheet-import <batch> <file>`. Image links are relative to the batch folder, so the page
works when the card folder moves.
"""
from __future__ import annotations

from pathlib import Path


def write_page(batch: Path, rows: list[dict]) -> Path:
    """Write batch/review.html for rows and return its path."""
    raise NotImplementedError
