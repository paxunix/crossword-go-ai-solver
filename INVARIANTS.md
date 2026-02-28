# INVARIANTS.md

Minimal repo invariants. Use this as a hard contract for solver/editor changes.

## 1) Board + Tokens
- Board is always `10x8` (rows x cols), coordinates `A1..H10`.
- Fixed cells are always enforced:
  - `A1 = "X"`
  - `B1..H1 = "#"`
  - `A2..A10 = "#"`
- Allowed grid tokens are only: `X`, `#`, `.`, `A-Z`.

## 2) Slot Semantics
- Slots run only East (`E`) or South (`S`).
- Slot starts adjacent to clue tile and ends at edge or next `#`.
- Slot cells are interior playable cells only (`r>=1,c>=1`).
- Zero-length slots are invalid input (error).

## 3) Clue/Constraint Semantics
- `solution` is knowledge, not placed state.
- If `solution` exists, its length must match slot length.
- Contradicting constraints must raise errors (no silent conflict resolution).
- Unknown clue marker is directional and uses `!=...` form.
- A single clue direction cannot be both unknown and solved (`unknown + solution` is invalid).

## 4) Move + Scoring
- Legal placements:
  - distinct target cells
  - only on `.` cells
  - letters available from rack multiset
- Scoring:
  - `+1` per placed tile
  - word points only for slots that become complete this move
  - word score uses full slot length
  - `+5` bonus only when start rack size is 5 and exactly 5 tiles are placed

## 5) Determinism + Phase A Policy
- Phase A suggestions must be non-speculative:
  - only place forced letters.
- Suggestion ordering must be deterministic and stable.
- Keep legality, score, and any future risk heuristic as separate concepts.

## 6) Separation of Concerns
- Core game/solver logic stays out of curses UI.
- JSON state is the integration contract between editor and solver modules.

## 7) Validation Gate
- Any change to solver behavior (model, constraints, scoring, move generation) must keep the regression test suite passing.
