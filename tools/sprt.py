#!/usr/bin/env python3
"""Run an SPRT (or fixed-length) self-play match between two builds.

    python3 tools/sprt.py --base HEAD --test WORKTREE --change "what changed"

Each opening is played twice with colors swapped (a game pair), and the
statistics are pentanomial: the pair score (0, .25, .5, .75, 1) is the unit,
which cancels most of the noise from unbalanced openings.
"""

import argparse
import json
import math
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from match import ROOT, BUILDS, Engine, make_build, play_game  # noqa: E402

OPENINGS = ROOT / "tools" / "openings.txt"
RESULT_FILE = BUILDS / "last_result.json"


# ------------------------------------------------------------------ statistics

def elo_to_score(elo):
    return 1 / (1 + 10 ** (-elo / 400))


def score_to_elo(score):
    score = min(max(score, 1e-6), 1 - 1e-6)
    return -400 * math.log10(1 / score - 1)


def pair_stats(pairs):
    """Mean and variance of pair scores; pairs is a list of 5 counts."""
    n = sum(pairs)
    if n == 0:
        return 0, 0.5, 0.0
    values = (0, 0.25, 0.5, 0.75, 1)
    mean = sum(c * v for c, v in zip(pairs, values)) / n
    var = sum(c * (v - mean) ** 2 for c, v in zip(pairs, values)) / n
    return n, mean, var


def llr(pairs, elo0, elo1):
    """Generalized SPRT log-likelihood ratio (normal approximation)."""
    n, mean, var = pair_stats(pairs)
    if n < 2 or var <= 0:
        return 0.0
    s0, s1 = elo_to_score(elo0), elo_to_score(elo1)
    return n * (s1 - s0) * (2 * mean - s0 - s1) / (2 * var)


def elo_estimate(pairs):
    n, mean, var = pair_stats(pairs)
    elo = score_to_elo(mean)
    if n < 2:
        return elo, float("inf")
    margin = 1.96 * math.sqrt(var / n)
    return elo, (score_to_elo(min(mean + margin, 1)) - score_to_elo(max(mean - margin, 0))) / 2


# -------------------------------------------------------------------- openings

def generate_openings(count=1600, plies=8, seed=2026):
    """Random but sane openings: random legal moves, kept only if a quick
    search says the position is roughly balanced."""
    from kingmotion.board import Board
    from kingmotion.search import Searcher

    rng = random.Random(seed)
    searcher = Searcher()
    fens = []
    seen = set()
    while len(fens) < count:
        board = Board()
        for _ in range(plies):
            moves = board.legal_moves()
            if not moves:
                break
            board.make(rng.choice(moves))
        if board.outcome() or board.hash in seen:
            continue
        _, score = searcher.search(board, max_depth=3)
        if abs(score) <= 60:
            seen.add(board.hash)
            fens.append(board.fen())
    OPENINGS.write_text("\n".join(fens) + "\n")
    return fens


def load_openings(pairs_needed):
    fens = []
    if OPENINGS.exists():
        fens = [line.strip() for line in OPENINGS.read_text().splitlines() if line.strip()]
    if len(fens) < pairs_needed:
        # Reusing an opening replays nearly the same pair of games, which adds
        # games without adding much information.
        print(f"Generating {max(pairs_needed, 1600)} openings (one-time)...", flush=True)
        fens = generate_openings(max(pairs_needed, 1600))
    return fens


# --------------------------------------------------------------------- driver

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="HEAD", help="git ref of the baseline")
    parser.add_argument("--test", default="WORKTREE", help="git ref, or WORKTREE for local edits")
    parser.add_argument("--change", default="", help="description for the log")
    parser.add_argument("--tc", default="5+0.05", help="base+increment in seconds")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--elo0", type=float, default=0.0)
    parser.add_argument("--elo1", type=float, default=15.0)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--beta", type=float, default=0.05)
    parser.add_argument("--max-games", type=int, default=3000)
    parser.add_argument("--fixed-games", type=int, default=0,
                        help="play exactly this many games, no SPRT stopping")
    parser.add_argument("--kind", default="sprt", choices=["sprt", "anchor"])
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    base_time, inc = (float(x) for x in args.tc.split("+"))
    lower = math.log(args.beta / (1 - args.alpha))
    upper = math.log((1 - args.beta) / args.alpha)
    max_games = args.fixed_games or args.max_games

    base_dir, base_label = make_build(args.base)
    test_dir, test_label = make_build(args.test)
    openings = load_openings((max_games + 1) // 2)
    random.Random(args.seed).shuffle(openings)
    print(f"{test_label} vs {base_label}  tc {args.tc}  "
          f"{'fixed ' + str(max_games) + ' games' if args.fixed_games else f'SPRT [{args.elo0}, {args.elo1}]'}",
          flush=True)

    lock = threading.Lock()
    state = {"pairs": [0] * 5, "wdl": [0, 0, 0], "next": 0, "done": False,
             "verdict": None, "reasons": {}}
    engines = []
    started = time.monotonic()

    def worker():
        try:
            test, base = Engine(test_dir), Engine(base_dir)
        except Exception as exc:
            with lock:
                state["done"], state["verdict"] = True, f"error: {exc}"
            return
        with lock:
            engines.extend((test, base))
        try:
            while True:
                with lock:
                    if state["done"] or state["next"] * 2 >= max_games:
                        return
                    fen = openings[state["next"] % len(openings)]
                    state["next"] += 1
                pair_score = 0.0
                results = []
                for test_white in (True, False):
                    if state["done"]:
                        return
                    white, black = (test, base) if test_white else (base, test)
                    try:
                        result, reason = play_game(white, black, fen, base_time, inc)
                    except Exception as exc:
                        # Stop the whole run: results from fewer workers, or
                        # from a broken engine, would be misleading.
                        with lock:
                            state["done"], state["verdict"] = True, f"error: {exc!r}"
                        return
                    score = result if test_white else 1 - result
                    pair_score += score
                    results.append((score, reason))
                with lock:
                    if state["done"]:
                        return
                    state["pairs"][int(pair_score * 2)] += 1
                    for score, reason in results:
                        state["wdl"][0 if score == 1 else 1 if score == 0.5 else 2] += 1
                        key = reason.split(" (")[-1].rstrip(")")
                        state["reasons"][key] = state["reasons"].get(key, 0) + 1
                    report(state, args, lower, upper, started)
                    value = llr(state["pairs"], args.elo0, args.elo1)
                    games = sum(state["wdl"])
                    if not args.fixed_games and value >= upper:
                        state["done"], state["verdict"] = True, "accepted"
                    elif not args.fixed_games and value <= lower:
                        state["done"], state["verdict"] = True, "rejected"
                    elif games >= max_games:
                        state["done"] = True
                        state["verdict"] = "measured" if args.fixed_games else "rejected (cap)"
        finally:
            test.close()
            base.close()

    pool = ThreadPoolExecutor(args.concurrency)
    futures = [pool.submit(worker) for _ in range(args.concurrency)]
    try:
        while not all(f.done() for f in futures):
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nInterrupted: stopping engines...", flush=True)
        with lock:
            state["done"] = True
            state["verdict"] = "aborted"
            for engine in engines:
                engine.proc.kill()
    pool.shutdown(wait=True)

    elo, err = elo_estimate(state["pairs"])
    result = {
        "date": time.strftime("%Y-%m-%d"),
        "kind": args.kind,
        "base": base_label,
        "test": test_label,
        "change": args.change,
        "tc": args.tc,
        "games": sum(state["wdl"]),
        "wins": state["wdl"][0], "draws": state["wdl"][1], "losses": state["wdl"][2],
        "pentanomial": state["pairs"],
        "elo": round(elo, 1), "elo_err": round(err, 1),
        "llr": round(llr(state["pairs"], args.elo0, args.elo1), 2),
        "bounds": [args.elo0, args.elo1],
        "result": state["verdict"] or "aborted",
        "minutes": round((time.monotonic() - started) / 60, 1),
        "endings": state["reasons"],
    }
    RESULT_FILE.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if test_label == "worktree":
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


def report(state, args, lower, upper, started):
    games = sum(state["wdl"])
    elo, err = elo_estimate(state["pairs"])
    w, d, l = state["wdl"]
    minutes = (time.monotonic() - started) / 60
    line = f"games {games:5}  W {w} D {d} L {l}  elo {elo:+6.1f} ± {err:5.1f}"
    if not args.fixed_games:
        line += f"  LLR {llr(state['pairs'], args.elo0, args.elo1):+5.2f} [{lower:.2f}, {upper:.2f}]"
    print(line + f"  {minutes:.1f}m", flush=True)


if __name__ == "__main__":
    main()
