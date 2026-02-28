#!/usr/bin/env python3
import argparse
import curses
import json
import re
import sys
import textwrap
from typing import Dict, List, Set

from solver_moves import generate_forced_moves

ROWS = 10
COLS = 8
COL_LABELS = "ABCDEFGH"

CTRL_W = 23  # save
CTRL_X = 24  # quit
CTRL_R = 18  # rack edit
CTRL_U = 21  # undo last committed suggested play
CTRL_O = 15  # output and exit
TAB = 9

SOLUTION_RE = re.compile(r'(^|\s)s=([A-Za-z]+)\b', re.IGNORECASE)
UNKNOWN_RE = re.compile(r'(^|\s)!=(.*)$')


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def cell_label(r: int, c: int) -> str:
    return f"{COL_LABELS[c]}{r+1}"

def make_initial_grid() -> List[List[str]]:
    g = [["." for _ in range(COLS)] for _ in range(ROWS)]
    g[0][0] = "X"
    for c in range(1, COLS):
        g[0][c] = "#"
    for r in range(1, ROWS):
        g[r][0] = "#"
    return g

def is_interior(r: int, c: int) -> bool:
    return r >= 1 and c >= 1

def fixed_dirs_for_cell(r: int, c: int) -> List[str]:
    if r == 0 and c >= 1:
        return ["S"]
    if c == 0 and r >= 1:
        return ["E"]
    return []

def normalize_grid_token(tok: str) -> str:
    s = str(tok).strip().upper()
    if not s:
        return "."
    if len(s) != 1:
        raise ValueError(f"Invalid token {tok}")
    if s == "3":
        return "#"
    if s in {".", "#", "X"}:
        return s
    if "A" <= s <= "Z":
        return s
    raise ValueError(f"Invalid token {tok}")

def normalize_rack(raw: str) -> List[str]:
    s = raw.strip().upper()
    letters = [ch for ch in s if "A" <= ch <= "Z"]
    return letters[:5]

def grid_to_pretty_text(grid):
    lines = ["     " + " ".join(COL_LABELS)]
    for r in range(ROWS):
        lines.append(f"{r+1:>3}  " + " ".join(grid[r]))
    return "\n".join(lines)

def format_clue_preview(items: List[dict]) -> str:
    """
    items is the per-cell clues list in JSON form:
      [{"dir":"E","text":"...","solution":"..."}, ...]
    Returns a compact string for the header.
    """
    if not items:
        return ""
    e = next((it for it in items if str(it.get("dir","")).upper() == "E"), None)
    s = next((it for it in items if str(it.get("dir","")).upper() == "S"), None)

    def fmt(it):
        if not it:
            return ""
        text = str(it.get("text", "")).strip()
        sol = it.get("solution")
        sol = str(sol).strip().upper() if sol else ""
        unknown = bool(it.get("unknown"))
        unknown_hint = str(it.get("unknown_hint", "")).strip()
        tags = []
        if sol:
            tags.append(f"s=({sol})")
        if unknown:
            hint = unknown_hint or text
            tags.append(f"!=({hint})")

        if unknown and tags:
            return " ".join(tags)
        if text and tags:
            return f"{text} {' '.join(tags)}"
        if text:
            return text
        if tags:
            return " ".join(tags)
        return ""

    parts = []
    if e:
        parts.append("E: " + fmt(e))
    if s:
        parts.append("S: " + fmt(s))
    return " | ".join(parts)

def iter_slot_cells(grid, clue_r: int, clue_c: int, direction: str):
    if direction == "E":
        dr, dc = 0, 1
    elif direction == "S":
        dr, dc = 1, 0
    else:
        return []

    out = []
    r, c = clue_r + dr, clue_c + dc
    while 0 <= r < ROWS and 0 <= c < COLS and grid[r][c] != "#":
        if not is_interior(r, c):
            break
        out.append((r, c))
        r += dr
        c += dc
    return out

def is_clue_complete(grid, clue_r: int, clue_c: int, clue_items: List[dict]) -> bool:
    dirs = []
    for it in clue_items:
        d = str(it.get("dir", "")).upper()
        if d in {"E", "S"}:
            dirs.append(d)
    if not dirs:
        return False
    for d in dirs:
        cells = iter_slot_cells(grid, clue_r, clue_c, d)
        if not cells:
            continue
        if any(not ("A" <= grid[r][c] <= "Z") for r, c in cells):
            return False
    return True

def clue_has_solution(clue_items: List[dict]) -> bool:
    for it in clue_items:
        sol = str(it.get("solution", "")).strip()
        if sol:
            return True
    return False

def clue_item_for_dir(clue_items: List[dict], direction: str):
    d = direction.upper()
    return next((it for it in clue_items if str(it.get("dir", "")).upper() == d), None)

def clue_dir_complete(grid, clue_r: int, clue_c: int, direction: str) -> bool:
    cells = iter_slot_cells(grid, clue_r, clue_c, direction)
    if not cells:
        return True
    return all("A" <= grid[r][c] <= "Z" for r, c in cells)

def render_clue_cell_text(clue_items: List[dict], r: int, c: int) -> str:
    e_item = clue_item_for_dir(clue_items, "E")
    s_item = clue_item_for_dir(clue_items, "S")

    def clue_mark(it):
        if not it:
            return " "
        return "#"

    fixed = fixed_dirs_for_cell(r, c)
    if fixed == ["E"]:
        return f" {clue_mark(e_item)} "
    if fixed == ["S"]:
        return f" {clue_mark(s_item)} "
    return f"{clue_mark(e_item)}/{clue_mark(s_item)}"

def draw_board_cells(
    stdscr,
    base_y: int,
    grid,
    clue_map,
    opponent_new_cells,
    cell_step: int,
    override_attrs: Dict[str, int],
    move_letters: Dict[str, str],
):
    for rr in range(ROWS):
        row_y = base_y + rr
        if row_y >= curses.LINES:
            break
        stdscr.addstr(row_y, 0, f"{rr+1:>3}  ")
        for cc in range(COLS):
            cell = cell_label(rr, cc)
            ch = grid[rr][cc]

            attr = 0
            override_cell_attr = False
            if cell in override_attrs:
                attr = override_attrs[cell]
                override_cell_attr = True

            if not override_cell_attr and cell in opponent_new_cells and curses.has_colors():
                attr |= curses.color_pair(4)

            draw_ch = f" {ch} "
            if cell in move_letters:
                draw_ch = f" {move_letters[cell]} "
            elif ch == "#":
                draw_ch = render_clue_cell_text(clue_map.get(cell, []), rr, cc)

            x = 5 + cell_step * cc
            if x >= curses.COLS:
                continue

            if ch == "#" and not override_cell_attr and curses.has_colors():
                items = clue_map.get(cell, [])
                fixed = fixed_dirs_for_cell(rr, cc)

                def dir_attr(direction: str):
                    it = clue_item_for_dir(items, direction)
                    if not it:
                        return attr
                    if clue_dir_complete(grid, rr, cc, direction):
                        return attr
                    if bool(it.get("unknown")):
                        return curses.color_pair(7)
                    if it.get("solution"):
                        return curses.color_pair(6)
                    return curses.color_pair(1)

                if fixed == ["E"]:
                    stdscr.addstr(row_y, x, draw_ch[:max(0, curses.COLS - x)], dir_attr("E"))
                elif fixed == ["S"]:
                    stdscr.addstr(row_y, x, draw_ch[:max(0, curses.COLS - x)], dir_attr("S"))
                else:
                    parts = [
                        (draw_ch[0], dir_attr("E")),
                        (draw_ch[1], attr),
                        (draw_ch[2], dir_attr("S")),
                    ]
                    for i, (ch_i, a_i) in enumerate(parts):
                        xx = x + i
                        if xx < curses.COLS:
                            stdscr.addstr(row_y, xx, ch_i, a_i)
            else:
                stdscr.addstr(row_y, x, draw_ch[:max(0, curses.COLS - x)], attr)

def draw_color_legend(stdscr, y: int):
    if y >= curses.LINES:
        return y
    if not curses.has_colors():
        stdscr.addstr(y, 0, "Legend: cursor | clue | clue+solution | clue+spec | opp-new | suggest/active"[:max(1, curses.COLS - 1)])
        return y + 1

    x = 0
    max_x = max(1, curses.COLS - 1)

    def put(text, attr=0):
        nonlocal x
        if x >= max_x:
            return
        s = text[: max_x - x]
        stdscr.addstr(y, x, s, attr)
        x += len(s)

    put("Legend: ")
    put(" cursor ", curses.color_pair(2))
    put(" ")
    put(" clue ", curses.color_pair(1))
    put(" ")
    put(" clue+sol ", curses.color_pair(6))
    put(" ")
    put(" clue+spec ", curses.color_pair(7))
    put(" ")
    put(" opp-new ", curses.color_pair(4))
    put(" ")
    put(" suggest/active ", curses.color_pair(3))
    return y + 1


# --------------------------------------------------
# JSON load/save
# --------------------------------------------------

def load_state(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_and_normalize_state(state):
    grid_raw = state.get("grid")
    if grid_raw is None:
        grid = make_initial_grid()
    else:
        grid = []
        if not (isinstance(grid_raw, list) and len(grid_raw) == ROWS):
            raise ValueError("grid must be 10 rows.")
        for row in grid_raw:
            if not (isinstance(row, list) and len(row) == COLS):
                raise ValueError("each grid row must be length 8.")
            grid.append([normalize_grid_token(x) for x in row])

    # enforce fixed layout
    grid[0][0] = "X"
    for c in range(1, COLS):
        grid[0][c] = "#"
    for r in range(1, ROWS):
        grid[r][0] = "#"

    def normalize_clue_items(items):
        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            d = str(it.get("dir", "")).strip().upper()
            if d not in {"E", "S"}:
                continue
            t = str(it.get("text", ""))
            clue = {"dir": d, "text": t}
            sol = it.get("solution")
            unknown = bool(it.get("unknown"))
            if unknown and sol:
                raise ValueError(f"clue {d}: unknown clue cannot also have solution")
            if sol:
                s = str(sol).strip().upper()
                if s and all("A" <= ch <= "Z" for ch in s):
                    clue["solution"] = s
            if unknown:
                clue["unknown"] = True
                hint = str(it.get("unknown_hint", "")).strip()
                if hint:
                    clue["unknown_hint"] = hint
            out.append(clue)
        return out

    clue_map = {}
    for entry in state.get("clues", []):
        cell = entry.get("cell")
        if not cell:
            continue
        clue_map[str(cell).strip().upper()] = normalize_clue_items(entry.get("clues", []))

    rack_raw = state.get("rack", [])
    rack = []
    if isinstance(rack_raw, list):
        for x in rack_raw:
            sx = str(x).strip().upper()
            if len(sx) == 1 and "A" <= sx <= "Z":
                rack.append(sx)
    rack = rack[:5]

    opponent_new_cells: Set[str] = set()
    for cell in state.get("opponent_new_cells", []):
        sc = str(cell).strip().upper()
        if not sc:
            continue
        try:
            rr = int(sc[1:]) - 1
            cc = COL_LABELS.index(sc[0])
        except Exception:
            continue
        if not is_interior(rr, cc):
            continue
        if "A" <= grid[rr][cc] <= "Z":
            opponent_new_cells.add(sc)

    return grid, clue_map, rack, opponent_new_cells

def build_state_json(grid, clue_map, rack, opponent_new_cells):
    def key_fn(cell):
        col = COL_LABELS.index(cell[0])
        row = int(cell[1:]) - 1
        return (row, col)

    clues = [{"cell": c, "clues": clue_map[c]}
             for c in sorted(clue_map.keys(), key=key_fn)]

    return {
        "size": {"cols": COLS, "rows": ROWS},
        "rack": rack,
        "grid": grid,
        "clues": clues,
        "opponent_new_cells": sorted(opponent_new_cells, key=key_fn),
    }


def apply_placements_to_state(state, placements):
    grid, clue_map, rack, _ = validate_and_normalize_state(state)

    rack_remaining = rack[:]
    for cell, letter in placements:
        if letter in rack_remaining:
            rack_remaining.remove(letter)
        else:
            raise ValueError(f"Selected move uses unavailable rack letter: {letter}")

        rc = cell.strip().upper()
        r = int(rc[1:]) - 1
        c = COL_LABELS.index(rc[0])
        if grid[r][c] != ".":
            raise ValueError(f"Selected move targets non-empty cell: {cell}")
        grid[r][c] = letter

    # Once player accepts a move, prior opponent markers no longer apply.
    opponent_new_cells = set()
    return build_state_json(grid, clue_map, rack_remaining, opponent_new_cells)


def save_state_file(path, grid, clue_map, rack, opponent_new_cells):
    if not path:
        raise ValueError("No save path configured.")
    out_state = build_state_json(grid, clue_map, rack, opponent_new_cells)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(out_state, indent=2))
        f.write("\n")


# --------------------------------------------------
# Clue parsing (text; split E/S; optional s=WORD)
# --------------------------------------------------

def extract_solution_and_clean_text(raw):
    s = raw.strip()
    sol = None
    m = SOLUTION_RE.search(s)
    if m:
        sol = m.group(2).upper()
        s = (s[:m.start()] + " " + s[m.end():]).strip()
        s = re.sub(r"\s+", " ", s)
    return s, sol

def extract_unknown_and_clean_text(raw):
    s = raw.strip()
    unknown = False
    unknown_hint = None
    m = UNKNOWN_RE.search(s)
    if m:
        unknown = True
        hint = m.group(2).strip()
        before = s[:m.start()].strip()
        s = re.sub(r"\s+", " ", before).strip()
        unknown_hint = hint
    return s, unknown, unknown_hint

def parse_clue_entry(raw, fixed_dirs):
    s = raw.strip()
    if not s:
        raise ValueError("Empty clue")

    if "/" in s:
        parts = s.split("/")
        if len(parts) != 2:
            raise ValueError("Only one '/' allowed")
        e_seg, s_seg = parts[0].strip(), parts[1].strip()
    else:
        e_seg, s_seg = s, ""

    e_text, e_sol = extract_solution_and_clean_text(e_seg) if e_seg else ("", None)
    s_text, s_sol = extract_solution_and_clean_text(s_seg) if s_seg else ("", None)
    e_text, e_unknown, e_unknown_hint = extract_unknown_and_clean_text(e_text) if e_text else ("", False, None)
    s_text, s_unknown, s_unknown_hint = extract_unknown_and_clean_text(s_text) if s_text else ("", False, None)
    if e_seg and "!=" in e_seg and e_unknown_hint is None:
        # Segment can be just "!=" with no clue text.
        e_unknown = True
        e_unknown_hint = ""
    if s_seg and "!=" in s_seg and s_unknown_hint is None:
        s_unknown = True
        s_unknown_hint = ""

    out = []

    def validate_unknown_solution_pair(d, sol, unknown):
        if unknown and sol:
            raise ValueError(f"{d} clue cannot be unknown and solved at the same time")

    def add(d, t, sol, unknown, unknown_hint=None):
        validate_unknown_solution_pair(d, sol, unknown)
        item = {"dir": d, "text": t}
        if sol:
            item["solution"] = sol
        if unknown:
            item["unknown"] = True
            if unknown_hint:
                item["unknown_hint"] = unknown_hint
        out.append(item)

    if fixed_dirs == ["E"]:
        add("E", e_text or s_text, e_sol or s_sol, e_unknown or s_unknown, e_unknown_hint if e_unknown else s_unknown_hint)
        return out

    if fixed_dirs == ["S"]:
        add("S", s_text or e_text, s_sol or e_sol, s_unknown or e_unknown, s_unknown_hint if s_unknown else e_unknown_hint)
        return out

    if (e_text or e_sol or e_unknown) and (s_text or s_sol or s_unknown):
        add("E", e_text, e_sol, e_unknown, e_unknown_hint)
        add("S", s_text, s_sol, s_unknown, s_unknown_hint)
    elif e_text or e_sol or e_unknown:
        add("E", e_text, e_sol, e_unknown, e_unknown_hint)
    elif s_text or s_sol or s_unknown:
        add("S", s_text, s_sol, s_unknown, s_unknown_hint)
    else:
        raise ValueError("No clue text")

    return out


# --------------------------------------------------
# Editor
# --------------------------------------------------

def curses_editor(stdscr, grid, clue_map, rack, opponent_new_cells, save_path=None):
    try:
        curses.set_escdelay(25)
    except Exception:
        pass
    curses.curs_set(0)
    stdscr.keypad(True)
    prompt_cell = None
    wrap_width = 79
    cell_w = 3
    cell_gap = 1
    cell_step = cell_w + cell_gap

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # clue-entered highlight
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_BLUE)    # clue with known solution
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_RED)     # clue with unknown/speculative info
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)    # cursor highlight
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)   # active clue edit cell
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_MAGENTA) # opponent newly played marker

    r, c = 1, 1
    mode = "edit"
    suggest_moves = []
    suggest_sel = 0
    suggest_scroll = 0
    suggest_stale = True
    status_msg = ""
    undo_snapshot = None

    help_lines = [
        "ARROWS move | A-Z letter | 3/# clue | *=toggle opp marker | TAB suggest",
        "ENTER: '.'->'#'+clue, '#' edit clue | clue text: use !=HINT | Ctrl-U undo | Ctrl-R rack | Ctrl-W save | Ctrl-O output | Ctrl-X quit"
    ]

    def snapshot_state():
        return (
            [row[:] for row in grid],
            json.loads(json.dumps(clue_map)),
            rack[:],
            set(opponent_new_cells),
            r,
            c,
        )

    def restore_snapshot(snap):
        nonlocal grid, clue_map, rack, opponent_new_cells, r, c, suggest_stale
        g, cm, rk, opp, rr, cc = snap
        grid = [row[:] for row in g]
        clue_map = json.loads(json.dumps(cm))
        rack = rk[:]
        opponent_new_cells = set(opp)
        r, c = rr, cc
        suggest_stale = True

    def current_state_json():
        return build_state_json(grid, clue_map, rack, opponent_new_cells)

    def recompute_suggestions():
        nonlocal suggest_moves, suggest_sel, suggest_scroll, suggest_stale, status_msg
        try:
            suggest_moves = generate_forced_moves(current_state_json(), top=10)
            suggest_sel = min(suggest_sel, max(0, len(suggest_moves) - 1))
            suggest_scroll = min(suggest_scroll, suggest_sel)
            status_msg = f"{len(suggest_moves)} suggestion(s) ready."
        except Exception as e:
            suggest_moves = []
            suggest_sel = 0
            suggest_scroll = 0
            status_msg = f"suggest error: {e}"
        suggest_stale = False

    def state_fingerprint():
        return json.dumps(build_state_json(grid, clue_map, rack, opponent_new_cells), sort_keys=True)

    initial_fp = state_fingerprint()

    def request_exit():
        nonlocal status_msg
        if state_fingerprint() == initial_fp:
            raise KeyboardInterrupt()
        ans = prompt_line("Unsaved changes. Save before exit? [s]ave/[d]iscard/[c]ancel: ").lower()
        if ans.startswith("s"):
            try:
                save_state_file(save_path, grid, clue_map, rack, opponent_new_cells)
                status_msg = f"Saved: {save_path}"
                return True
            except Exception as e:
                status_msg = f"Save failed: {e}"
                return False
        if ans.startswith("d"):
            raise KeyboardInterrupt()
        return False

    def footer_y():
        return max(0, curses.LINES - 2)

    def ui_width():
        return max(10, min(wrap_width, max(1, curses.COLS - 1)))

    def wrapped_lines(text: str):
        w = ui_width()
        return textwrap.wrap(text, width=w) or [""]

    def add_wrapped(y: int, text: str):
        for ln in wrapped_lines(text):
            if y >= curses.LINES:
                break
            stdscr.addstr(y, 0, ln)
            y += 1
        return y

    def prompt_line(prompt, clue_cell=None, initial_text=""):
        nonlocal prompt_cell
        prompt_cell = clue_cell
        draw()

        lines = wrapped_lines(prompt)
        if curses.LINES >= 2:
            input_y = curses.LINES - 1
            prompt_cap = curses.LINES - 1
            shown = lines[-prompt_cap:]
            prompt_top = input_y - len(shown)

            for i in range(prompt_top, curses.LINES):
                stdscr.move(i, 0)
                stdscr.clrtoeol()
            for i, ln in enumerate(shown):
                y = prompt_top + i
                if y < input_y:
                    stdscr.addstr(y, 0, ln)

            y = input_y
            start_x = 0
            stdscr.move(y, 0)
            stdscr.clrtoeol()
        else:
            y = 0
            stdscr.move(y, 0)
            stdscr.clrtoeol()
            stdscr.addstr(y, 0, lines[-1])
            start_x = min(len(lines[-1]), ui_width())

        stdscr.refresh()

        try:
            curses.curs_set(1)
        except curses.error:
            pass

        curses.noecho()
        text = str(initial_text)
        buf = list(text)
        cur = len(buf)
        cancelled = False
        try:
            max_len = max(1, ui_width() - start_x)
            view_start = 0

            def move_word_left():
                nonlocal cur
                while cur > 0 and buf[cur - 1].isspace():
                    cur -= 1
                while cur > 0 and not buf[cur - 1].isspace():
                    cur -= 1

            def move_word_right():
                nonlocal cur
                n = len(buf)
                while cur < n and buf[cur].isspace():
                    cur += 1
                while cur < n and not buf[cur].isspace():
                    cur += 1

            def redraw_input():
                nonlocal view_start
                if cur < view_start:
                    view_start = cur
                elif cur > view_start + max_len:
                    view_start = cur - max_len

                shown = "".join(buf[view_start:view_start + max_len])
                stdscr.move(y, start_x)
                stdscr.clrtoeol()
                stdscr.addstr(y, start_x, shown)
                cx = start_x + (cur - view_start)
                cx = max(start_x, min(start_x + max_len, cx))
                stdscr.move(y, cx)
                stdscr.refresh()

            redraw_input()
            while True:
                try:
                    ch = stdscr.get_wch()
                except KeyboardInterrupt:
                    cancelled = True
                    break

                # Enter accepts.
                if ch in ("\n", "\r") or ch == curses.KEY_ENTER:
                    break

                # ESC cancels without changes.
                if ch == "\x1b" or ch == 27:
                    cancelled = True
                    break

                # Navigation keys.
                if ch == curses.KEY_LEFT or ch == "\x02":  # Ctrl-B
                    if cur > 0:
                        cur -= 1
                    redraw_input()
                    continue
                if ch == curses.KEY_RIGHT or ch == "\x06":  # Ctrl-F
                    if cur < len(buf):
                        cur += 1
                    redraw_input()
                    continue
                if ch in (
                    getattr(curses, "KEY_SLEFT", -1),
                    getattr(curses, "KEY_CTRL_LEFT", -1),
                    getattr(curses, "KEY_CLEFT", -1),
                ):
                    move_word_left()
                    redraw_input()
                    continue
                if ch in (
                    getattr(curses, "KEY_SRIGHT", -1),
                    getattr(curses, "KEY_CTRL_RIGHT", -1),
                    getattr(curses, "KEY_CRIGHT", -1),
                ):
                    move_word_right()
                    redraw_input()
                    continue
                if ch == curses.KEY_HOME or ch == "\x01":  # Ctrl-A
                    cur = 0
                    redraw_input()
                    continue
                if ch == curses.KEY_END or ch == "\x05":  # Ctrl-E
                    cur = len(buf)
                    redraw_input()
                    continue

                # Deletion keys.
                if ch in ("\b", "\x7f") or ch == curses.KEY_BACKSPACE:
                    if cur > 0:
                        del buf[cur - 1]
                        cur -= 1
                    redraw_input()
                    continue
                if ch == curses.KEY_DC:
                    if cur < len(buf):
                        del buf[cur]
                    redraw_input()
                    continue

                # Printable text inserts at cursor.
                if isinstance(ch, str) and ch.isprintable():
                    buf.insert(cur, ch)
                    cur += 1
                    redraw_input()
                    continue
        finally:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            prompt_cell = None
        if cancelled:
            return ""
        return "".join(buf).strip()

    def draw():
        nonlocal suggest_scroll
        stdscr.erase()
        y = 0

        if mode == "suggest":
            y = add_wrapped(y, "Suggest Mode: UP/DOWN select | ENTER apply | TAB back to edit | Ctrl-U undo last play")
            y = add_wrapped(y, f"Status: {status_msg}" if status_msg else "Status:")
            rack_str = "".join(rack) if rack else "(empty)"
            y = add_wrapped(y, f"Rack: {rack_str}")

            list_h = max(3, min(10, curses.LINES // 4))
            if suggest_sel < suggest_scroll:
                suggest_scroll = suggest_sel
            if suggest_sel >= suggest_scroll + list_h:
                suggest_scroll = suggest_sel - list_h + 1

            for i in range(list_h):
                idx = suggest_scroll + i
                row_y = y + i
                if idx >= len(suggest_moves) or row_y >= curses.LINES:
                    break
                mv = suggest_moves[idx]
                ps = ", ".join(f"{c}={l}" for c, l in mv.placements) if mv.placements else "(pass)"
                line = f"{idx+1:>2}. {ps} | t={mv.tile_points} w={mv.word_points} b={mv.bonus} total={mv.total}"
                attr = curses.color_pair(2) if (idx == suggest_sel and curses.has_colors()) else (curses.A_REVERSE if idx == suggest_sel else 0)
                stdscr.addstr(row_y, 0, line[:max(1, curses.COLS - 1)], attr)

            y += list_h + 1
            y = draw_color_legend(stdscr, y)
        else:
            for line in help_lines:
                y = add_wrapped(y, line)

            rack_str = "".join(rack) if rack else "(empty)"
            y = add_wrapped(y, f"Rack: {rack_str}")

            cur_cell = cell_label(r, c)
            y = add_wrapped(y, f"Cursor {cur_cell} '{grid[r][c]}'")

            preview = format_clue_preview(clue_map.get(cur_cell, []))
            if preview:
                y = add_wrapped(y, "Clue: " + preview)
            else:
                y = add_wrapped(y, "Clue: (none)")
            y = add_wrapped(y, f"Status: {status_msg}" if status_msg else "Status:")
            y = draw_color_legend(stdscr, y)

            y += 1  # blank line

        if y >= curses.LINES:
            stdscr.refresh()
            return

        header = "     " + "".join(f"{c:^{cell_step}}" for c in COL_LABELS).rstrip()
        stdscr.addstr(y, 0, header[:max(1, curses.COLS - 1)])
        y += 1

        move_cells = set()
        move_letters = {}
        override_attrs = {}
        if mode == "suggest" and suggest_moves:
            move_cells = {cell for cell, _ in suggest_moves[suggest_sel].placements}
            move_letters = {cell: letter for cell, letter in suggest_moves[suggest_sel].placements}
        if mode == "suggest" and curses.has_colors():
            for cell in move_cells:
                override_attrs[cell] = curses.color_pair(3)
        if mode == "edit":
            if prompt_cell is not None:
                pr, pc = prompt_cell
                override_attrs[cell_label(pr, pc)] = (
                    curses.color_pair(3) if curses.has_colors() else (curses.A_REVERSE | curses.A_BOLD)
                )
            else:
                override_attrs[cell_label(r, c)] = (
                    curses.color_pair(2) if curses.has_colors() else curses.A_REVERSE
                )

        draw_board_cells(
            stdscr=stdscr,
            base_y=y,
            grid=grid,
            clue_map=clue_map,
            opponent_new_cells=opponent_new_cells,
            cell_step=cell_step,
            override_attrs=override_attrs,
            move_letters=move_letters,
        )

        stdscr.refresh()

    def edit_rack():
        nonlocal rack, suggest_stale, status_msg
        line = prompt_line("Enter rack letters (e.g. ABCDE or A B C D E), max 5: ")
        if not line:
            return
        rack = normalize_rack(line)
        suggest_stale = True
        status_msg = "Rack updated."

    def enter_clue():
        nonlocal grid, suggest_stale, status_msg
        token = grid[r][c]
        if token not in (".", "#"):
            return

        if token == ".":
            if not is_interior(r, c):
                return
            grid[r][c] = "#"

        cell = cell_label(r, c)
        fixed = fixed_dirs_for_cell(r, c)

        existing = ""
        if cell in clue_map:
            items = clue_map[cell]
            def part(it):
                t = it.get("text", "")
                sol = it.get("solution")
                unknown = bool(it.get("unknown"))
                unknown_hint = str(it.get("unknown_hint", "")).strip()
                p = t
                if sol:
                    p += f" s={sol}"
                if unknown:
                    p += f" !={unknown_hint or t}"
                return p.strip()
            e = next((it for it in items if str(it.get("dir","")).upper() == "E"), None)
            s_ = next((it for it in items if str(it.get("dir","")).upper() == "S"), None)
            if e and s_:
                existing = f"{part(e)} / {part(s_)}"
            elif e:
                existing = part(e)
            elif s_:
                existing = "/" + part(s_)

        dir_hint = ""
        if fixed == ["E"]:
            dir_hint = "dir fixed: E"
        elif fixed == ["S"]:
            dir_hint = "dir fixed: S"
        else:
            dir_hint = "dir: E/S"

        line = prompt_line(
            f"{cell} clue [{dir_hint}; split E/S with '/', optional s=WORD, !=HINT]: ",
            clue_cell=(r, c),
            initial_text=existing,
        )
        if not line:
            return

        try:
            clue_map[cell] = parse_clue_entry(line, fixed)
            suggest_stale = True
            status_msg = f"Clue updated at {cell}."
        except Exception:
            pass

    while True:
        draw()
        try:
            ch = stdscr.getch()
        except KeyboardInterrupt:
            if request_exit():
                return grid, clue_map, rack, opponent_new_cells, "quit"
            continue

        if ch == CTRL_X:
            if request_exit():
                return grid, clue_map, rack, opponent_new_cells, "quit"
            continue

        if ch == CTRL_W:
            try:
                save_state_file(save_path, grid, clue_map, rack, opponent_new_cells)
                status_msg = f"Saved: {save_path}"
            except Exception as e:
                status_msg = f"Save failed: {e}"
            continue

        if ch == CTRL_O:
            return grid, clue_map, rack, opponent_new_cells, "output"

        if ch == CTRL_R:
            edit_rack()
            continue

        if ch == TAB:
            if mode == "edit":
                mode = "suggest"
                if suggest_stale:
                    recompute_suggestions()
            else:
                mode = "edit"
            continue

        if ch == CTRL_U:
            if undo_snapshot is not None:
                restore_snapshot(undo_snapshot)
                undo_snapshot = None
                status_msg = "Undid last committed play."
            else:
                status_msg = "No committed play to undo."
            continue

        if mode == "suggest":
            if ch == curses.KEY_UP:
                suggest_sel = max(0, suggest_sel - 1)
                continue
            if ch == curses.KEY_DOWN:
                suggest_sel = min(max(0, len(suggest_moves) - 1), suggest_sel + 1)
                continue
            if ch in (10, 13, curses.KEY_ENTER):
                if not suggest_moves:
                    status_msg = "No suggestions available."
                    continue
                mv = suggest_moves[suggest_sel]
                undo_snapshot = snapshot_state()
                try:
                    updated = apply_placements_to_state(current_state_json(), mv.placements)
                    grid, clue_map, rack, opponent_new_cells = validate_and_normalize_state(updated)
                    mode = "edit"
                    suggest_stale = True
                    status_msg = f"Applied move with total={mv.total}. Press Ctrl-U to undo."
                except Exception as e:
                    status_msg = f"Apply failed: {e}"
                continue
            continue

        if ch == curses.KEY_UP:
            r = max(0, r-1); continue
        if ch == curses.KEY_DOWN:
            r = min(ROWS-1, r+1); continue
        if ch == curses.KEY_LEFT:
            c = max(0, c-1); continue
        if ch == curses.KEY_RIGHT:
            c = min(COLS-1, c+1); continue

        if ch in (10, 13, curses.KEY_ENTER):
            enter_clue()
            continue

        if ch == ord(' ') or ch in (127, 8, curses.KEY_BACKSPACE):
            if is_interior(r, c):
                grid[r][c] = "."
                clue_map.pop(cell_label(r, c), None)
                opponent_new_cells.discard(cell_label(r, c))
                suggest_stale = True
                status_msg = f"Cleared {cell_label(r, c)}."
            continue

        if 32 <= ch <= 126:
            s = chr(ch).upper()
            if s in {"3", "#"}:
                if is_interior(r, c):
                    grid[r][c] = "#"
                    opponent_new_cells.discard(cell_label(r, c))
                    enter_clue()
                    suggest_stale = True
                elif grid[r][c] == "#":
                    enter_clue()
            elif s == "*":
                if is_interior(r, c):
                    cell = cell_label(r, c)
                    if "A" <= grid[r][c] <= "Z":
                        if cell in opponent_new_cells:
                            opponent_new_cells.remove(cell)
                        else:
                            opponent_new_cells.add(cell)
                        suggest_stale = True
                        status_msg = f"Toggled opponent marker at {cell}."
            elif s in {".", "#"} or ("A" <= s <= "Z"):
                if is_interior(r, c):
                    grid[r][c] = s
                    if s != "#":
                        clue_map.pop(cell_label(r, c), None)
                    if not ("A" <= s <= "Z"):
                        opponent_new_cells.discard(cell_label(r, c))
                    suggest_stale = True
                    status_msg = f"Set {cell_label(r, c)} to {s}."


def curses_suggest_viewer(stdscr, grid, clue_map, rack, opponent_new_cells, moves):
    try:
        curses.set_escdelay(25)
    except Exception:
        pass
    curses.curs_set(0)
    stdscr.keypad(True)

    cell_w = 3
    cell_gap = 1
    cell_step = cell_w + cell_gap
    sel = 0
    scroll = 0

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # clue-entered highlight
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_BLUE)    # clue with known solution
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_RED)     # clue with unknown/speculative info
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)    # selected move row
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_MAGENTA) # opponent marker
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_GREEN)   # suggested placements

    def draw():
        nonlocal scroll
        stdscr.erase()
        y = 0
        stdscr.addstr(y, 0, "SUGGEST: UP/DOWN select move | ENTER accept | q/ESC quit"[:max(1, curses.COLS - 1)])
        y += 1

        rack_str = "".join(rack) if rack else "(empty)"
        stdscr.addstr(y, 0, f"Rack: {rack_str}"[:max(1, curses.COLS - 1)])
        y += 1

        list_h = max(3, min(12, curses.LINES // 3))
        if sel < scroll:
            scroll = sel
        if sel >= scroll + list_h:
            scroll = sel - list_h + 1

        for i in range(list_h):
            idx = scroll + i
            row_y = y + i
            if idx >= len(moves) or row_y >= curses.LINES:
                break
            mv = moves[idx]
            if mv.placements:
                ps = ", ".join(f"{c}={l}" for c, l in mv.placements)
            else:
                ps = "(pass)"
            line = f"{idx+1:>2}. {ps} | t={mv.tile_points} w={mv.word_points} b={mv.bonus} total={mv.total}"
            attr = curses.color_pair(2) if (idx == sel and curses.has_colors()) else (curses.A_REVERSE if idx == sel else 0)
            stdscr.addstr(row_y, 0, line[:max(1, curses.COLS - 1)], attr)

        y += list_h + 1
        y = draw_color_legend(stdscr, y)
        if y >= curses.LINES:
            stdscr.refresh()
            return

        header = "     " + "".join(f"{c:^{cell_step}}" for c in COL_LABELS).rstrip()
        stdscr.addstr(y, 0, header[:max(1, curses.COLS - 1)])
        y += 1

        move_cells = {cell for cell, _ in moves[sel].placements} if moves else set()
        move_letters = {cell: letter for cell, letter in moves[sel].placements} if moves else {}
        override_attrs = {}
        if curses.has_colors():
            for cell in move_cells:
                override_attrs[cell] = curses.color_pair(5)

        draw_board_cells(
            stdscr=stdscr,
            base_y=y,
            grid=grid,
            clue_map=clue_map,
            opponent_new_cells=opponent_new_cells,
            cell_step=cell_step,
            override_attrs=override_attrs,
            move_letters=move_letters,
        )

        stdscr.refresh()

    while True:
        draw()
        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return None
        if ch in (10, 13, curses.KEY_ENTER):
            return sel
        if ch == curses.KEY_UP:
            sel = max(0, sel - 1)
            continue
        if ch == curses.KEY_DOWN:
            sel = min(max(0, len(moves) - 1), sel + 1)
            continue


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")

    p_edit = sub.add_parser("edit", help="Open curses editor")
    p_edit.add_argument("json_path", nargs="?", help="Board state JSON file (read on start, write on save).")

    p_suggest = sub.add_parser("suggest", help="Suggest deterministic forced moves")
    p_suggest.add_argument("json_path", help="Board state JSON file")
    p_suggest.add_argument("--top", type=int, default=10, help="Number of moves to show")

    # Backward compatibility: if first arg is not a subcommand, treat as legacy edit mode.
    argv = sys.argv[1:]
    if argv and argv[0] not in {"edit", "suggest", "-h", "--help"}:
        args = parser.parse_args(["edit"] + argv)
    else:
        args = parser.parse_args()

    if args.command == "suggest":
        state = load_state(args.json_path)
        moves = generate_forced_moves(state, top=args.top)

        # Interactive TUI when attached to a terminal; fallback to text otherwise.
        if sys.stdin.isatty() and sys.stdout.isatty():
            grid, clue_map, rack, opponent_new_cells = validate_and_normalize_state(state)
            selected = curses.wrapper(
                lambda stdscr: curses_suggest_viewer(
                    stdscr, grid, clue_map, rack, opponent_new_cells, moves
                )
            )
            if selected is not None:
                mv = moves[selected]
                ps = ", ".join(f"{c}={l}" for c, l in mv.placements) if mv.placements else "(pass)"
                print(f"Selected: {ps}")
                print(f"tile={mv.tile_points} word={mv.word_points} bonus={mv.bonus} total={mv.total}")
                if mv.completed_slots:
                    print(f"completed={', '.join(mv.completed_slots)}")
                updated = apply_placements_to_state(state, mv.placements)
                with open(args.json_path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(updated, indent=2))
                    f.write("\n")
                print(f"Saved: {args.json_path}")
        else:
            print(f"Top {len(moves)} move(s) for {args.json_path}:")
            for i, mv in enumerate(moves, start=1):
                if mv.placements:
                    ps = ", ".join(f"{c}={l}" for c, l in mv.placements)
                else:
                    ps = "(pass)"
                print(f"{i}. {ps}")
                print(f"   tile={mv.tile_points} word={mv.word_points} bonus={mv.bonus} total={mv.total}")
                if mv.completed_slots:
                    print(f"   completed={', '.join(mv.completed_slots)}")
        return

    json_path = getattr(args, "json_path", None)
    if json_path:
        try:
            state = load_state(json_path)
        except FileNotFoundError:
            state = {}
    else:
        state = {}

    grid, clue_map, rack, opponent_new_cells = validate_and_normalize_state(state)

    try:
        grid, clue_map, rack, opponent_new_cells, action = curses.wrapper(
            lambda stdscr: curses_editor(stdscr, grid, clue_map, rack, opponent_new_cells, save_path=json_path)
        )
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return

    if action != "output":
        return

    out_state = build_state_json(grid, clue_map, rack, opponent_new_cells)
    json_text = json.dumps(out_state, indent=2)

    print("\n--- FINAL GRID ---")
    print(grid_to_pretty_text(grid))
    print("\n--- JSON OUTPUT ---")
    print(json_text)

    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_text)
            f.write("\n")
        print(f"\nSaved: {json_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
