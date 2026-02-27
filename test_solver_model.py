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


if __name__ == "__main__":
    unittest.main()
