from dataclasses import dataclass
from typing import Dict, List, Tuple

from solver_model import build_board_model, cell_to_rc
from tile_rules import consume_rack_for_letters, normalize_rack_items


@dataclass(frozen=True)
class ScoreBreakdown:
    placements: Tuple[Tuple[str, str], ...]
    tile_points: int
    word_points: int
    bonus: int
    total: int
    completed_slots: Tuple[str, ...]


def _normalize_rack(state: dict) -> List[str]:
    return normalize_rack_items(state.get("rack", []))


def _normalize_placements(move: dict) -> List[Tuple[str, str]]:
    out = []
    for p in move.get("placements", []):
        cell = str(p.get("cell", "")).strip().upper()
        letter = str(p.get("letter", "")).strip().upper()
        if len(letter) != 1 or not ("A" <= letter <= "Z"):
            raise ValueError(f"invalid placement letter at {cell}: {letter}")
        out.append((cell, letter))
    return out


def _slot_complete(grid: List[List[str]], cells: Tuple[Tuple[int, int], ...]) -> bool:
    for r, c in cells:
        ch = grid[r][c]
        if not ("A" <= ch <= "Z"):
            return False
    return True


def score_move(state: dict, move: dict) -> ScoreBreakdown:
    model = build_board_model(state)
    rack = _normalize_rack(state)
    placements = _normalize_placements(move)

    if len(placements) > len(rack):
        raise ValueError("placements exceed rack size")

    # Enforce rack/special-tile availability and special-tile round rules.
    consume_rack_for_letters(rack, [letter for _, letter in placements], enforce_special_rules=True)

    # Validate placements and apply to a copy.
    post = [row[:] for row in model.grid]
    seen = set()
    for cell, letter in placements:
        if cell in seen:
            raise ValueError(f"duplicate placement cell: {cell}")
        seen.add(cell)
        r, c = cell_to_rc(cell)
        if model.grid[r][c] != ".":
            raise ValueError(f"placement must target empty '.' cell: {cell}")
        post[r][c] = letter

    before_complete: Dict[str, bool] = {}
    after_complete: Dict[str, bool] = {}
    for slot in model.slots:
        before_complete[slot.id] = _slot_complete(model.grid, slot.cells)
        after_complete[slot.id] = _slot_complete(post, slot.cells)

    completed_slots = tuple(
        slot.id
        for slot in model.slots
        if (not before_complete[slot.id]) and after_complete[slot.id]
    )

    tile_points = len(placements)
    word_points = sum(
        slot.length for slot in model.slots if slot.id in set(completed_slots)
    )
    bonus = 5 if len(rack) == 5 and len(placements) == 5 else 0
    total = tile_points + word_points + bonus

    return ScoreBreakdown(
        placements=tuple(placements),
        tile_points=tile_points,
        word_points=word_points,
        bonus=bonus,
        total=total,
        completed_slots=completed_slots,
    )
