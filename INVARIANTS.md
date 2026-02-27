# INVARIANTS.md

This repo implements tooling for a competitive crossword-like board game.
These invariants are non-negotiable unless explicitly revised.

Use this as a checklist when changing parsing, slot extraction, scoring, or move gen.

---

## 1) Grid / Coordinates

- Grid is always **10 rows × 8 cols**.
- Columns are **A–H**, rows **1–10**.
- `A1` is always `"X"` and never editable as a clue or letter.
- Row 1 (B1–H1) cells are always `"#"`.
- Column A (A2–A10) cells are always `"#"`.
- All other cells are “interior” (row >= 2, col >= B in A1 terms; i.e., 0-based r>=1,c>=1).

**Never** let JSON or UI override those fixed cells.

---

## 2) Token Semantics

Allowed grid tokens:
- `"X"` dead UI
- `"#"` clue tile
- `"."` empty playable
- `"A"–"Z"` placed letter

**Never** introduce other tokens.

---

## 3) Words / Slot Extraction

- Words run only **E** or **S**.
- Slot starts at the cell adjacent to a clue tile in the slot direction.
- Slot continues until:
  - board edge, OR
  - next `"#"` tile.
- Slot cells are always interior playable cells (never include `#` or `X`).

Edge cases to handle:
- A clue could theoretically have **length 0** (immediately blocked by `#` or edge). Decide policy:
  - Either forbid and treat as invalid input, or allow but treat as a slot with no scoring.
  - Document which policy is used and test it.

---

## 4) Clue Data Contract

Clues are stored in JSON as:
- `cell: "C5"`
- `clues: [{dir:"E"|"S", text:"...", solution?:"WORD"}]`

Conventions:
- Two-clue tiles: always one E clue and one S clue.
- Fixed bands:
  - Row 1 clues are S-only.
  - Col A clues are E-only.

The editor may allow clue text to be empty; solver must tolerate it.

---

## 5) Meaning of `solution`

- `solution` is **knowledge**, not board state.
- It constrains letters in the slot but does not place them into `grid`.

Validation:
- If `solution` exists, and slot length is known:
  - Either enforce exact length match (recommended), or treat mismatch as error.
- If two constraints disagree on a cell, that is a contradiction:
  - surface clearly (error) rather than silently picking one.

---

## 6) Placement Legality (Phase A)

Phase A MUST NOT guess unknown letters.

Policy:
- Only recommend placements in cells where the letter is **forced** by constraints:
  - already on board, or
  - implied by `solution` propagation.

Moves that place letters in unconstrained cells are speculative and should be avoided in Phase A.

---

## 7) Scoring Invariants

### Tile points
- +1 point per valid placed tile.

### Word completion points
- A word scores ONLY when it becomes complete due to the current move.
- A word is complete when all its cells contain A–Z in the *post-move* grid.
- If a word was already complete before the move, it scores 0 this move.
- If one placement completes multiple words, score each.

### Word completion uses full word length
- When you complete a word, score = number of letters in that word.
- This is independent of how many letters you personally placed this move.

### Bonus
- +5 bonus only if:
  - rack size at start of turn == 5
  - AND placements_count == 5
- No “endgame bonus” when rack < 5.

### Invalid placements
- In actual game: invalid attempts are rejected and penalized -1 each.
- In solver: do not generate invalid moves.
- If you later simulate exploratory play, track penalties explicitly.

---

## 8) Move Application Invariants

- A move can place 0..len(rack) tiles.
- Placements must target distinct cells and only cells that are `"."` in grid.
- Applying a move should not mutate clue tiles or fixed bands.
- Applying a move should not reorder rack (rack is an unordered multiset for our purposes).

---

## 9) Risk / Opponent Heuristics (When Added)

Keep “risk” separate from “score”.
- Primary score = points you gain now.
- Risk heuristic = penalty for enabling opponent.

Start simple:
- Penalize leaving slots with exactly 1 empty cell (after your move).
- Optional: softer penalty for 2 empties.

Do not conflate risk with legality.

---

## 10) Output / CLI Invariants

For `suggest`:
- Always show:
  - placements (cell->letter)
  - tile points
  - word completion points
  - bonus
  - total

Maintain determinism:
- Sorting ties: stable and predictable (e.g., by total desc, then fewer tiles, then lexical).

---

## 11) Testing Must Cover

- Slot extraction at edges and near clue tiles.
- Intersection completion scoring (one tile completes two words).
- Completing a word that already has some letters placed (still scores full length).
- Bonus eligibility.
- Contradictory `solution` constraints.

---

## 12) “Do Not Break” List

- Never change coordinate meanings.
- Never change the meaning of `solution`.
- Never embed game logic into curses UI.
- Never recommend speculative letters in Phase A.
