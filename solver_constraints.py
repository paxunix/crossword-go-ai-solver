from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from solver_model import (
    BoardModel,
    COLS,
    ROWS,
    build_board_model,
    rc_to_cell,
)


@dataclass(frozen=True)
class ConstraintResult:
    model: BoardModel
    forced_letters: Dict[Tuple[int, int], str]
    allowed_letters: Dict[Tuple[int, int], Optional[str]]


def _parse_solution_constraints(state: dict) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for clue_entry in state.get("clues", []):
        cell = str(clue_entry.get("cell", "")).strip().upper()
        if not cell:
            continue
        for clue in clue_entry.get("clues", []):
            direction = str(clue.get("dir", "")).strip().upper()
            if direction not in {"E", "S"}:
                continue

            sol = clue.get("solution")
            if not sol:
                continue
            s = str(sol).strip().upper()
            if not s or any(not ("A" <= ch <= "Z") for ch in s):
                raise ValueError(f"invalid solution for {cell}:{direction}")

            slot_id = f"{cell}:{direction}"
            prev = out.get(slot_id)
            if prev and prev != s:
                raise ValueError(f"conflicting solutions for {slot_id}")
            out[slot_id] = s
    return out


def propagate_constraints(state: dict) -> ConstraintResult:
    model = build_board_model(state)
    solutions = _parse_solution_constraints(state)
    forced: Dict[Tuple[int, int], str] = {}

    def assign_letter(rc: Tuple[int, int], letter: str, source: str):
        prev = forced.get(rc)
        if prev and prev != letter:
            cell = rc_to_cell(*rc)
            raise ValueError(
                f"contradiction at {cell}: '{prev}' vs '{letter}' ({source})"
            )
        forced[rc] = letter

    # Grid letters are hard constraints.
    for r in range(1, ROWS):
        for c in range(1, COLS):
            tok = model.grid[r][c]
            if "A" <= tok <= "Z":
                assign_letter((r, c), tok, "grid")

    # Known slot solutions constrain each slot position.
    for slot in model.slots:
        sol = solutions.get(slot.id)
        if not sol:
            continue
        if len(sol) != slot.length:
            raise ValueError(
                f"solution length mismatch for {slot.id}: got {len(sol)} expected {slot.length}"
            )
        for rc, ch in zip(slot.cells, sol):
            assign_letter(rc, ch, f"solution {slot.id}")

    allowed: Dict[Tuple[int, int], Optional[str]] = {}
    for r in range(1, ROWS):
        for c in range(1, COLS):
            tok = model.grid[r][c]
            if tok == "#":
                continue
            allowed[(r, c)] = forced.get((r, c))

    return ConstraintResult(
        model=model,
        forced_letters=forced,
        allowed_letters=allowed,
    )
