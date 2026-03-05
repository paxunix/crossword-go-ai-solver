import unittest

from solver_model import cell_to_rc
from solver_scoring import score_move


def make_initial_grid():
    g = [["." for _ in range(8)] for _ in range(10)]
    g[0][0] = "X"
    for c in range(1, 8):
        g[0][c] = "#"
    for r in range(1, 10):
        g[r][0] = "#"
    return g


class SolverScoringTests(unittest.TestCase):
    def test_single_tile_completes_two_words(self):
        grid = make_initial_grid()
        # Fill B-column except B2.
        for row, ch in zip(range(3, 11), "CDEFGHIJ"):
            r, c = cell_to_rc(f"B{row}")
            grid[r][c] = ch
        # Fill row 2 from C2..H2 except B2.
        for col, ch in zip("CDEFGH", "CDEFGH"):
            r, c = cell_to_rc(f"{col}2")
            grid[r][c] = ch

        state = {
            "rack": ["B"],
            "grid": grid,
            "clues": [
                {"cell": "B1", "clues": [{"dir": "S", "text": "down"}]},
                {"cell": "A2", "clues": [{"dir": "E", "text": "across"}]},
            ],
        }
        move = {"placements": [{"cell": "B2", "letter": "B"}]}
        out = score_move(state, move)
        self.assertEqual(out.tile_points, 1)
        self.assertEqual(out.word_points, 16)  # len(B1:S)=9 + len(A2:E)=7
        self.assertEqual(out.total, 17)
        self.assertEqual(out.completed_slots, ("B1:S", "A2:E"))

    def test_word_scoring_uses_full_word_length(self):
        grid = make_initial_grid()
        for col, ch in zip("BCDEFG", "BCDEFG"):
            r, c = cell_to_rc(f"{col}2")
            grid[r][c] = ch

        state = {
            "rack": ["H"],
            "grid": grid,
            "clues": [{"cell": "A2", "clues": [{"dir": "E", "text": "across"}]}],
        }
        out = score_move(state, {"placements": [{"cell": "H2", "letter": "H"}]})
        self.assertEqual(out.tile_points, 1)
        self.assertEqual(out.word_points, 7)
        self.assertEqual(out.total, 8)

    def test_already_complete_word_scores_zero(self):
        grid = make_initial_grid()
        for col, ch in zip("BCDEFGH", "BCDEFGH"):
            r, c = cell_to_rc(f"{col}2")
            grid[r][c] = ch

        state = {
            "rack": ["Z"],
            "grid": grid,
            "clues": [{"cell": "A2", "clues": [{"dir": "E", "text": "across"}]}],
        }
        # Place elsewhere; no completion points should be re-awarded.
        out = score_move(state, {"placements": [{"cell": "B3", "letter": "Z"}]})
        self.assertEqual(out.word_points, 0)
        self.assertEqual(out.tile_points, 1)
        self.assertEqual(out.total, 1)

    def test_bonus_requires_full_rack_and_five_placements(self):
        state = {
            "rack": ["A", "B", "C", "D", "E"],
            "grid": make_initial_grid(),
            "clues": [],
        }
        out = score_move(
            state,
            {
                "placements": [
                    {"cell": "B2", "letter": "A"},
                    {"cell": "C2", "letter": "B"},
                    {"cell": "D2", "letter": "C"},
                    {"cell": "E2", "letter": "D"},
                    {"cell": "F2", "letter": "E"},
                ]
            },
        )
        self.assertEqual(out.tile_points, 5)
        self.assertEqual(out.bonus, 5)
        self.assertEqual(out.total, 10)

    def test_bonus_applies_for_full_six_tile_rack_with_joker(self):
        state = {
            "rack": ["?", "A", "B", "C", "D", "E"],
            "grid": make_initial_grid(),
            "clues": [],
        }
        out = score_move(
            state,
            {
                "placements": [
                    {"cell": "B2", "letter": "Z"},
                    {"cell": "C2", "letter": "A"},
                    {"cell": "D2", "letter": "B"},
                    {"cell": "E2", "letter": "C"},
                    {"cell": "F2", "letter": "D"},
                    {"cell": "G2", "letter": "E"},
                ]
            },
        )
        self.assertEqual(out.tile_points, 6)
        self.assertEqual(out.bonus, 5)
        self.assertEqual(out.total, 11)

    def test_invalid_placement_on_non_empty_cell(self):
        grid = make_initial_grid()
        r, c = cell_to_rc("B2")
        grid[r][c] = "A"
        state = {"rack": ["B"], "grid": grid, "clues": []}
        with self.assertRaisesRegex(ValueError, "target empty"):
            score_move(state, {"placements": [{"cell": "B2", "letter": "B"}]})

    def test_joker_can_satisfy_any_required_letter(self):
        grid = make_initial_grid()
        state = {"rack": ["?"], "grid": grid, "clues": []}
        out = score_move(state, {"placements": [{"cell": "B2", "letter": "Z"}]})
        self.assertEqual(out.tile_points, 1)

    def test_joker_must_be_played_when_in_rack(self):
        grid = make_initial_grid()
        state = {"rack": ["?"], "grid": grid, "clues": []}
        with self.assertRaisesRegex(ValueError, "must play special tile"):
            score_move(state, {"placements": []})


if __name__ == "__main__":
    unittest.main()
