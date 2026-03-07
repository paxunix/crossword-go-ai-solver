# INVARIANTS.md

Minimal repo invariants. Use this as a hard contract for solver/editor changes.

## 1) Board + Tokens
- Board is always `10x8` (rows x cols), coordinates `A1..H10`.
- Fixed cells are always enforced:
  - `A1 = "X"`
  - `B1..H1 = "#"`
  - `A2..A10 = "#"`
- Allowed grid tokens are only: `X`, `#`, `.`, `A-Z`.
- Rack tokens are `A-Z` plus special tile `?` (joker).
- Rack capacity is 5 normally, or 6 when one tile is `?`.

## 2) Slot Semantics
- Slots run only East (`E`) or South (`S`).
- Slot starts adjacent to clue tile and ends at edge or next `#`.
- Slot cells are interior playable cells only (`r>=1,c>=1`).
- Clue direction is geometry-constrained:
  - top row clue tiles (`B1..H1`) are `S` only
  - left column clue tiles (`A2..A10`) are `E` only
  - column `H` clue tiles are `S` only
  - row `10` clue tiles are `E` only
  - `H10` has no legal clue direction
- Multi-clue tiles (`E` + `S`) are only valid in `B2..G9`.
- Zero-length slots are invalid input (error).

## 3) Clue/Constraint Semantics
- `solution` is knowledge, not placed state.
- If `solution` exists, its length must match slot length.
- Contradicting constraints must raise errors (no silent conflict resolution).
- Duplicate clue directions in the same clue cell are invalid.
- Unknown clue marker is directional and uses `!=...` form.
- A single clue direction cannot be both unknown and solved (`unknown + solution` is invalid).

## 4) Move + Scoring
- Legal placements:
  - distinct target cells
  - only on `.` cells
  - letters available from rack multiset (with `?` wildcard support)
  - if `?` is present in rack, move must consume it
- Scoring:
  - `+1` per placed tile
  - word points only for slots that become complete this move
  - word score uses full slot length
  - `+5` bonus only when starting rack is full (`5` normal, `6` with `?`) and all rack tiles are placed

## 5) Determinism + Phase A Policy
- Phase A suggestions must be non-speculative:
  - only place forced letters.
- Suggestion ordering must be deterministic and stable.
- Keep legality, score, and risk as separate concepts.
- Risk may blend structural heuristics with opponent expected-value estimates,
  but must remain deterministic for identical input state.
- Prediction engines are selectable (`baseline`, `enhanced`).
- Enhanced risk may consume optional explicit opponent-pool metadata:
  - `opponent_pool_counts`, `opponent_pool`, `opponent_draw_count`.

## 6) Editor Session Behavior
- Undo (`Ctrl-U`) is in-session history (multi-step), not persisted in JSON.
- In check mode, inferred complete slots are selectable and can be applied to
  clue `solution` values via `Enter`.

## 7) Separation of Concerns
- Core game/solver logic stays out of curses UI.
- JSON state is the integration contract between editor and solver modules.

## 8) Validation Gate
- Any change to solver behavior (model, constraints, scoring, move generation) must keep the regression test suite passing.
