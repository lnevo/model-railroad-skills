"""review.html: editable, relative picture links, a storage key per batch, recorded rows read-only."""
import json
import re
import unittest
from unittest import mock

from helpers import CardFolder
from cards import picker, schema, sheet


def row(photo="x.jpg", **kw):
    r = {c: "" for c in schema.REVIEW_COLUMNS}
    r.update(photo=photo, kind="car", status="pending", reporting_marks="CSX", road_number="1")
    r.update(kw)
    return r


class Page(CardFolder):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(picker, "page_parts", return_value=("", "", ""))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.batch = self.paths.batch("b1")
        self.batch.mkdir(parents=True)

    def page(self, rows):
        return sheet.write_page(self.batch, rows).read_text(encoding="utf-8")

    def test_sheet_is_editable_and_keeps_every_column(self):
        text = self.page([row()])
        self.assertIn('data-f="road_number"', text)
        self.assertIn("Download review.csv", text)
        self.assertIn('"roster_id"', text)
        self.assertIn("<option selected>pending</option>", text)

    def test_picture_link_is_relative_to_the_batch_folder(self):
        text = self.page([row(image="images/final/x y.png")])
        self.assertIn('src="../../images/final/x%20y.png"', text)
        self.assertNotIn("file://", text)
        self.assertNotIn(str(self.tmp), text)

    def test_storage_key_has_batch_name_and_creation_time(self):
        key = lambda text: re.search(r'KEY=("[^"]+")', text).group(1)
        first = key(self.page([row()]))
        self.assertIn("b1", first)
        self.assertEqual(first, key(self.page([row()])))  # stable while the batch lives
        (self.batch / sheet.STAMP_FILE).write_text(json.dumps({"created": "later"}))
        self.assertNotEqual(first, key(self.page([row()])))

    def test_recorded_row_shows_status_read_only(self):
        text = self.page([row(status="recorded")])
        self.assertIn('data-f="status" value="recorded" readonly', text)
        self.assertNotIn("<select", text)
        self.assertIn("readonly", text.split('data-f="road_number"')[1][:80])

    def test_adjust_crop_button_only_for_photos_with_a_view(self):
        (self.batch / "picker.json").write_text(json.dumps({"x.jpg": {}}))
        text = self.page([row("x.jpg"), row("y.jpg")])
        self.assertEqual(text.count("Adjust crop</button>"), 1)

    def test_picker_parts_are_embedded(self):
        with mock.patch.object(picker, "page_parts", return_value=("/*css*/", "<div id=pk></div>", "/*js*/")):
            text = self.page([row()])
        for part in ("/*css*/", "<div id=pk></div>", "/*js*/"):
            self.assertIn(part, text)

    def test_text_is_escaped(self):
        text = self.page([row(note='<b>"x"</b>')])
        self.assertNotIn("<b>\"x\"", text)


if __name__ == "__main__":
    unittest.main()
