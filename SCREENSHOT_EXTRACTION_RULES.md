# Screenshot Extraction Rules

This document defines how to convert a game screenshot into the JSON state format
used by the solver/editor.

Use this when building `*.json` from screenshots so the process is deterministic.

## 1. Coordinate + Grid Mapping

- External coordinates are `A1..H10` (`A1` top-left).
- JSON `grid` is always 10 rows x 8 cols.
- Fixed cells:
  - `A1 = "X"`
  - `B1..H1 = "#"`
  - `A2..A10 = "#"`
- Playable cells use:
  - `"."` unknown/empty
  - `"A".."Z"` visible letters

## 2. Clue Cell Capture

- Top-row clue tiles (`B1..H1`) are `S` clues.
- Left-column clue tiles (`A2..A10`) are `E` clues.
- Interior `#` tiles may define one or two clues:
  - if right arrow shown, include `E`
  - if down arrow shown, include `S`
- Geometry constraints for clue directions:
  - Any clue tile in column `H` can only be `S`.
  - Any clue tile in row `10` can only be `E`.
  - `H10` cannot be a clue tile (no legal outgoing slot).
  - Multi-clue (`E` + `S`) is only possible in `B2..G9`.
- Split clues are always ordered `E` then `S`.

## 3. Clue Text and Placeholder Normalization

- Preserve readable clue text verbatim as much as possible.
- Treat `...` and `_` as equivalent placeholder forms in clue text.  The
  placeholder represent the solution letters needed to complete the clue
  text's word/phrase.  e.g.  WIND__  could be WINDOW, WINDY, WINDMILL, etc.
  but the missing letters are still constrained by length for that slot.
- Do not infer slot length from underscore/ellipsis count.
- Slot length is constrained only by board geometry.

## 4. Picture Clues (`!=` policy)

When clue content is pictorial:

- Set human-readable clue text in `text` (example: `RAVEN (picture)`).
- Mark speculative answer via unknown fields:
  - `"unknown": true`
  - `"unknown_hint": "<candidate answer>"`
- In editor shorthand this corresponds to:
  - `<text> !=<candidate>`

Candidate selection policy:

- Use board-constrained slot length + direction first.
- Prefer the highest-confidence candidate that fits slot geometry.  Do this
  for picture clues as well as partial clues as well as word/phrase clues.
- Frequent solution types:
    - one, two, or three letter solutions are usually (but not always) the
      acronym of the words of the clue.
    - be careful with this, since sometimes a clue could have multiple
      meanings even for a single letter clue (e.g. SELF => I, not SELF => S)
- If uncertain, still provide best candidate and keep it speculative (`unknown`).
- If no viable candidate is found, use generic text and leave `unknown_hint`
  descriptive (example: `"unknown_hint": "bird silhouette"`).

## 5. Opponent Tile Marking

- Green letters on light-grey tile backgrounds indicate letters newly played by
  opponent.
- Those coordinates must be included in:
  - `"opponent_new_cells": ["..."]`
- These coordinates must also remain normal letters in `grid`.

## 6. Confidence + Ambiguity Handling

- If a letter is unreadable, keep `.` in `grid` unless strong cross evidence exists.
- If clue text is partially unreadable, keep best-effort literal text; do not invent
  certainty.
- Prefer deterministic tie-breakers:
  1. exact visual match
  2. slot length fit
  3. intersection consistency with visible letters

## 7. Canonical Worked Example

- Screenshot session Level 282 is captured in `282.json`.
