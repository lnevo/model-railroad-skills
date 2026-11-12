"""Builder 3b. The `cards` command. Subcommands:

  init [--name NAME] [--short NAME]   make cards.toml and the folders here
  review [--batch NAME]               crop and read new photos in photos/incoming/, write a batch
  ai-notes BATCH FILE                 merge the photo-reader agent's JSON into the batch
  sheet-import BATCH FILE             take the review.csv downloaded from review.html
  fill BATCH PHOTO --set COL=VALUE..  set fields from the command line
  kind BATCH car|loco PHOTO..         switch photos between car and locomotive
  crop BATCH [PHOTO BOX] [--refresh]  re-cut one picture (box from the page), or rebuild the views
  approve BATCH [--no-ai]             approve the unflagged rows
  records BATCH [--dry-run] [--allow-pending]   write approved rows to data/
  locos set ID COL=VALUE.. | locos status       locomotive details a photo cannot give
  print [--all] [--calibrate] [--mark-printed]  cards not yet printed -> output/cards_<date>.docx
  status                              batches, fleet counts and cards waiting to print
"""
from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError
