import tomllib
import unittest

from helpers import CardFolder, PHOTOS
from cards import config


class Template(unittest.TestCase):
    def test_template_parses_and_matches_the_defaults(self):
        data = tomllib.loads(config.template("A \"Quoted\" Line", "AQL"))
        cfg = config.from_dict(data, PHOTOS)
        self.assertEqual(cfg.railroad_name, "A 'Quoted' Line")
        for key in ("roads", "car_types", "review", "locos"):
            for sub, value in config.DEFAULTS[key].items():
                self.assertEqual(data[key][sub], value, f"{key}.{sub}")
        self.assertIsNone(cfg.logo)


class Load(CardFolder):
    toml = '''
[[descriptions]]
type = "Hopper"
classes = ["LO"]
words = ["Covered"]
label = "Cov Hopper"
'''

    def test_rules_and_lookups(self):
        self.assertEqual(self.cfg.descriptions[0].words, ("covered",))
        self.assertEqual(self.cfg.car_type("Boxcar"), "Box Car")
        self.assertEqual(self.cfg.display_road("XX"), "XX")

    def test_unknown_key_is_refused(self):
        self.paths.config.write_text(self.paths.config.read_text().replace("[review]", "[review]\nblurr = 1"))
        with self.assertRaises(SystemExit) as err:
            config.load(self.tmp)
        self.assertIn("review.blurr", str(err.exception))

    def test_open_tables_take_any_key(self):
        cfg = config.from_dict({"roads": {"display": {"NW": "N&W"}, "aliases": {"now": "NW"}},
                                "sheet": {"margin_top": 0.2}}, self.tmp)
        self.assertEqual(cfg.display_road("NW"), "N&W")
        self.assertEqual(cfg.road_code("now"), "NW")
        self.assertEqual(cfg.road_code(" b o "), "BO")
        self.assertEqual(cfg.sheet, {"preset": "poker-3x3", "margin_top": 0.2})

    def test_missing_file(self):
        self.paths.config.unlink()
        with self.assertRaises(SystemExit):
            config.load(self.tmp)

    def test_paths_round_trip(self):
        p = self.paths.final / "x.png"
        self.assertEqual(self.paths.rel(p), "images/final/x.png")
        self.assertEqual(self.paths.resolve("images/final/x.png"), p)
        self.assertEqual(self.paths.rel(None), "")


if __name__ == "__main__":
    unittest.main()
