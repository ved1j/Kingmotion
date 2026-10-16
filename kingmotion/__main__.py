"""Command-line entry point: `python -m kingmotion [uci|play|perft|bench]`."""

import argparse
import time

from .board import Board, BLACK, WHITE, START_FEN, perft
from .search import Searcher, score_to_uci, format_pv

BENCH_POSITIONS = [
    START_FEN,
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
]


def main():
    parser = argparse.ArgumentParser(prog="kingmotion", description="Kingmotion chess engine")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("uci", help="run the UCI protocol loop (default)")
    p_play = sub.add_parser("play", help="play against the engine in the terminal")
    p_play.add_argument("--color", choices=["white", "black"], default="white")
    p_play.add_argument("--time", type=float, default=2.0, help="seconds per engine move")
    p_play.add_argument("--fen", default=START_FEN)
    p_perft = sub.add_parser("perft", help="count move-tree leaves to check movegen")
    p_perft.add_argument("depth", type=int)
    p_perft.add_argument("--fen", default=START_FEN)
    p_bench = sub.add_parser("bench", help="fixed-depth search speed benchmark")
    p_bench.add_argument("--depth", type=int, default=5)
    args = parser.parse_args()

    if args.command == "play":
        from .play import play
        play(WHITE if args.color == "white" else BLACK, args.time, args.fen)
    elif args.command == "perft":
        start = time.monotonic()
        nodes = perft(Board(args.fen), args.depth)
        print(f"perft({args.depth}) = {nodes}  [{time.monotonic() - start:.2f}s]")
    elif args.command == "bench":
        total, start = 0, time.monotonic()
        for fen in BENCH_POSITIONS:
            searcher = Searcher()
            move, score = searcher.search(Board(fen), max_depth=args.depth)
            total += searcher.nodes
            print(f"{format_pv([move]):6} {score_to_uci(score):10} {searcher.nodes:>8} nodes  {fen}")
        elapsed = time.monotonic() - start
        print(f"\n{total} nodes in {elapsed:.2f}s ({int(total / elapsed)} nps)")
    else:
        from .uci import main as uci_main
        uci_main()


if __name__ == "__main__":
    main()
