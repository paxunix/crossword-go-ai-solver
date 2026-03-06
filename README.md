Crossword GO! AI Solver
=======================

Curses TUI that lets the user enter clue information and known solution
words within the puzzle. This helps optimize plays against the computer
opponent.

```
crossword-go-ai-solver.py board.json
```

Further usage is documented in the UI.

Current state is deterministic play prediction based entirely on scoring
model and available letters and board state.  Useful mostly to offload board
state memory from the player into a file.

Screenshot to JSON
==================

Use the helper script to run Codex extraction on a screenshot:

```
./screenshot2json.zsh /path/to/board.png
```

This writes `<image-basename>.json` into the repo root using
`SCREENSHOT_EXTRACTION_RULES.md` as the extraction policy.

Future
======

- AI clue interpretation and move risk analysis
- AI screenshot OCR to 80/20 the initial board configuration
