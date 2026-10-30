"""Self-play games between two Kingmotion builds over UCI.

A "build" is a directory containing a `kingmotion/` package, made from a git
ref with `git archive` (or a copy of the working tree), so two versions can
play each other without stepping on each other's imports.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / ".builds"
sys.path.insert(0, str(ROOT))

from kingmotion.board import Board, WHITE  # noqa: E402  (the referee)

MAX_PLIES = 400
RESIGN_CP, RESIGN_MOVES = 800, 3
DRAW_CP, DRAW_PLIES, DRAW_START = 8, 8, 60
MATE_CP = 100000


def make_build(ref):
    """Return (build_dir, label) for a git ref, or WORKTREE for local edits."""
    BUILDS.mkdir(exist_ok=True)
    if ref == "WORKTREE":
        target = BUILDS / f"worktree-{int(time.time() * 1000)}"
        shutil.copytree(ROOT / "kingmotion", target / "kingmotion",
                        ignore=shutil.ignore_patterns("__pycache__"))
        return target, "worktree"
    sha = subprocess.run(["git", "rev-parse", "--short", ref], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout.strip()
    target = BUILDS / sha
    if not (target / "kingmotion").exists():
        target.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "archive", sha, "kingmotion"], cwd=ROOT,
                                 check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive, check=True)
    return target, sha


class Engine:
    def __init__(self, build_dir):
        self.build_dir = build_dir
        self._start()

    def _start(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "kingmotion"], cwd=self.build_dir,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._send("uci")
        self._wait_for("uciok")

    def _send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _wait_for(self, token):
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise EOFError("engine exited")
            if line.startswith(token):
                return line

    def new_game(self):
        if self.proc.poll() is not None:
            self._start()
        self._send("ucinewgame")
        self._send("isready")
        self._wait_for("readyok")

    def go(self, fen, moves, wtime, btime, inc):
        """Return (uci_move, score_cp_from_mover_pov or None)."""
        self._send(f"position fen {fen}" + (" moves " + " ".join(moves) if moves else ""))
        ms = lambda s: max(1, int(s * 1000))  # noqa: E731
        self._send(f"go wtime {ms(wtime)} btime {ms(btime)} winc {ms(inc)} binc {ms(inc)}")
        score = None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise EOFError("engine exited")
            if line.startswith("info") and " score " in line:
                parts = line.split()
                i = parts.index("score")
                kind, value = parts[i + 1], int(parts[i + 2])
                score = value if kind == "cp" else (MATE_CP if value > 0 else -MATE_CP)
            elif line.startswith("bestmove"):
                return line.split()[1], score

    def close(self):
        try:
            self._send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


def play_game(white, black, fen, base_time, inc):
    """Play one game. Returns (result_for_white, reason): 1, 0.5 or 0."""
    board = Board(fen)
    moves = []
    clock = {WHITE: base_time, -WHITE: base_time}
    for engine in (white, black):
        engine.new_game()
    resign_streak = {WHITE: 0, -WHITE: 0}
    quiet_plies = 0

    while True:
        outcome = board.outcome()
        if outcome:
            if outcome.startswith("1-0"):
                return 1.0, outcome
            if outcome.startswith("0-1"):
                return 0.0, outcome
            return 0.5, outcome
        if len(moves) >= MAX_PLIES:
            return 0.5, "max plies"

        side = board.side
        engine = white if side == WHITE else black
        loss = 0.0 if side == WHITE else 1.0
        start = time.monotonic()
        try:
            text, score = engine.go(fen, moves, clock[WHITE], clock[-WHITE], inc)
        except EOFError:
            return loss, "engine crashed"
        clock[side] -= time.monotonic() - start
        if clock[side] < 0:
            return loss, "time forfeit"
        clock[side] += inc
        move = board.parse_uci(text)
        if move is None:
            return loss, f"illegal move {text}"
        board.make(move)
        moves.append(text)

        if score is not None:
            resign_streak[side] = resign_streak[side] + 1 if score <= -RESIGN_CP else 0
            if resign_streak[side] >= RESIGN_MOVES and resign_streak[-side] == 0:
                return loss, "adjudicated: resign"
            quiet_plies = quiet_plies + 1 if abs(score) <= DRAW_CP else 0
            if len(moves) >= DRAW_START and quiet_plies >= DRAW_PLIES:
                return 0.5, "adjudicated: draw"
