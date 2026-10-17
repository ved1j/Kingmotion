# Kingmotion ♚

[![tests](https://github.com/ved1j/Kingmotion/actions/workflows/tests.yml/badge.svg)](https://github.com/ved1j/Kingmotion/actions/workflows/tests.yml)

A UCI chess engine written in pure Python — no dependencies, readable code.

## Features

**Board & move generation**
- 10×12 mailbox board with signed-int pieces
- Full legal move generation: castling, en passant, under-promotion
- Incremental Zobrist hashing, make/unmake with an undo stack
- Verified against the standard perft suite

**Search**
- Iterative deepening negamax with principal variation search (PVS)
- Transposition table with mate-score adjustment
- Aspiration windows
- Quiescence search with delta pruning and check evasions
- Null-move pruning, reverse futility pruning, late move reductions
- Check extensions and mate-distance pruning
- Move ordering: TT move → MVV-LVA captures → promotions → killers → history
- Repetition and fifty-move-rule draw detection

**Evaluation**
- Tapered (middlegame/endgame) material + piece-square tables
- Passed, doubled and isolated pawns
- Bishop pair, rooks on open/semi-open files

## Usage

Requires Python 3.9+.

```bash
python3 -m kingmotion play                 # play as white, 2s per engine move (SAN or UCI input)
python3 -m kingmotion play --color black --time 5
python3 -m kingmotion                      # UCI mode (for chess GUIs)
python3 -m kingmotion perft 5              # move generator check
python3 -m kingmotion bench --depth 6      # speed benchmark
```

Or install it to get a `kingmotion` command:

```bash
pip install -e .
```

### Using with a chess GUI

Add Kingmotion as a UCI engine in [Cute Chess](https://cutechess.com/),
[Arena](http://www.playwitharena.de/) or [En Croissant](https://encroissant.org/),
with the command `python3 -m kingmotion` and the repository folder as the
working directory (or just `kingmotion` after `pip install`).

Supported UCI commands: `uci`, `isready`, `ucinewgame`, `setoption` (`Hash`, `Clear Hash`),
`position [startpos | fen …] moves …`, `go` (`wtime btime winc binc movestogo
depth nodes movetime infinite`), `stop`, `quit`, plus `d` (show board) and
`perft N`.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Layout

```
kingmotion/
  board.py      board, FEN, move generation, make/unmake, perft
  evaluate.py   static evaluation
  search.py     alpha-beta search and transposition table
  uci.py        UCI protocol
  play.py       terminal play
  __main__.py   command-line entry point
tests/          perft, search and UCI tests
```

## Ideas for next steps

- Static exchange evaluation (SEE)
- King safety and mobility terms in the evaluation
- An opening book
- Port the hot loops to a faster language, or use PyPy for a ~5× speedup

## License

MIT
