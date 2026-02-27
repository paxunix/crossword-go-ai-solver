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

Future
======

- AI clue interpretation and move risk analysis
- AI screenshot OCR to 80/20 the initial board configuration
