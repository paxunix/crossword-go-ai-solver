from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations, product
from math import comb
from typing import Dict, List, Tuple

from solver_constraints import propagate_constraints
from solver_model import cell_to_rc, rc_to_cell
from solver_scoring import score_move
from tile_rules import (
    JOKER_TILE,
    consume_rack_for_letters,
    joker_cells_for_placements,
    normalize_rack_items,
)

RISK_ONE_EMPTY = 5
RISK_TWO_EMPTY = 2


@dataclass(frozen=True)
class MoveSuggestion:
    placements: Tuple[Tuple[str, str], ...]
    joker_cells: Tuple[str, ...]
    tile_points: int
    word_points: int
    bonus: int
    total: int
    risk_penalty: int
    completed_slots: Tuple[str, ...]


def _normalize_rack(state: dict) -> List[str]:
    return normalize_rack_items(state.get("rack", []))


def _placement_key(placements: Tuple[Tuple[str, str], ...]) -> str:
    return ",".join(f"{cell}={letter}" for cell, letter in placements)


def _slot_length_weight(slot_len: int) -> int:
    # Mild scaling by slot length: 2-3 => 1, 4-5 => 2, 6-7 => 3, 8+ => 4.
    return 1 + max(0, int(slot_len) - 2) // 2


def _structural_risk_for_post_grid(model, placements: Tuple[Tuple[str, str], ...]) -> int:
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


def _post_move_rack(start_rack: List[str], placements: Tuple[Tuple[str, str], ...]) -> List[str]:
    counts = Counter(start_rack)
    for _, letter in placements:
        if counts[letter] > 0:
            counts[letter] -= 1
    out: List[str] = []
    for ch in start_rack:
        if counts[ch] > 0:
            out.append(ch)
            counts[ch] -= 1
    return out


def _hypergeom_prob_at_least(pool: Counter, draws: int, needed: Counter) -> float:
    req_letters = [ch for ch, n in needed.items() if n > 0 and ch != JOKER_TILE]
    joker_pool = pool.get(JOKER_TILE, 0)
    need_total = sum(needed[ch] for ch in req_letters)
    pool_total = sum(pool.values())
    if need_total == 0:
        return 1.0
    if draws < need_total or pool_total < draws:
        return 0.0

    total_ways = comb(pool_total, draws)
    if total_ways == 0:
        return 0.0

    req_pool_total = sum(pool[ch] for ch in req_letters)
    other_pool = pool_total - req_pool_total - joker_pool
    favorable = 0

    # Enumerate draw counts for required letters and jokers.
    alloc = [0] * (len(req_letters) + 1)

    def rec(i: int, used: int, ways_mul: int):
        nonlocal favorable
        if i == len(req_letters):
            max_j = min(joker_pool, draws - used)
            for j in range(max_j + 1):
                rem = draws - used - j
                if not (0 <= rem <= other_pool):
                    continue
                deficits = 0
                for idx, ch in enumerate(req_letters):
                    deficits += max(0, needed[ch] - alloc[idx])
                if deficits <= j:
                    favorable += ways_mul * comb(joker_pool, j) * comb(other_pool, rem)
            return
        ch = req_letters[i]
        max_k = min(pool[ch], draws - used)
        for k in range(0, max_k + 1):
            alloc[i] = k
            rec(i + 1, used + k, ways_mul * comb(pool[ch], k))

    rec(0, 0, 1)
    return favorable / total_ways


def _opponent_draw_pool_counts(constraints, post_grid: List[List[str]], my_post_rack: List[str]) -> Counter:
    # Approximate remaining draw pool as forced letters still unfilled after our move,
    # minus the letters currently known in our rack.
    need = Counter()
    for (r, c), ch in constraints.forced_letters.items():
        if post_grid[r][c] == ".":
            need[ch] += 1

    my_counts = Counter(my_post_rack)
    for ch, n in my_counts.items():
        if n > 0:
            need[ch] = max(0, need[ch] - n)
            if need[ch] == 0:
                need.pop(ch, None)
    # Approximate single-joker game: if we don't currently hold joker, opponent draw pool may.
    if JOKER_TILE not in my_counts:
        need[JOKER_TILE] += 1
    return need


def _confidence_for_post_grid(constraints, post_grid: List[List[str]], state: dict) -> float:
    total_open = 0
    forced_open = 0
    for r in range(1, len(post_grid)):
        for c in range(1, len(post_grid[r])):
            if post_grid[r][c] != ".":
                continue
            total_open += 1
            if (r, c) in constraints.forced_letters:
                forced_open += 1
    forced_ratio = 1.0 if total_open == 0 else (forced_open / total_open)

    # Opponent metadata quality: if user marked last-play cells, pool-based inference
    # is slightly more trustworthy; otherwise keep confidence mostly unchanged.
    hist = state.get("opponent_new_cells")
    if isinstance(hist, list):
        hist_n = sum(1 for x in hist if isinstance(x, str) and x.strip())
        history_factor = 0.85 + 0.15 * min(5, hist_n) / 5.0
    else:
        history_factor = 1.0
    return max(0.0, min(1.0, forced_ratio * history_factor))


def _opponent_one_turn_ev(constraints, post_grid: List[List[str]], my_post_rack: List[str]) -> float:
    pool = _opponent_draw_pool_counts(constraints, post_grid, my_post_rack)
    pool_total = sum(pool.values())
    max_draw = 6 if pool.get(JOKER_TILE, 0) > 0 else 5
    draws = min(max_draw, pool_total)
    if draws <= 0:
        return 0.0

    ev = 0.0
    for slot in constraints.model.slots:
        empties = []
        for r, c in slot.cells:
            if post_grid[r][c] == ".":
                empties.append((r, c))
        if not empties or len(empties) > 5:
            continue
        if any(rc not in constraints.forced_letters for rc in empties):
            continue

        need = Counter(constraints.forced_letters[rc] for rc in empties)
        p_complete = _hypergeom_prob_at_least(pool, draws, need)
        if p_complete <= 0.0:
            continue

        # Approximate one-turn value: slot completion points + tile placements.
        slot_value = slot.length + len(empties)
        if len(empties) == 5:
            slot_value += 5  # potential rack-empty bonus
        ev += p_complete * slot_value
    return ev


def _blended_risk_penalty(state: dict, constraints, start_rack: List[str], placements: Tuple[Tuple[str, str], ...]) -> int:
    post_grid = [row[:] for row in constraints.model.grid]
    for cell, letter in placements:
        r, c = cell_to_rc(cell)
        post_grid[r][c] = letter

    structural = _structural_risk_for_post_grid(constraints.model, placements)
    my_post_rack = _post_move_rack(start_rack, placements)
    opponent_ev = _opponent_one_turn_ev(constraints, post_grid, my_post_rack)
    confidence = _confidence_for_post_grid(constraints, post_grid, state)

    blended = confidence * opponent_ev + (1.0 - confidence) * structural
    return int(round(blended))


def generate_forced_moves(state: dict, top: int = 10, sort_mode: str = "score") -> List[MoveSuggestion]:
    sort_mode = str(sort_mode or "score").strip().lower()
    if sort_mode not in {"score", "risk"}:
        sort_mode = "score"
    rack = _normalize_rack(state)
    if not rack:
        return []
    constraints = propagate_constraints(state)
    rack_counts = Counter(rack)
    joker_count = rack_counts.get(JOKER_TILE, 0)
    rack_letters = [ch for ch in rack if "A" <= ch <= "Z"]
    rack_letter_counts = Counter(rack_letters)

    # Candidate empty cells where the exact forced letter is placeable from rack.
    by_letter: Dict[str, List[str]] = defaultdict(list)
    for (r, c), forced_letter in constraints.forced_letters.items():
        if constraints.model.grid[r][c] != ".":
            continue
        if rack_letter_counts[forced_letter] > 0:
            by_letter[forced_letter].append(rc_to_cell(r, c))
    for ch in by_letter:
        by_letter[ch].sort()
    forced_cell_letter: Dict[str, str] = {}
    for (r, c), forced_letter in constraints.forced_letters.items():
        if constraints.model.grid[r][c] == ".":
            forced_cell_letter[rc_to_cell(r, c)] = forced_letter
    all_forced_cells = sorted(forced_cell_letter.keys())

    letters = sorted(rack_letter_counts.keys())
    options_per_letter: List[List[Tuple[str, ...]]] = []
    for ch in letters:
        cells = by_letter.get(ch, [])
        max_pick = min(rack_letter_counts[ch], len(cells))
        opts: List[Tuple[str, ...]] = []
        for k in range(max_pick + 1):
            opts.extend(combinations(cells, k))
        options_per_letter.append(opts)

    suggestions: List[MoveSuggestion] = []
    seen = set()
    def maybe_add_suggestion(place_t: Tuple[Tuple[str, str], ...]):
        key = _placement_key(place_t)
        if key in seen:
            return
        try:
            consume_rack_for_letters(rack, [l for _, l in place_t], enforce_special_rules=True)
        except ValueError:
            return
        seen.add(key)
        score = score_move(
            state,
            {"placements": [{"cell": c, "letter": l} for c, l in place_t]},
        )
        suggestions.append(
            MoveSuggestion(
                placements=score.placements,
                joker_cells=tuple(joker_cells_for_placements(rack, list(score.placements), enforce_special_rules=True)),
                tile_points=score.tile_points,
                word_points=score.word_points,
                bonus=score.bonus,
                total=score.total,
                risk_penalty=_blended_risk_penalty(state, constraints, rack, score.placements),
                completed_slots=score.completed_slots,
            )
        )

    base_pick_products = product(*options_per_letter) if letters else [tuple()]
    for picks in base_pick_products:
        base_cells = set()
        placements: List[Tuple[str, str]] = []
        for ch, picked_cells in zip(letters, picks):
            for cell in picked_cells:
                base_cells.add(cell)
                placements.append((cell, ch))
        remaining_for_joker = [cell for cell in all_forced_cells if cell not in base_cells]
        max_joker_pick = min(joker_count, len(remaining_for_joker))
        for joker_k in range(max_joker_pick + 1):
            for joker_cells in combinations(remaining_for_joker, joker_k):
                merged = placements + [(cell, forced_cell_letter[cell]) for cell in joker_cells]
                merged.sort(key=lambda x: x[0])
                maybe_add_suggestion(tuple(merged))

    if sort_mode == "risk":
        suggestions.sort(
            key=lambda m: (
                -m.risk_penalty,
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
