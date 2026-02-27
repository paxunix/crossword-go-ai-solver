#!/usr/bin/env python3
import argparse
import curses
import json
import re
import sys
import textwrap
from typing import Dict, List

ROWS = 10
COLS = 8
COL_LABELS = "ABCDEFGH"

CTRL_W = 23  # save
CTRL_X = 24  # quit
CTRL_R = 18  # rack edit

SOLUTION_RE = re.compile(r'(^|\s)s=([A-Za-z]+)\b', re.IGNORECASE)
UNKNOWN_RE = re.compile(r'(^|\s)!=(.*)$', re.IGNORECASE)


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
        unk = f"!={text}" if unknown else ""
        if sol:
            base = f"{text} (s={sol})" if text else f"(s={sol})"
            return f"{unk} {base}".strip() if unk else base
        return unk if unk else text

    parts = []
    if e:
        parts.append("E: " + fmt(e))
    if s:
        parts.append("S: " + fmt(s))
    return " | ".join(parts)


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

    return grid, clue_map, rack

def build_state_json(grid, clue_map, rack):
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
        "clues": clues
    }


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
    m = UNKNOWN_RE.search(s)
    if m:
        unknown = True
        hint = m.group(2).strip()
        before = (s[:m.start()] + " " + s[m.end():]).strip()
        s = hint if hint else before
        s = re.sub(r"\s+", " ", s)
    return s, unknown

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

    e_text, e_unknown = extract_unknown_and_clean_text(e_seg) if e_seg else ("", False)
    s_text, s_unknown = extract_unknown_and_clean_text(s_seg) if s_seg else ("", False)
    e_text, e_sol = extract_solution_and_clean_text(e_text) if e_text else ("", None)
    s_text, s_sol = extract_solution_and_clean_text(s_text) if s_text else ("", None)

    out = []

    def validate_unknown_solution_pair(d, sol, unknown):
        if unknown and sol:
            raise ValueError(f"{d} clue cannot be unknown and solved at the same time")

    def add(d, t, sol, unknown):
        validate_unknown_solution_pair(d, sol, unknown)
        item = {"dir": d, "text": t}
        if sol:
            item["solution"] = sol
        if unknown:
            item["unknown"] = True
        out.append(item)

    if fixed_dirs == ["E"]:
        add("E", e_text or s_text, e_sol or s_sol, e_unknown or s_unknown)
        return out

    if fixed_dirs == ["S"]:
        add("S", s_text or e_text, s_sol or e_sol, s_unknown or e_unknown)
        return out

    if (e_text or e_sol or e_unknown) and (s_text or s_sol or s_unknown):
        add("E", e_text, e_sol, e_unknown)
        add("S", s_text, s_sol, s_unknown)
    elif e_text or e_sol or e_unknown:
        add("E", e_text, e_sol, e_unknown)
    elif s_text or s_sol or s_unknown:
        add("S", s_text, s_sol, s_unknown)
    else:
        raise ValueError("No clue text")

    return out


# --------------------------------------------------
# Editor
# --------------------------------------------------

def curses_editor(stdscr, grid, clue_map, rack):
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
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)    # cursor highlight
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_GREEN)   # active clue edit cell

    r, c = 1, 1

    help_lines = [
        "ARROWS move | A-Z letter | 3/# clue | !/1 unknown clue | SPACE/BKSP=.",
        "ENTER: '.'->'#'+clue, '#' edit clue | clue text: use !=HINT for unknown | Ctrl-R rack | Ctrl-W save | Ctrl-X quit"
    ]

    def state_fingerprint():
        return json.dumps(build_state_json(grid, clue_map, rack), sort_keys=True)

    initial_fp = state_fingerprint()

    def request_exit():
        if state_fingerprint() == initial_fp:
            raise KeyboardInterrupt()
        ans = prompt_line("Unsaved changes. Save before exit? [s]ave/[d]iscard/[c]ancel: ").lower()
        if ans.startswith("s"):
            return True
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

    def prompt_line(prompt, clue_cell=None):
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

        curses.echo()
        s = ""
        try:
            stdscr.move(y, start_x)
            try:
                s = stdscr.getstr(y, start_x).decode("utf-8", errors="replace")
            except KeyboardInterrupt:
                s = ""
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            prompt_cell = None
        return s.strip()

    def draw():
        stdscr.erase()
        y = 0
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

        y += 1  # blank line

        header = "     " + "".join(f"{c:^{cell_step}}" for c in COL_LABELS).rstrip()
        stdscr.addstr(y, 0, header)
        y += 1

        for rr in range(ROWS):
            stdscr.addstr(y+rr, 0, f"{rr+1:>3}  ")
            for cc in range(COLS):
                ch = grid[rr][cc]
                cell = cell_label(rr, cc)

                attr = 0
                if ch == "#" and cell in clue_map and curses.has_colors():
                    attr |= curses.color_pair(1)

                if prompt_cell == (rr, cc):
                    attr = curses.color_pair(3) if curses.has_colors() else (curses.A_REVERSE | curses.A_BOLD)
                elif rr == r and cc == c:
                    attr = curses.color_pair(2) if curses.has_colors() else curses.A_REVERSE

                draw_ch = f" {ch} "
                if ch == "#":
                    items = clue_map.get(cell, [])
                    e_item = next((it for it in items if str(it.get("dir", "")).upper() == "E"), None)
                    s_item = next((it for it in items if str(it.get("dir", "")).upper() == "S"), None)

                    def clue_mark(it):
                        if not it:
                            return " "
                        return "!" if bool(it.get("unknown")) else "#"

                    fixed = fixed_dirs_for_cell(rr, cc)
                    if fixed == ["E"]:
                        draw_ch = f" {clue_mark(e_item)} "
                    elif fixed == ["S"]:
                        draw_ch = f" {clue_mark(s_item)} "
                    else:
                        draw_ch = f"{clue_mark(e_item)}/{clue_mark(s_item)}"

                stdscr.addstr(y+rr, 5 + cell_step * cc, draw_ch, attr)

        stdscr.refresh()

    def edit_rack():
        nonlocal rack
        line = prompt_line("Enter rack letters (e.g. ABCDE or A B C D E), max 5: ")
        if not line:
            return
        rack = normalize_rack(line)

    def enter_clue(force_unknown=False):
        nonlocal grid
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
                p = (f"!={t}" if unknown else t)
                if sol:
                    p += f" s={sol}"
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
            f"{cell} clue [{dir_hint}; split E/S with '/', optional s=WORD, !=HINT] [{existing}]: "
            , clue_cell=(r, c)
        )
        if not line:
            return

        try:
            clue_map[cell] = parse_clue_entry(line, fixed)
        except Exception:
            pass

    while True:
        draw()
        try:
            ch = stdscr.getch()
        except KeyboardInterrupt:
            if request_exit():
                return grid, clue_map, rack
            continue

        if ch == CTRL_X:
            if request_exit():
                return grid, clue_map, rack
            continue

        if ch == CTRL_W:
            return grid, clue_map, rack

        if ch == CTRL_R:
            edit_rack()
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
            continue

        if 32 <= ch <= 126:
            s = chr(ch).upper()
            if s in {"3", "#"}:
                if is_interior(r, c):
                    grid[r][c] = "#"
                    enter_clue()
                elif grid[r][c] == "#":
                    enter_clue()
            elif s in {"!", "1"}:
                if is_interior(r, c):
                    grid[r][c] = "#"
                    enter_clue(force_unknown=True)
                elif grid[r][c] == "#":
                    enter_clue(force_unknown=True)
            elif s in {".", "#"} or ("A" <= s <= "Z"):
                if is_interior(r, c):
                    grid[r][c] = s


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", nargs="?", help="Board state JSON file (read on start, write on save).")
    args = parser.parse_args()

    if args.json_path:
        try:
            state = load_state(args.json_path)
        except FileNotFoundError:
            state = {}
    else:
        state = {}

    grid, clue_map, rack = validate_and_normalize_state(state)

    try:
        grid, clue_map, rack = curses.wrapper(
            lambda stdscr: curses_editor(stdscr, grid, clue_map, rack)
        )
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return

    out_state = build_state_json(grid, clue_map, rack)
    json_text = json.dumps(out_state, indent=2)

    print("\n--- FINAL GRID ---")
    print(grid_to_pretty_text(grid))
    print("\n--- JSON OUTPUT ---")
    print(json_text)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            f.write(json_text)
            f.write("\n")
        print(f"\nSaved: {args.json_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
