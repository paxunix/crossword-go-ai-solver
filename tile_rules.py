from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable, List


BASE_MAX_RACK_SIZE = 5
MAX_RACK_SIZE_WITH_JOKER = 6
JOKER_TILE = "?"


@dataclass(frozen=True)
class SpecialTileRule:
    token: str
    name: str
    wildcard: bool
    must_play_if_in_rack: bool


SPECIAL_TILE_RULES = {
    JOKER_TILE: SpecialTileRule(
        token=JOKER_TILE,
        name="joker",
        wildcard=True,
        must_play_if_in_rack=True,
    ),
}

SPECIAL_TILE_ALIASES = {
    "JOKER": JOKER_TILE,
}


def _normalize_rack_token(raw) -> str:
    s = str(raw).strip().upper()
    if not s:
        return ""
    if s in SPECIAL_TILE_RULES:
        return s
    if s in SPECIAL_TILE_ALIASES:
        return SPECIAL_TILE_ALIASES[s]
    if len(s) == 1 and "A" <= s <= "Z":
        return s
    return ""


def normalize_rack_items(items: Iterable) -> List[str]:
    out: List[str] = []
    for x in items:
        tok = _normalize_rack_token(x)
        if tok:
            out.append(tok)
    cap = MAX_RACK_SIZE_WITH_JOKER if JOKER_TILE in out else BASE_MAX_RACK_SIZE
    return out[:cap]


def normalize_rack_text(raw: str) -> List[str]:
    s = re.sub(r"\bJOKER\b", JOKER_TILE, str(raw).upper())
    out: List[str] = []
    for ch in s:
        if ch == JOKER_TILE or ("A" <= ch <= "Z"):
            out.append(ch)
    cap = MAX_RACK_SIZE_WITH_JOKER if JOKER_TILE in out else BASE_MAX_RACK_SIZE
    return out[:cap]


def has_must_play_special_tile(rack: List[str]) -> bool:
    for tok in rack:
        rule = SPECIAL_TILE_RULES.get(tok)
        if rule and rule.must_play_if_in_rack:
            return True
    return False


def full_rack_size_for_tiles(rack: List[str]) -> int:
    tokens = normalize_rack_items(rack)
    return MAX_RACK_SIZE_WITH_JOKER if JOKER_TILE in tokens else BASE_MAX_RACK_SIZE


def consume_rack_for_letters(
    rack: List[str],
    placed_letters: List[str],
    enforce_special_rules: bool = True,
) -> List[str]:
    placements = [str(ch).strip().upper() for ch in placed_letters if str(ch).strip()]
    if any(len(ch) != 1 or not ("A" <= ch <= "Z") for ch in placements):
        raise ValueError("placed letters must be A-Z")

    rack_tokens = normalize_rack_items(rack)
    rack_counts = Counter(rack_tokens)
    letter_counts = Counter(tok for tok in rack_tokens if len(tok) == 1 and "A" <= tok <= "Z")
    wildcard_tokens = [tok for tok, rule in SPECIAL_TILE_RULES.items() if rule.wildcard]
    wildcard_count = sum(rack_counts[tok] for tok in wildcard_tokens)

    if len(placements) > len(rack_tokens):
        raise ValueError("placements exceed rack size")

    place_counts = Counter(placements)
    min_wild_needed = 0
    for ch, n in place_counts.items():
        direct = letter_counts.get(ch, 0)
        if n > direct:
            min_wild_needed += n - direct

    if min_wild_needed > wildcard_count:
        raise ValueError("placement uses unavailable rack letters")

    wildcard_use = min_wild_needed
    if enforce_special_rules:
        must_play_count = sum(
            rack_counts[tok]
            for tok, rule in SPECIAL_TILE_RULES.items()
            if rule.must_play_if_in_rack
        )
        if must_play_count > 0 and len(placements) == 0:
            raise ValueError("must play special tile this turn")
        if must_play_count > len(placements):
            raise ValueError("not enough placements to satisfy must-play special tiles")
        wildcard_use = max(wildcard_use, must_play_count)

    # Assign wildcard usage per letter: deficits first, then extra up to wildcard_use.
    wildcard_by_letter = Counter()
    for ch, n in place_counts.items():
        direct = letter_counts.get(ch, 0)
        wildcard_by_letter[ch] = max(0, n - direct)
    used = sum(wildcard_by_letter.values())
    extra = wildcard_use - used
    if extra > 0:
        for ch, n in place_counts.items():
            room = n - wildcard_by_letter[ch]
            add = min(room, extra)
            wildcard_by_letter[ch] += add
            extra -= add
            if extra == 0:
                break

    consume_letters = Counter()
    for ch, n in place_counts.items():
        consume_letters[ch] = n - wildcard_by_letter[ch]

    consume_special = Counter()
    need = wildcard_use
    for tok in wildcard_tokens:
        take = min(rack_counts[tok], need)
        consume_special[tok] = take
        need -= take
        if need == 0:
            break
    if need != 0:
        raise ValueError("placement uses unavailable special tiles")

    remaining: List[str] = []
    letters_left = consume_letters.copy()
    special_left = consume_special.copy()
    for tok in rack_tokens:
        if tok in special_left and special_left[tok] > 0:
            special_left[tok] -= 1
            continue
        if "A" <= tok <= "Z" and letters_left[tok] > 0:
            letters_left[tok] -= 1
            continue
        remaining.append(tok)
    return remaining


def joker_cells_for_placements(
    rack: List[str],
    placements: List[tuple],
    enforce_special_rules: bool = True,
) -> List[str]:
    # Validate first with shared legality rules.
    consume_rack_for_letters(
        rack,
        [str(letter).strip().upper() for _, letter in placements],
        enforce_special_rules=enforce_special_rules,
    )

    rack_tokens = normalize_rack_items(rack)
    rack_counts = Counter(rack_tokens)
    letter_counts = Counter(tok for tok in rack_tokens if len(tok) == 1 and "A" <= tok <= "Z")
    wildcard_tokens = [tok for tok, rule in SPECIAL_TILE_RULES.items() if rule.wildcard]
    wildcard_count = sum(rack_counts[tok] for tok in wildcard_tokens)

    place_letters = [str(letter).strip().upper() for _, letter in placements]
    place_counts = Counter(place_letters)

    # Minimum wildcard usage from letter deficits.
    wildcard_by_letter = Counter()
    for ch, n in place_counts.items():
        wildcard_by_letter[ch] = max(0, n - letter_counts.get(ch, 0))
    wildcard_use = sum(wildcard_by_letter.values())

    if enforce_special_rules:
        must_play_count = sum(
            rack_counts[tok]
            for tok, rule in SPECIAL_TILE_RULES.items()
            if rule.must_play_if_in_rack
        )
        wildcard_use = max(wildcard_use, must_play_count)
    wildcard_use = min(wildcard_use, wildcard_count)

    # Assign per-letter wildcard usage to earliest occurrences of that letter.
    is_wild = [False] * len(placements)
    idx_by_letter = {}
    for i, (_, letter) in enumerate(placements):
        ch = str(letter).strip().upper()
        idx_by_letter.setdefault(ch, []).append(i)
    for ch, k in wildcard_by_letter.items():
        for i in idx_by_letter.get(ch, [])[:k]:
            is_wild[i] = True

    used = sum(1 for x in is_wild if x)
    extra = max(0, wildcard_use - used)
    if extra > 0:
        for i in range(len(is_wild)):
            if not is_wild[i]:
                is_wild[i] = True
                extra -= 1
                if extra == 0:
                    break

    out = []
    for (cell, _), mark in zip(placements, is_wild):
        if mark:
            out.append(str(cell).strip().upper())
    return out
