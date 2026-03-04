import importlib.util
import pathlib
import unittest


def load_module():
    path = pathlib.Path(__file__).parent / "crossword-go-ai-solver.py"
    spec = importlib.util.spec_from_file_location("cw_solver", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


cw = load_module()


class UnknownClueTests(unittest.TestCase):
    def test_parse_single_unknown(self):
        items = cw.parse_clue_entry("!=a grey circle", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["dir"], "E")
        self.assertEqual(items[0]["text"], "")
        self.assertTrue(items[0]["unknown"])
        self.assertEqual(items[0]["unknown_hint"], "a grey circle")

    def test_parse_split_unknown_only_s(self):
        items = cw.parse_clue_entry("filler / !=maybe cola", [])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["dir"], "E")
        self.assertEqual(items[1]["dir"], "S")
        self.assertEqual(items[1]["text"], "")
        self.assertTrue(items[1]["unknown"])
        self.assertEqual(items[1]["unknown_hint"], "maybe cola")
        self.assertFalse(items[0].get("unknown", False))

    def test_parse_fixed_direction_preserves_unknown(self):
        items = cw.parse_clue_entry("!=context text", ["S"])
        self.assertEqual(items, [{"dir": "S", "text": "", "unknown": True, "unknown_hint": "context text"}])

    def test_parse_unknown_only_allowed(self):
        items = cw.parse_clue_entry("!=", [])
        self.assertEqual(items, [{"dir": "E", "text": "", "unknown": True}])

    def test_parse_split_unknown_only_allowed(self):
        items = cw.parse_clue_entry("!= / !=", [])
        self.assertEqual(
            items,
            [
                {"dir": "E", "text": "", "unknown": True},
                {"dir": "S", "text": "", "unknown": True},
            ],
        )

    def test_parse_split_mixed_directional_unknown(self):
        items = cw.parse_clue_entry("!=loose hint / target group s=TG", [])
        self.assertEqual(
            items,
            [
                {"dir": "E", "text": "", "unknown": True, "unknown_hint": "loose hint"},
                {"dir": "S", "text": "target group", "solution": "TG"},
            ],
        )

    def test_parse_clue_text_with_unknown_hint(self):
        items = cw.parse_clue_entry("picture clue !=grey circle", [])
        self.assertEqual(
            items,
            [{"dir": "E", "text": "picture clue", "unknown": True, "unknown_hint": "grey circle"}],
        )

    def test_parse_clue_text_with_solution(self):
        items = cw.parse_clue_entry("electric vehicle s=EV", [])
        self.assertEqual(items, [{"dir": "E", "text": "electric vehicle", "solution": "EV"}])

    def test_parse_unknown_and_solution_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown and solved"):
            cw.parse_clue_entry("!=maybe s=ABC", [])

    def test_parse_solution_marker_case_insensitive(self):
        items = cw.parse_clue_entry("target group S=tg", [])
        self.assertEqual(items, [{"dir": "E", "text": "target group", "solution": "TG"}])

    def test_bang_in_normal_text_is_literal(self):
        items = cw.parse_clue_entry("wow! clue", [])
        self.assertEqual(items, [{"dir": "E", "text": "wow! clue"}])

    def test_normalize_state_rejects_unknown_solution_conflict(self):
        state = {
            "grid": cw.make_initial_grid(),
            "rack": [],
            "clues": [
                {
                    "cell": "B1",
                    "clues": [{"dir": "S", "text": "hint", "unknown": True, "solution": "ABC"}],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "unknown clue cannot also have solution"):
            cw.validate_and_normalize_state(state)

    def test_normalize_state_keeps_unknown_flag(self):
        state = {
            "grid": cw.make_initial_grid(),
            "rack": ["A"],
            "clues": [
                {"cell": "B1", "clues": [{"dir": "S", "text": "shape", "unknown": True}]}
            ],
        }
        _, clue_map, _, _ = cw.validate_and_normalize_state(state)
        self.assertTrue(clue_map["B1"][0]["unknown"])

    def test_opponent_new_cells_roundtrip(self):
        grid = cw.make_initial_grid()
        grid[2][2] = "V"  # C3
        state = {
            "grid": grid,
            "rack": [],
            "clues": [],
            "opponent_new_cells": ["C3", "B2"],  # B2 is '.', should be filtered out
        }
        ng, clue_map, rack, opp = cw.validate_and_normalize_state(state)
        self.assertEqual(opp, {"C3"})
        out = cw.build_state_json(ng, clue_map, rack, opp)
        self.assertEqual(out["opponent_new_cells"], ["C3"])

    def test_apply_placements_updates_grid_rack_and_clears_opponent_metadata(self):
        grid = cw.make_initial_grid()
        state = {
            "grid": grid,
            "rack": ["A", "B", "C"],
            "clues": [],
            "opponent_new_cells": ["C3"],
        }
        out = cw.apply_placements_to_state(state, [("B2", "A"), ("C2", "B")])
        self.assertEqual(out["grid"][1][1], "A")  # B2
        self.assertEqual(out["grid"][1][2], "B")  # C2
        self.assertEqual(out["rack"], ["C"])
        self.assertEqual(out["opponent_new_cells"], [])

    def test_apply_placements_consumes_joker(self):
        grid = cw.make_initial_grid()
        state = {
            "grid": grid,
            "rack": ["?", "A"],
            "clues": [],
            "opponent_new_cells": [],
        }
        out = cw.apply_placements_to_state(state, [("B2", "Z")])
        self.assertEqual(out["grid"][1][1], "Z")
        self.assertEqual(out["rack"], ["A"])

    def test_joker_question_mark_roundtrip_persists(self):
        grid = cw.make_initial_grid()
        state = {"grid": grid, "rack": ["?"], "clues": []}
        ng, clue_map, rack, opp = cw.validate_and_normalize_state(state)
        self.assertEqual(rack, ["?"])
        out = cw.build_state_json(ng, clue_map, rack, opp)
        self.assertEqual(out["rack"], ["?"])

    def test_rack_allows_six_with_joker(self):
        grid = cw.make_initial_grid()
        state = {"grid": grid, "rack": ["A", "B", "C", "D", "E", "?"], "clues": []}
        _, _, rack, _ = cw.validate_and_normalize_state(state)
        self.assertEqual(rack, ["A", "B", "C", "D", "E", "?"])

    def test_rack_without_joker_truncates_to_five(self):
        grid = cw.make_initial_grid()
        state = {"grid": grid, "rack": ["A", "B", "C", "D", "E", "F"], "clues": []}
        _, _, rack, _ = cw.validate_and_normalize_state(state)
        self.assertEqual(rack, ["A", "B", "C", "D", "E"])

    def test_is_clue_complete(self):
        grid = cw.make_initial_grid()
        # A2:E spans B2..H2
        self.assertFalse(cw.is_clue_complete(grid, 1, 0, [{"dir": "E", "text": "across"}]))
        for col, ch in zip("BCDEFGH", "ABCDEFG"):
            r = 1
            c = cw.COL_LABELS.index(col)
            grid[r][c] = ch
        self.assertTrue(cw.is_clue_complete(grid, 1, 0, [{"dir": "E", "text": "across"}]))

    def test_clue_has_solution(self):
        self.assertFalse(cw.clue_has_solution([{"dir": "E", "text": "x"}]))
        self.assertTrue(cw.clue_has_solution([{"dir": "E", "text": "x", "solution": "EV"}]))


if __name__ == "__main__":
    unittest.main()
