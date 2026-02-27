from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations, product
from typing import Dict, List, Tuple

from solver_constraints import propagate_constraints
from solver_model import rc_to_cell
from solver_scoring import ScoreBreakdown, score_move


@dataclass(frozen=True)
class MoveSuggestion:
    placements: Tuple[Tuple[str, str], ...]
    tile_points: int
    word_points: int
    bonus: int
    total: int
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


def _as_suggestion(score: ScoreBreakdown) -> MoveSuggestion:
    return MoveSuggestion(
        placements=score.placements,
        tile_points=score.tile_points,
        word_points=score.word_points,
        bonus=score.bonus,
        total=score.total,
        completed_slots=score.completed_slots,
    )


def generate_forced_moves(state: dict, top: int = 10) -> List[MoveSuggestion]:
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
        suggestions.append(_as_suggestion(score))
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
            suggestions.append(_as_suggestion(score))

    suggestions.sort(
        key=lambda m: (
            -m.total,
            len(m.placements),
            _placement_key(m.placements),
        )
    )
    if top < 0:
        top = 0
    return suggestions[:top]
