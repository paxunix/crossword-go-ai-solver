import unittest

from solver_model import build_board_model, cell_to_rc, rc_to_cell


def make_initial_grid():
    g = [["." for _ in range(8)] for _ in range(10)]
    g[0][0] = "X"
    for c in range(1, 8):
        g[0][c] = "#"
    for r in range(1, 10):
        g[r][0] = "#"
    return g


class SolverModelTests(unittest.TestCase):
    def test_coordinate_roundtrip(self):
        self.assertEqual(cell_to_rc("C5"), (4, 2))
        self.assertEqual(rc_to_cell(4, 2), "C5")

    def test_slot_extraction_and_intersection_graph(self):
        grid = make_initial_grid()
        grid[1][1] = "#"  # B2 interior clue

        state = {
            "size": {"cols": 8, "rows": 10},
            "grid": grid,
            "clues": [
                {"cell": "B2", "clues": [{"dir": "E", "text": "row clue"}]},
                {"cell": "C1", "clues": [{"dir": "S", "text": "col clue"}]},
            ],
        }
        model = build_board_model(state)

        slot_ids = [s.id for s in model.slots]
        self.assertEqual(slot_ids, ["C1:S", "B2:E"])

        c2 = cell_to_rc("C2")
        self.assertEqual(model.cell_to_slots[c2], ("C1:S", "B2:E"))

        b2_e = next(s for s in model.slots if s.id == "B2:E")
        self.assertEqual(b2_e.length, 6)
        self.assertEqual(b2_e.cells[0], cell_to_rc("C2"))
        self.assertEqual(b2_e.cells[-1], cell_to_rc("H2"))

    def test_zero_length_slot_rejected(self):
        grid = make_initial_grid()
        grid[1][1] = "#"  # B2 clue tile
        grid[1][2] = "#"  # C2 blocks E immediately

        state = {
            "grid": grid,
            "clues": [{"cell": "B2", "clues": [{"dir": "E", "text": "blocked"}]}],
        }
        with self.assertRaisesRegex(ValueError, "zero-length slot"):
            build_board_model(state)

    def test_column_h_clue_is_s_only(self):
        grid = make_initial_grid()
        grid[5][7] = "#"  # H6 interior edge clue tile
        state = {
            "grid": grid,
            "clues": [{"cell": "H6", "clues": [{"dir": "E", "text": "invalid"}]}],
        }
        with self.assertRaisesRegex(ValueError, "not allowed"):
            build_board_model(state)

    def test_row_10_clue_is_e_only(self):
        grid = make_initial_grid()
        grid[9][2] = "#"  # C10 interior edge clue tile
        state = {
            "grid": grid,
            "clues": [{"cell": "C10", "clues": [{"dir": "S", "text": "invalid"}]}],
        }
        with self.assertRaisesRegex(ValueError, "not allowed"):
            build_board_model(state)

    def test_h10_has_no_legal_direction(self):
        grid = make_initial_grid()
        grid[9][7] = "#"  # H10
        state = {
            "grid": grid,
            "clues": [{"cell": "H10", "clues": [{"dir": "E", "text": "invalid"}]}],
        }
        with self.assertRaisesRegex(ValueError, "not allowed"):
            build_board_model(state)

    def test_duplicate_direction_rejected(self):
        grid = make_initial_grid()
        grid[1][1] = "#"  # B2
        state = {
            "grid": grid,
            "clues": [
                {"cell": "B2", "clues": [{"dir": "E", "text": "one"}, {"dir": "E", "text": "two"}]}
            ],
        }
        with self.assertRaisesRegex(ValueError, "duplicate direction"):
            build_board_model(state)


if __name__ == "__main__":
    unittest.main()
