from dataclasses import dataclass
from typing import Dict, List, Tuple
import re

ROWS = 10
COLS = 8
COL_LABELS = "ABCDEFGH"
VALID_TOKENS = {".", "#", "X"}
CELL_RE = re.compile(r"^([A-H])(10|[1-9])$")


@dataclass(frozen=True)
class Slot:
    id: str
    clue_cell: str
    dir: str
    cells: Tuple[Tuple[int, int], ...]
    length: int
    known_letters: Dict[Tuple[int, int], str]
    empty_cells: Tuple[Tuple[int, int], ...]


@dataclass(frozen=True)
class BoardModel:
    size: Dict[str, int]
    grid: List[List[str]]
    slots: Tuple[Slot, ...]
    cell_to_slots: Dict[Tuple[int, int], Tuple[str, ...]]


def is_interior(r: int, c: int) -> bool:
    return r >= 1 and c >= 1


def cell_to_rc(cell: str) -> Tuple[int, int]:
    s = str(cell).strip().upper()
    m = CELL_RE.match(s)
    if not m:
        raise ValueError(f"Invalid cell: {cell}")
    col = COL_LABELS.index(m.group(1))
    row = int(m.group(2)) - 1
    return row, col


def rc_to_cell(r: int, c: int) -> str:
    if not (0 <= r < ROWS and 0 <= c < COLS):
        raise ValueError(f"Out of bounds rc: {(r, c)}")
    return f"{COL_LABELS[c]}{r + 1}"


def _make_initial_grid() -> List[List[str]]:
    g = [["." for _ in range(COLS)] for _ in range(ROWS)]
    g[0][0] = "X"
    for c in range(1, COLS):
        g[0][c] = "#"
    for r in range(1, ROWS):
        g[r][0] = "#"
    return g


def _normalize_grid(state: dict) -> List[List[str]]:
    grid_raw = state.get("grid")
    if grid_raw is None:
        grid = _make_initial_grid()
    else:
        if not (isinstance(grid_raw, list) and len(grid_raw) == ROWS):
            raise ValueError("grid must be 10 rows")
        grid = []
        for row in grid_raw:
            if not (isinstance(row, list) and len(row) == COLS):
                raise ValueError("each grid row must be length 8")
            out_row = []
            for tok in row:
                s = str(tok).strip().upper()
                if len(s) != 1:
                    raise ValueError(f"Invalid grid token: {tok}")
                if s in VALID_TOKENS or ("A" <= s <= "Z"):
                    out_row.append(s)
                else:
                    raise ValueError(f"Invalid grid token: {tok}")
            grid.append(out_row)

    # Fixed cell invariants are enforced, never overridden by JSON.
    grid[0][0] = "X"
    for c in range(1, COLS):
        grid[0][c] = "#"
    for r in range(1, ROWS):
        grid[r][0] = "#"
    return grid


def _fixed_dirs_for_cell(r: int, c: int) -> Tuple[str, ...]:
    if r == 0 and c >= 1:
        return ("S",)
    if c == 0 and r >= 1:
        return ("E",)
    if not is_interior(r, c):
        return ()
    dirs = []
    if c < COLS - 1:
        dirs.append("E")
    if r < ROWS - 1:
        dirs.append("S")
    return tuple(dirs)


def _extract_slot_cells(grid: List[List[str]], clue_r: int, clue_c: int, direction: str) -> Tuple[Tuple[int, int], ...]:
    if direction == "E":
        dr, dc = 0, 1
    elif direction == "S":
        dr, dc = 1, 0
    else:
        raise ValueError(f"Invalid direction: {direction}")

    cells = []
    r = clue_r + dr
    c = clue_c + dc
    while 0 <= r < ROWS and 0 <= c < COLS and grid[r][c] != "#":
        if not is_interior(r, c):
            break
        cells.append((r, c))
        r += dr
        c += dc
    return tuple(cells)


def build_board_model(state: dict) -> BoardModel:
    size = state.get("size", {})
    if size and (size.get("cols") != COLS or size.get("rows") != ROWS):
        raise ValueError("size must be cols=8 rows=10")

    grid = _normalize_grid(state)
    slots: List[Slot] = []

    for clue_entry in state.get("clues", []):
        clue_cell = str(clue_entry.get("cell", "")).strip().upper()
        if not clue_cell:
            continue
        clue_r, clue_c = cell_to_rc(clue_cell)
        if grid[clue_r][clue_c] != "#":
            raise ValueError(f"clue cell must be '#': {clue_cell}")

        allowed_dirs = _fixed_dirs_for_cell(clue_r, clue_c)
        seen_dirs = set()
        for clue in clue_entry.get("clues", []):
            direction = str(clue.get("dir", "")).strip().upper()
            if direction not in {"E", "S"}:
                continue
            if direction in seen_dirs:
                raise ValueError(f"duplicate direction {direction} at {clue_cell}")
            seen_dirs.add(direction)
            if direction not in allowed_dirs:
                raise ValueError(f"direction {direction} not allowed at {clue_cell}")

            cells = _extract_slot_cells(grid, clue_r, clue_c, direction)
            if not cells:
                raise ValueError(f"zero-length slot at {clue_cell} dir={direction}")

            known_letters = {}
            empty_cells = []
            for r, c in cells:
                tok = grid[r][c]
                if "A" <= tok <= "Z":
                    known_letters[(r, c)] = tok
                else:
                    empty_cells.append((r, c))

            slot_id = f"{clue_cell}:{direction}"
            slots.append(
                Slot(
                    id=slot_id,
                    clue_cell=clue_cell,
                    dir=direction,
                    cells=cells,
                    length=len(cells),
                    known_letters=known_letters,
                    empty_cells=tuple(empty_cells),
                )
            )

    slots.sort(key=lambda s: (cell_to_rc(s.clue_cell), s.dir))

    cell_to_slots: Dict[Tuple[int, int], List[str]] = {}
    for slot in slots:
        for rc in slot.cells:
            cell_to_slots.setdefault(rc, []).append(slot.id)

    frozen_cell_to_slots = {rc: tuple(ids) for rc, ids in cell_to_slots.items()}

    return BoardModel(
        size={"cols": COLS, "rows": ROWS},
        grid=grid,
        slots=tuple(slots),
        cell_to_slots=frozen_cell_to_slots,
    )
