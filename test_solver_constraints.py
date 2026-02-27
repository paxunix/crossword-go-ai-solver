import unittest

from solver_constraints import propagate_constraints
from solver_model import cell_to_rc


def make_initial_grid():
    g = [["." for _ in range(8)] for _ in range(10)]
    g[0][0] = "X"
    for c in range(1, 8):
        g[0][c] = "#"
    for r in range(1, 10):
        g[r][0] = "#"
    return g


class SolverConstraintTests(unittest.TestCase):
    def test_propagate_solutions_and_intersection(self):
        state = {
            "grid": make_initial_grid(),
            "clues": [
                {"cell": "B1", "clues": [{"dir": "S", "text": "down", "solution": "BCDEFGHIJ"}]},
                {"cell": "A2", "clues": [{"dir": "E", "text": "across", "solution": "BCDEFGH"}]},
            ],
        }
        out = propagate_constraints(state)
        self.assertEqual(out.forced_letters[cell_to_rc("B2")], "B")
        self.assertEqual(out.forced_letters[cell_to_rc("C2")], "C")
        self.assertEqual(out.allowed_letters[cell_to_rc("H2")], "H")

    def test_solution_length_mismatch_rejected(self):
        state = {
            "grid": make_initial_grid(),
            "clues": [
                {"cell": "B1", "clues": [{"dir": "S", "text": "down", "solution": "ABC"}]},
            ],
        }
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            propagate_constraints(state)

    def test_intersection_contradiction_rejected(self):
        state = {
            "grid": make_initial_grid(),
            "clues": [
                {"cell": "B1", "clues": [{"dir": "S", "text": "down", "solution": "ACDEFGHIJ"}]},
                {"cell": "A2", "clues": [{"dir": "E", "text": "across", "solution": "BCDEFGH"}]},
            ],
        }
        with self.assertRaisesRegex(ValueError, "contradiction"):
            propagate_constraints(state)

    def test_grid_solution_contradiction_rejected(self):
        grid = make_initial_grid()
        r, c = cell_to_rc("B2")
        grid[r][c] = "Z"
        state = {
            "grid": grid,
            "clues": [
                {"cell": "B1", "clues": [{"dir": "S", "text": "down", "solution": "ACDEFGHIJ"}]},
            ],
        }
        with self.assertRaisesRegex(ValueError, "contradiction"):
            propagate_constraints(state)


if __name__ == "__main__":
    unittest.main()
