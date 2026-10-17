"""Universal Chess Interface (UCI) front end, so Kingmotion can be plugged
into GUIs like Cute Chess, Arena, En Croissant or lichess-bot."""

import sys
import threading
import time

from . import __version__
from .board import Board, START_FEN, WHITE, move_to_uci, perft
from .search import Searcher, score_to_uci, format_pv, tt_entries_for, DEFAULT_HASH_MB

MOVE_OVERHEAD = 0.05  # seconds kept in reserve for GUI/IO latency


def time_budget(board, params):
    """Turn UCI 'go' parameters into (soft, hard) limits in seconds."""
    if "movetime" in params:
        t = max(0.01, params["movetime"] / 1000 - MOVE_OVERHEAD)
        return t, t
    key, inc_key = ("wtime", "winc") if board.side == WHITE else ("btime", "binc")
    if key not in params:
        return None, None
    remaining = params[key] / 1000
    inc = params.get(inc_key, 0) / 1000
    moves_to_go = params.get("movestogo", 30)
    budget = remaining / max(moves_to_go, 1) + inc * 0.75
    hard = max(0.01, min(budget * 3, remaining * 0.5) - MOVE_OVERHEAD)
    soft = min(budget * 0.6, hard)
    return soft, hard


class UCI:
    def __init__(self, out=sys.stdout):
        self.board = Board()
        self.searcher = Searcher()
        self.thread = None
        self.out = out

    def send(self, line):
        print(line, file=self.out, flush=True)

    def loop(self, stream=sys.stdin):
        for line in stream:
            if not self.handle(line.strip()):
                break
        self.stop_search()

    def handle(self, line):
        """Process one command. Returns False when the engine should exit."""
        tokens = line.split()
        if not tokens:
            return True
        cmd = tokens[0]
        if cmd == "uci":
            self.send(f"id name Kingmotion {__version__}")
            self.send("id author Kingmotion contributors")
            self.send(f"option name Hash type spin default {DEFAULT_HASH_MB} min 1 max 1024")
            self.send("option name Clear Hash type button")
            self.send("uciok")
        elif cmd == "isready":
            self.send("readyok")
        elif cmd == "ucinewgame":
            self.stop_search()
            self.searcher.new_game()
            self.board = Board()
        elif cmd == "setoption":
            self._setoption(tokens)
        elif cmd == "position":
            self.stop_search()
            self._position(tokens)
        elif cmd == "go":
            self.stop_search()
            self._go(tokens)
        elif cmd == "stop":
            self.stop_search()
        elif cmd == "quit":
            return False
        elif cmd == "d":
            self.send(str(self.board))
            self.send(f"Fen: {self.board.fen()}")
        elif cmd == "perft" and len(tokens) > 1:
            self._perft(int(tokens[1]))
        return True

    def _setoption(self, tokens):
        if "name" not in tokens:
            return
        end = tokens.index("value") if "value" in tokens else len(tokens)
        name = " ".join(tokens[tokens.index("name") + 1:end]).lower()
        value = tokens[end + 1] if end + 1 < len(tokens) else None
        if name == "hash" and value and value.isdigit():
            self.stop_search()
            self.searcher.tt_max = tt_entries_for(max(1, min(1024, int(value))))
            self.searcher.tt.clear()
        elif name == "clear hash":
            self.stop_search()
            self.searcher.new_game()

    def _position(self, tokens):
        moves_at = tokens.index("moves") if "moves" in tokens else len(tokens)
        if len(tokens) > 1 and tokens[1] == "fen":
            fen = " ".join(tokens[2:moves_at])
        else:
            fen = START_FEN
        self.board = Board(fen)
        for text in tokens[moves_at + 1:]:
            m = self.board.parse_uci(text)
            if m is None:
                self.send(f"info string illegal move {text}")
                break
            self.board.make(m)

    def _go(self, tokens):
        params = {}
        numeric = ("wtime", "btime", "winc", "binc", "movestogo", "depth", "nodes", "movetime")
        for i, tok in enumerate(tokens[:-1]):
            if tok in numeric:
                params[tok] = int(tokens[i + 1])
        infinite = "infinite" in tokens
        soft, hard = (None, None) if infinite else time_budget(self.board, params)

        def info(depth, score, nodes, elapsed, pv):
            nps = int(nodes / elapsed) if elapsed > 0 else 0
            self.send(f"info depth {depth} score {score_to_uci(score)} nodes {nodes} "
                      f"nps {nps} time {int(elapsed * 1000)} pv {format_pv(pv)}")

        def run():
            move, _ = self.searcher.search(self.board, max_depth=params.get("depth"),
                                           soft_time=soft, hard_time=hard,
                                           max_nodes=params.get("nodes"), on_info=info)
            self.send(f"bestmove {move_to_uci(move) if move else '0000'}")

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop_search(self):
        if self.thread and self.thread.is_alive():
            self.searcher.stop = True
            self.thread.join()
        self.thread = None

    def _perft(self, depth):
        start = time.monotonic()
        total = 0
        for m in self.board.legal_moves():
            self.board.make(m)
            n = perft(self.board, depth - 1)
            self.board.unmake()
            total += n
            self.send(f"{move_to_uci(m)}: {n}")
        elapsed = time.monotonic() - start
        self.send(f"\nNodes searched: {total} ({elapsed:.2f}s)")


def main():
    UCI().loop()
