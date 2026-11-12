"""Builder 3b. A review batch: batches/<name>/review.csv (schema.REVIEW_COLUMNS) and its stages.

Ported from the source pipeline's intake_stages.py. Every command that changes review.csv rewrites
review.html (sheet.write_page). Gates: review refuses an existing batch; approve needs an AI note on
every pending row unless --no-ai and approves only unflagged rows; records refuses pending rows
unless --allow-pending and records only approved rows.
"""
from __future__ import annotations
