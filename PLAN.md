# PLAN.md

This document defines the next development steps.

The goal is to move from data-entry tooling → actionable move optimization.

---

# CURRENT STATE

Implemented:

- curses board editor
- JSON load/save
- rack editing
- clue entry + optional known solutions
- clue preview display

Missing:

- clue entry support for unknown clues
- solver
- slot extraction
- scoring engine
- move recommendation

---

# PHASE 0 - Implement Support For Unknown Clues

## Tasks

### 1. update the schema to indicate a clue is unknown

The clue text may still be useful as a hint.  Some clues are pictures and
the user may not know what the picture represents, but may give
some contextual info about it.  For example, "a grey circle" is not a useful
clue by itself, since the solution could be "DISC" or even simply the word
"GRAY".  The board state needs to track these separately.  Use "!" to
indicate an unknown clue, but still support entry of the clue text for it
like usual.  Entry key presses to indicate this are "!" or "1".

# PHASE 1 — Board Model + Slot Extraction

## Objective

Turn JSON into a fully structured internal model.

---

## Tasks

### 1. Coordinate utilities

Create:

- cell_to_rc("C5") -> (4,2)
- rc_to_cell(4,2) -> "C5"

---

### 2. Slot extraction

Given clue entries:

- walk in direction E or S
- collect cells until edge or #.

Output:

Slot object:

{
  id,
  clue_cell,
  dir,
  cells:[(r,c)...],
  length,
  known_letters,
  empty_cells
}

---

### 3. Intersection graph

Build:

cell -> slots containing cell

Needed later for constraint propagation.

---

### Deliverable

Function:

build_board_model(state) -> BoardModel

---

# PHASE 2 — Constraint Propagation

## Objective

Infer known letters.

Sources:

1. grid placed letters
2. clue.solution strings

---

## Rules

If clue has solution:

- slot length MUST match.
- each letter constrains corresponding cell.

Intersecting solved slots must agree.

Raise error on contradiction.  There should be no contradiction because that
means the potential solution word is invalid and cannot be played.  If there
is ambiguity, it's useful to indicate possible solutions (and may be useful
to track them until the ambiguity can be resolved via further play by
opponent or user.  For example COKE and COLA may both be suitable solutions
for a 4-letter clue of "fizzy drink", but only one of them can be correct
and that depends on the surrounding letters.

---

### Output

allowed_letters[cell]:

- fixed letter OR
- unknown.

---

# PHASE 3 — Move Scoring Engine

## Objective

Score hypothetical placements.

---

## Inputs

- current board
- rack
- placement set

---

## Must compute

1. tile points (+1 each)
2. newly completed words
3. completion score
4. +5 bonus if 5 tiles placed from full rack.

---

## Word completion rule

Score only if:

- slot incomplete before move
- slot complete after move

---

### Deliverable

score_move(state, move) -> ScoreBreakdown

---

# PHASE 4 — Move Generation (Phase A Policy)

## Policy

Only generate moves where letters are fully known.

No guessing.

---

## Generate

- all combinations of placing 0..N rack tiles
- only into forced cells.

---

## Output

Move:

{
  placements:[
    {"cell":"D6","letter":"T"}
  ],
  score,
  completed_slots
}

---

# PHASE 5 — Suggest Command

CLI:

cw suggest state.json --top 10

Output:

- top moves sorted by score
- breakdown:
  - tile points
  - word points
  - bonus

---

# PHASE 6 — Risk Heuristic (Simple)

Add heuristic penalties:

- leaving slots with 1 empty cell (high risk)
- leaving slots with 2 empties (moderate)

This approximates opponent opportunity.

---

# PHASE 7 — Tests

Required tests:

- slot extraction
- scoring edge cases
- intersection completion
- bonus logic

---

# FUTURE (NOT NOW)

- clue solving
- probabilistic bag modeling
- minimax / expectimax
- opponent inference

---

# SUCCESS CRITERIA

At end of Phase 5:

User workflow:

1. Edit board.
2. Save JSON.
3. Run:

   cw suggest state.json

4. Receive playable move recommendations.
