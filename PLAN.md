# PLAN.md

This document tracks remaining work only.

## Current Status

Implemented:
- Editor-first loop:
  - edit board/rack/clues
  - `TAB` to in-session suggestions
  - commit suggested move in-session
  - continue editing for opponent turn
- One-step undo of committed suggestion (`Ctrl-U`).
- Save/output controls:
  - `Ctrl-W` save in-place
  - `Ctrl-O` output/dump and exit
  - `Ctrl-X` quit with single-key unsaved prompt (`s/d/c/Esc`)
- JSON load/save with clue metadata and opponent marker metadata.
- Clue parsing supports directional `s=...` and `!=...`.
- Board model extraction (`solver_model.py`).
- Constraint propagation (`solver_constraints.py`).
- Move scoring (`solver_scoring.py`).
- Deterministic forced-letter move generation (`solver_moves.py`).
- Suggest command and interactive selection UI (standalone + integrated).
- Risk heuristic:
  - post-move penalties for leaving slots with 1 empty cell (high) or 2 empty cells (moderate)
  - risk shown alongside score in suggest outputs/UI
  - optional risk-aware sorting (`suggest --sort risk`, in-editor `S` toggle in Suggest mode)

## Next Work

### 1. Test Expansion (integration-heavy)
- Add regression tests for integrated edit/suggest mode flow:
  - `TAB` recompute after edits/rack/clue changes
  - commit move updates rack/grid and clears opponent markers
  - `Ctrl-U` undo restores exact prior state
- Add prompt/editor control regressions:
  - single-key unsaved prompt behavior
  - `Esc` prompt cancel behavior
  - `Ctrl-C` no-traceback behavior

### 2. Performance/Scale Safety
- Add guardrails for move generation on dense forced states (avoid UI stalls).
- Add optional cap/logging for candidate enumeration size.

## Not In Scope (for now)
- NLP clue solving.
- Opponent probabilistic modeling.
- Minimax/expectimax search.
