import unittest

from solver_moves import generate_forced_moves, prediction_engines


def make_initial_grid():
    g = [["." for _ in range(8)] for _ in range(10)]
    g[0][0] = "X"
    for c in range(1, 8):
        g[0][c] = "#"
    for r in range(1, 10):
        g[r][0] = "#"
    return g


class SolverMovesTests(unittest.TestCase):
    def test_prediction_engines_include_baseline_and_enhanced(self):
        engines = prediction_engines()
        self.assertIn("baseline", engines)
        self.assertIn("enhanced", engines)

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

    def test_generate_forced_moves_uses_joker_and_no_pass(self):
        grid = make_initial_grid()
        grid[2][3] = "#"  # D3 blocks A3:E to length 2 (B3,C3)
        state = {
            "rack": ["?"],
            "grid": grid,
            "clues": [
                {"cell": "A3", "clues": [{"dir": "E", "text": "", "solution": "EV"}]},
            ],
        }
        moves = generate_forced_moves(state, top=10)
        placement_sets = [m.placements for m in moves]
        self.assertNotIn(tuple(), placement_sets)
        self.assertIn((("B3", "E"),), placement_sets)
        self.assertIn((("C3", "V"),), placement_sets)

    def test_generate_forced_moves_no_pass_when_joker_present_with_other_tiles(self):
        grid = make_initial_grid()
        grid[2][3] = "#"  # D3 blocks A3:E to length 2 (B3,C3)
        state = {
            "rack": ["?", "X", "Y"],
            "grid": grid,
            "clues": [
                {"cell": "A3", "clues": [{"dir": "E", "text": "", "solution": "EV"}]},
            ],
        }
        moves = generate_forced_moves(state, top=20)
        placement_sets = [m.placements for m in moves]
        self.assertNotIn(tuple(), placement_sets)

    def test_generate_forced_moves_marks_joker_cell(self):
        grid = make_initial_grid()
        grid[2][3] = "#"  # D3 blocks A3:E to length 2 (B3,C3)
        state = {
            "rack": ["?"],
            "grid": grid,
            "clues": [
                {"cell": "A3", "clues": [{"dir": "E", "text": "", "solution": "EV"}]},
            ],
        }
        moves = generate_forced_moves(state, top=10)
        by_place = {m.placements: m for m in moves}
        self.assertEqual(by_place[(("B3", "E"),)].joker_cells, ("B3",))
        self.assertEqual(by_place[(("C3", "V"),)].joker_cells, ("C3",))

    def test_enhanced_prediction_engine_adjusts_risk_with_speculative_clues(self):
        grid = make_initial_grid()
        grid[2][3] = "#"  # D3 blocks A3:E to length 2 (B3,C3)
        grid[3][4] = "#"  # E4 blocks A4:E to length 3 (B4,C4,D4)
        state = {
            "rack": ["V", "X"],
            "grid": grid,
            "clues": [
                {"cell": "A3", "clues": [{"dir": "E", "text": "", "solution": "EV"}]},
                {"cell": "A4", "clues": [{"dir": "E", "text": "unknown lane", "unknown": True, "unknown_hint": "ABC"}]},
            ],
            "opponent_new_cells": ["B2"],
        }
        baseline = generate_forced_moves(state, top=20, sort_mode="score", prediction_engine="baseline")
        enhanced = generate_forced_moves(state, top=20, sort_mode="score", prediction_engine="enhanced")
        b_map = {m.placements: m.risk_penalty for m in baseline}
        e_map = {m.placements: m.risk_penalty for m in enhanced}
        self.assertIn((("C3", "V"),), b_map)
        self.assertIn((("C3", "V"),), e_map)
        self.assertNotEqual(b_map[(("C3", "V"),)], e_map[(("C3", "V"),)])

    def test_enhanced_prediction_engine_differs_on_fully_known_early_board(self):
        grid = make_initial_grid()
        state = {
            "rack": ["B", "C", "X", "Y", "Z"],
            "grid": grid,
            "clues": [
                {"cell": "A2", "clues": [{"dir": "E", "text": "", "solution": "BCDEFGH"}]},
                {"cell": "B1", "clues": [{"dir": "S", "text": "", "solution": "BCDEFGHIJ"}]},
            ],
        }
        baseline = generate_forced_moves(state, top=20, sort_mode="score", prediction_engine="baseline")
        enhanced = generate_forced_moves(state, top=20, sort_mode="score", prediction_engine="enhanced")
        b_map = {m.placements: m.risk_penalty for m in baseline}
        e_map = {m.placements: m.risk_penalty for m in enhanced}
        target = (("B2", "B"),)
        self.assertIn(target, b_map)
        self.assertIn(target, e_map)
        self.assertNotEqual(b_map[target], e_map[target])


if __name__ == "__main__":
    unittest.main()
