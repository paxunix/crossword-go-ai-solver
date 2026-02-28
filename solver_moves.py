from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations, product
from typing import Dict, List, Tuple

from solver_constraints import propagate_constraints
from solver_model import cell_to_rc, rc_to_cell
from solver_scoring import score_move

RISK_ONE_EMPTY = 5
RISK_TWO_EMPTY = 2


@dataclass(frozen=True)
class MoveSuggestion:
    placements: Tuple[Tuple[str, str], ...]
    tile_points: int
    word_points: int
    bonus: int
    total: int
    risk_penalty: int
    completed_slots: Tuple[str, ...]


def _normalize_rack(state: dict) -> List[str]:
    rack = []
    for x in state.get("rack", []):
        s = str(x).strip().upper()
        if len(s) == 1 and "A" <= s <= "Z":
            rack.append(s)
    return rack[:5]


def _placement_key(placements: Tuple[Tuple[str, str], ...]) -> str:
    return ",".join(f"{cell}={letter}" for cell, letter in placements)


def _slot_length_weight(slot_len: int) -> int:
    # Mild scaling by slot length: 2-3 => 1, 4-5 => 2, 6-7 => 3, 8+ => 4.
    return 1 + max(0, int(slot_len) - 2) // 2


def _risk_penalty_for_post_grid(model, placements: Tuple[Tuple[str, str], ...]) -> int:
    post = [row[:] for row in model.grid]
    for cell, letter in placements:
        r, c = cell_to_rc(cell)
        post[r][c] = letter

    penalty = 0
    for slot in model.slots:
        slot_weight = _slot_length_weight(len(slot.cells))
        empties = 0
        for r, c in slot.cells:
            if not ("A" <= post[r][c] <= "Z"):
                empties += 1
        if empties == 1:
            penalty += RISK_ONE_EMPTY * slot_weight
        elif empties == 2:
            penalty += RISK_TWO_EMPTY * slot_weight
    return penalty


def generate_forced_moves(state: dict, top: int = 10, sort_mode: str = "score") -> List[MoveSuggestion]:
    sort_mode = str(sort_mode or "score").strip().lower()
    if sort_mode not in {"score", "risk"}:
        sort_mode = "score"
    constraints = propagate_constraints(state)
    rack = _normalize_rack(state)
    rack_counts = Counter(rack)

    # Candidate empty cells where the exact forced letter is placeable from rack.
    by_letter: Dict[str, List[str]] = defaultdict(list)
    for (r, c), forced_letter in constraints.forced_letters.items():
        if constraints.model.grid[r][c] != ".":
            continue
        if rack_counts[forced_letter] > 0:
            by_letter[forced_letter].append(rc_to_cell(r, c))
    for ch in by_letter:
        by_letter[ch].sort()

    letters = sorted(rack_counts.keys())
    options_per_letter: List[List[Tuple[str, ...]]] = []
    for ch in letters:
        cells = by_letter.get(ch, [])
        max_pick = min(rack_counts[ch], len(cells))
        opts: List[Tuple[str, ...]] = []
        for k in range(max_pick + 1):
            opts.extend(combinations(cells, k))
        options_per_letter.append(opts)

    suggestions: List[MoveSuggestion] = []
    seen = set()
    if not letters:
        score = score_move(state, {"placements": []})
        suggestions.append(
            MoveSuggestion(
                placements=score.placements,
                tile_points=score.tile_points,
                word_points=score.word_points,
                bonus=score.bonus,
                total=score.total,
                risk_penalty=_risk_penalty_for_post_grid(constraints.model, score.placements),
                completed_slots=score.completed_slots,
            )
        )
    else:
        for picks in product(*options_per_letter):
            placements: List[Tuple[str, str]] = []
            for ch, picked_cells in zip(letters, picks):
                for cell in picked_cells:
                    placements.append((cell, ch))
            placements.sort(key=lambda x: x[0])
            place_t = tuple(placements)
            key = _placement_key(place_t)
            if key in seen:
                continue
            seen.add(key)
            score = score_move(
                state,
                {"placements": [{"cell": c, "letter": l} for c, l in place_t]},
            )
            suggestions.append(
                MoveSuggestion(
                    placements=score.placements,
                    tile_points=score.tile_points,
                    word_points=score.word_points,
                    bonus=score.bonus,
                    total=score.total,
                    risk_penalty=_risk_penalty_for_post_grid(constraints.model, score.placements),
                    completed_slots=score.completed_slots,
                )
            )

    if sort_mode == "risk":
        suggestions.sort(
            key=lambda m: (
                m.risk_penalty,
                -m.total,
                len(m.placements),
                _placement_key(m.placements),
            )
        )
    else:
        suggestions.sort(
            key=lambda m: (
                -m.total,
                m.risk_penalty,
                len(m.placements),
                _placement_key(m.placements),
            )
        )
    if top < 0:
        top = 0
    return suggestions[:top]
