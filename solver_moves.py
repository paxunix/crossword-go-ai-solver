from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations, product
from math import comb
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
    req_letters = [ch for ch, n in needed.items() if n > 0]
    need_total = sum(needed[ch] for ch in req_letters)
    pool_total = sum(pool.values())
    if need_total == 0:
        return 1.0
    if draws < need_total or pool_total < draws:
        return 0.0
    for ch in req_letters:
        if pool.get(ch, 0) < needed[ch]:
            return 0.0

    total_ways = comb(pool_total, draws)
    if total_ways == 0:
        return 0.0

    req_pool_total = sum(pool[ch] for ch in req_letters)
    other_pool = pool_total - req_pool_total
    favorable = 0

    # Enumerate draw counts for required letters with lower bounds.
    alloc = [0] * len(req_letters)

    def rec(i: int, used: int, ways_mul: int):
        nonlocal favorable
        if i == len(req_letters):
            rem = draws - used
            if 0 <= rem <= other_pool:
                favorable += ways_mul * comb(other_pool, rem)
            return
        ch = req_letters[i]
        min_k = needed[ch]
        max_k = min(pool[ch], draws - used)
        for k in range(min_k, max_k + 1):
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
    draws = min(5, pool_total)
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
                risk_penalty=_blended_risk_penalty(state, constraints, rack, score.placements),
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
                    risk_penalty=_blended_risk_penalty(state, constraints, rack, score.placements),
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
