# AGENTS.md

This repository contains tooling for a competitive crossword-like board game.

This file is the authoritative handoff for agents (Codex CLI, AI assistants, etc.)
working on this repo.

The goal is deterministic, testable tooling — NOT prompt-only reasoning.

Before implementing any code change, read `INVARIANTS.md` when the work touches:
- board/token normalization
- clue parsing/representation
- solver model/constraints/scoring/move generation
- JSON contract or editor state transitions

---

# 1. Game Rules (Authoritative)

## Board layout

- Board size: **8 columns × 10 rows**
- Coordinates:
  - Columns: A–H
  - Rows: 1–10
  - A1 = top-left

### Fixed cells

- A1 is always `"X"` (dead UI cell).
- Row 1 (B1–H1) are clue tiles.
- Column A (A2–A10) are clue tiles.

These are not playable letter cells.

---

## Cell types

Grid tokens:

- `"X"` = dead UI cell (A1)
- `"#"` = clue tile
- `"."` = empty playable cell
- `"A"–"Z"` = placed letter

---

## Words

- Words run only:
  - East (left → right)
  - South (top → bottom)

- Every clue tile defines one or two words:
  - E direction
  - S direction

- Word starts adjacent to clue tile in arrow direction.
- Word continues until:
  - board edge, OR
  - another clue tile (`#`).

---

## Intersections

- Playable cells may belong to both an E word and an S word.
- Letter must satisfy both words.

---

## Tile mechanics

- Players have up to **5 tiles** in rack.
- On a turn, player may place 0–5 tiles.
- Tiles can be placed anywhere legal.
- No adjacency restrictions.

### Valid placement

A placement is valid if the letter matches the hidden board solution.

Game immediately validates:

- Invalid letter:
  - rejected
  - tile returns to rack
  - player loses 1 point per invalid attempt

---

## Scoring

### Tile score
- +1 point per valid tile placed.

### Word completion
- When a word becomes complete during your turn:
  - score = word length.
- Completed words are scored once only.
- If one placement completes multiple words, score each.

### Bonus
- +5 bonus if:
  - player started turn with 5 tiles
  - AND successfully placed all 5.

No bonus when rack < 5.

---

## End condition

Game ends when all playable cells are filled.

---

## Strategic goal

Primary:
- maximize own score.

Secondary:
- minimize opponent scoring opportunities.

Important consequence:
- Sometimes optimal play uses fewer than 5 tiles.

---

# 2. Repository Purpose

This repo is building:

1. A curses-based board editor.
2. A move-analysis / optimization engine.
3. Eventually a strong move recommendation system.

The editor already exists.
The solver is next.

---

# 3. JSON State Contract (CRITICAL)

All tooling MUST respect this schema.

Example:

{
  "size": {"cols":8,"rows":10},
  "rack": ["A","B","C","D","E"],
  "grid": [...10x8...],
  "clues": [
    {
      "cell":"C5",
      "clues":[
        {"dir":"E","text":"TARGET GROUP","solution":"TG"},
        {"dir":"S","text":"UPPER WEST","solution":"UW"}
      ]
    }
  ],
  "opponent_new_cells": ["C3","D6"]
}

---

## Fields

### size
Always:
- cols = 8
- rows = 10

---

### rack

Array of 0–5 uppercase letters.

Represents current player rack.

---

### grid

10 rows × 8 columns.

Allowed tokens:

- X
- #
- .
- A-Z

---

### clues

List of clue objects:

{
  "cell": "B1",
  "clues": [...]
}

Each clue entry:

{
  "dir": "E" | "S",
  "text": "...",
  "solution": "WORD" (optional),
  "unknown": true (optional),
  "unknown_hint": "..." (optional)
}

---

### opponent_new_cells

Optional metadata:
- list of cell labels for letters newly played by opponent.
- example: `["C3","D6"]`

This is metadata only (not a grid token).

---

## Meaning of `solution`

- Optional.
- Represents a known solved answer.
- DOES NOT imply letters are already placed.
- Used for constraint inference.

---

# 4. Clue conventions

Editor input:

- Single clue:
  clue text

- Split clue:
  clueE / clueS

Order is ALWAYS:
- first = E
- second = S

Optional known solution:

s=WORD

Optional unknown clue hint:

!=HINT

Examples:

P_ANO s=PIANO

TARGET GROUP s=TG / UPPER WEST s=UW

MAYBE A LOGO !=grey circle

Rules:
- `s=` and `!=` apply per clue direction (per segment).
- A single direction cannot be both solved and unknown.

---

# 5. Current Editor Behavior (Implemented)

Keyboard:

- Arrows: move cursor
- A-Z: set letter (interior only)
- 3: set #
- Space / Backspace: set .
- Enter:
  - "." → "#" + clue entry
  - "#" → edit clue
- Tab: toggle Edit/Suggest mode
- Ctrl-U: undo last committed suggested play (single-step)
- *: toggle opponent-new marker for a letter cell
- Ctrl-R: edit rack
- Ctrl-W: save in-place (stay in editor)
- Ctrl-O: output/dump and exit
- Ctrl-X: quit

Suggest mode:
- Shows top deterministic move options and live board preview.
- Enter commits selected move in-session (updates grid + rack).
- Committing a suggested move clears `opponent_new_cells`.

Header displays:

- rack
- cursor cell
- clue preview for current cell

Save behavior:

- if filename provided:
  - load on start
  - overwrite same file on save

---

# 6. Architectural Intent

This project should evolve into:

- deterministic engine
- testable modules
- minimal hidden state

DO NOT embed game logic inside curses UI.

---

# 7. Upcoming Solver Responsibilities

Solver must:

1. Parse JSON state.
2. Extract word slots from clues.
3. Build intersection graph.
4. Detect completion events.
5. Score moves.

Phase 1 uses only known constraints.

---

# 8. Constraint Model (IMPORTANT)

Known letters come from:

- already placed grid letters
- clues with `solution`

Unknown letters are NOT guessed in Phase 1.

Phase 1 policy:

- only suggest placements where letter is forced.

This prevents speculative illegal moves.

Risk model policy:
- Risk is a blended metric, not legality:
  - structural risk (near-complete slots left open)
  - estimated opponent next-turn expected score (`opponent_EV`)
- Blend weight is confidence-driven from current board knowledge
  (forced-letter coverage + opponent metadata quality).
- On highly solved boards, `opponent_EV` should dominate.

---

# 9. Non-Goals (for now)

Do NOT:

- attempt NLP clue solving yet
- model exact AI opponent
- perform deep minimax search

These come later.

---

# 10. Coding Expectations

- Small modules.
- Pure functions where possible.
- Avoid global mutable state.
- Coordinate helpers centralized.

---

# 11. Coordinate Rules

Internally preferred:

(row, col) zero-based.

Externally:

A1 notation.

Provide helpers both ways.

---

# 12. Future Direction (High-level)

Planned evolution:

Phase A:
- constraint-aware scoring

Phase B:
- clue solving integration

Phase C:
- probabilistic opponent modeling

Phase D:
- full move optimizer

---

# 13. Test + Validation Workflow

Use lightweight validation by default, and full suite when solver logic changes.

## Fast smoke checks (run for most edits)

- Syntax check:
  - `python3 -m py_compile crossword-go-ai-solver.py solver_model.py solver_constraints.py solver_scoring.py solver_moves.py`
- Quick core tests:
  - `python3 -m unittest -v test_solver_moves.py`

## Full regression suite (required for solver/model/scoring/constraint changes)

- `python3 -m unittest -v test_solver_model.py test_solver_constraints.py test_solver_scoring.py test_solver_moves.py test_phase0_unknown_clues.py`

## When to run what

- UI-only changes (drawing, keybindings, prompt UX): smoke checks are sufficient unless behavior touches state/normalization/scoring.
- Parser/normalization or JSON contract changes: run full regression suite.
- Constraint/scoring/move-ranking/risk changes: run full regression suite.
