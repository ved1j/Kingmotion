"""Play Kingmotion in the terminal."""

from .board import Board, START_FEN, WHITE
from .search import Searcher, score_to_uci

HELP = """Enter moves in SAN (Nf3, exd5, O-O, e8=Q) or UCI (g1f3). Other commands:
  moves  list your legal moves
  undo   take back your last move
  fen    print the current position as FEN
  hint   ask the engine for a suggestion
  quit   leave the game"""


def play(human_color=WHITE, think_time=2.0, fen=START_FEN):
    board = Board(fen)
    searcher = Searcher()
    print("Kingmotion — type 'help' for commands.\n")

    while True:
        print(board, "\n")
        result = board.outcome()
        if result:
            print(f"Game over: {result}")
            return

        if board.side != human_color:
            print("Kingmotion is thinking...")
            move, score = searcher.search(board, soft_time=think_time, hard_time=think_time * 2)
            print(f"Kingmotion plays {board.san(move)}  (eval {score_to_uci(score)})\n")
            board.make(move)
            continue

        try:
            text = input("Your move: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text in ("quit", "exit"):
            return
        if text == "help":
            print(HELP, "\n")
        elif text == "moves":
            legal = board.legal_moves()
            print(" ".join(sorted(board.san(m, legal) for m in legal)), "\n")
        elif text == "fen":
            print(board.fen(), "\n")
        elif text == "undo":
            if len(board.stack) >= 2:
                board.unmake()
                board.unmake()
            else:
                print("Nothing to undo.\n")
        elif text == "hint":
            move, _ = searcher.search(board, soft_time=think_time / 2, hard_time=think_time)
            print(f"Try {board.san(move)}\n")
        else:
            move = board.parse_move(text)
            if move is None:
                print(f"'{text}' is not a legal move. Type 'help' for help.\n")
            else:
                board.make(move)
