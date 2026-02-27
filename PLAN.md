# PLAN.md

This document tracks remaining work only.

## Current Status

Implemented:
- Editor with in-session `TAB` suggest mode and one-step undo (`Ctrl-U`).
- JSON load/save, clue/rack editing, unknown clue support (`!=...`), opponent marker metadata.
- Board model extraction (`solver_model.py`).
- Constraint propagation (`solver_constraints.py`).
- Move scoring (`solver_scoring.py`).
- Deterministic forced-letter move generation (`solver_moves.py`).
- Suggest command and interactive selection UI.

## Next Work

### 1. Risk Heuristic (Phase 6)
- Add a separate risk score (do not mix into legality).
- Start with penalties for leaving:
  - slots with 1 empty cell (high)
  - slots with 2 empty cells (moderate)
- Show both `total` and `risk` in suggest UI/list.
- Add deterministic tie-breaking with risk as an explicit key.

### 2. Suggest Quality / UX Refinement
- Add optional sort modes:
  - score-first (default)
  - risk-aware
- Improve suggest panel readability for long placement lists (compact rendering / truncation).
- Optional: show why a move is legal (forced cells source).

### 3. CLI Contract Hardening
- Add a stable machine-readable suggest output mode (`--json`).
- Include full breakdown fields in JSON output.
- Keep text output deterministic and human-friendly.

### 4. Test Expansion
- Add regression tests for integrated edit/suggest mode flow:
  - `TAB` recompute after edits
  - commit move updates rack/grid and clears opponent markers
  - `Ctrl-U` undo restores exact prior state
- Add move-generation edge cases:
  - duplicate rack letters
  - zero legal forced placements
  - pass move handling

## Not In Scope (for now)
- NLP clue solving.
- Opponent probabilistic modeling.
- Minimax/expectimax search.
