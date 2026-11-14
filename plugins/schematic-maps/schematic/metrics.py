"""Text widths for the drawing's sans-serif lettering, so labels are measured the same on every machine.

Advance widths in thousandths of an em for the printable ASCII characters (32 to 126), regular and bold,
for a Helvetica-style face. The drawing names a family list (Helvetica Neue, Helvetica, Arial), so the
numbers are close for whichever one the viewer has. No font file is read: a missing system font cannot
change where a label is placed, and the tests give the same answer on Linux, macOS and Windows.
"""

REGULAR = (
    278, 259, 426, 556, 556, 1000, 630, 278, 259, 259, 352, 600,
    278, 389, 278, 333, 556, 556, 556, 556, 556, 556, 556, 556,
    556, 556, 278, 278, 600, 600, 600, 556, 800, 648, 685, 722,
    704, 611, 574, 759, 722, 259, 519, 667, 556, 871, 722, 760,
    648, 760, 685, 648, 574, 722, 611, 926, 611, 648, 611, 259,
    333, 259, 600, 500, 222, 537, 593, 537, 593, 537, 296, 574,
    556, 222, 222, 519, 222, 853, 556, 574, 593, 593, 333, 500,
    315, 556, 500, 758, 518, 500, 480, 333, 222, 333, 600,
)
BOLD = (
    278, 278, 463, 556, 556, 1000, 685, 278, 296, 296, 407, 600,
    278, 407, 278, 371, 556, 556, 556, 556, 556, 556, 556, 556,
    556, 556, 278, 278, 600, 600, 600, 556, 800, 685, 704, 741,
    741, 648, 593, 759, 741, 295, 556, 722, 593, 907, 741, 778,
    667, 778, 722, 649, 611, 741, 630, 944, 667, 667, 648, 333,
    371, 333, 600, 500, 259, 574, 611, 574, 611, 574, 333, 611,
    593, 258, 278, 574, 258, 906, 593, 611, 611, 611, 389, 537,
    352, 593, 520, 814, 537, 519, 519, 333, 223, 333, 600,
)
FALLBACK = {"normal": 556, "bold": 600}      # any character outside printable ASCII


def text_width(s, size, weight="normal", spacing=0.0):
    """Width in drawing units of s at font size `size`, plus letter spacing between characters."""
    table = BOLD if weight == "bold" else REGULAR
    em = sum(table[ord(c) - 32] if 32 <= ord(c) < 127 else FALLBACK["bold" if weight == "bold" else "normal"]
             for c in s)
    return em * size / 1000.0 + spacing * max(len(s) - 1, 0)
