import unittest

from solver_moves import generate_forced_moves


def make_initial_grid():
    g = [["." for _ in range(8)] for _ in range(10)]
    g[0][0] = "X"
    for c in range(1, 8):
        g[0][c] = "#"
    for r in range(1, 10):
        g[r][0] = "#"
    return g


class SolverMovesTests(unittest.TestCase):
    def test_generate_forced_moves_includes_pass_and_scored_move(self):
        grid = make_initial_grid()
        grid[2][3] = "#"  # D3 blocks A3:E to length 2 (B3,C3)
        state = {
            "rack": ["V", "X"],
            "grid": grid,
            "clues": [
                {"cell": "A3", "clues": [{"dir": "E", "text": "", "solution": "EV"}]},
            ],
        }
        moves = generate_forced_moves(state, top=10)
        placement_sets = [m.placements for m in moves]
        self.assertIn(tuple(), placement_sets)  # pass
        self.assertIn((("C3", "V"),), placement_sets)

    def test_generate_forced_moves_sorted_deterministically(self):
        grid = make_initial_grid()
        grid[2][3] = "#"  # D3
        grid[3][4] = "#"  # E4, so A4:E is B4..D4 length 3
        state = {
            "rack": ["V", "C", "D"],
            "grid": grid,
            "clues": [
                {"cell": "A3", "clues": [{"dir": "E", "text": "", "solution": "EV"}]},
                {"cell": "A4", "clues": [{"dir": "E", "text": "", "solution": "CDM"}]},
            ],
        }
        moves = generate_forced_moves(state, top=10)
        totals = [m.total for m in moves]
        self.assertEqual(totals, sorted(totals, reverse=True))

        # Tie-break uses fewer tiles first, then lexical placement order.
        tied = [m for m in moves if m.total == moves[-1].total]
        if len(tied) >= 2:
            sizes = [len(m.placements) for m in tied]
            self.assertEqual(sizes, sorted(sizes))


if __name__ == "__main__":
    unittest.main()
