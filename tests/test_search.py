import io
import time
import unittest

from kingmotion.board import Board, move_to_uci
from kingmotion.evaluate import evaluate
from kingmotion.search import Searcher, MATE_BOUND
from kingmotion.uci import UCI


def best(fen, depth=4):
    move, score = Searcher().search(Board(fen), max_depth=depth)
    return move_to_uci(move), score


class SearchTest(unittest.TestCase):
    def test_back_rank_mate_in_one(self):
        move, score = best("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
        self.assertEqual(move, "d1d8")
        self.assertGreaterEqual(score, MATE_BOUND)

    def test_scholars_mate(self):
        move, _ = best("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1")
        self.assertEqual(move, "f3f7")

    def test_mate_in_two(self):
        # Ladder mate: 1. Ra7 (or Rb7) Kg8 2. R?8#
        move, score = best("7k/8/8/8/8/8/R7/1R4K1 w - - 0 1", depth=5)
        self.assertGreaterEqual(score, MATE_BOUND)
        self.assertIn(move, {"a2a7", "b1b7"})

    def test_captures_hanging_queen(self):
        move, _ = best("4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1", depth=3)
        self.assertEqual(move, "d2d5")

    def test_respects_time_limit(self):
        start = time.monotonic()
        Searcher().search(Board(), soft_time=0.2, hard_time=0.4)
        self.assertLess(time.monotonic() - start, 1.0)

    def test_evaluation_is_symmetric(self):
        white = Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1")
        black = Board("rnbqk2r/pppp1ppp/5n2/2b1p3/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq - 0 1")
        self.assertEqual(evaluate(white), evaluate(black))


class UCITest(unittest.TestCase):
    def test_go_depth_returns_bestmove(self):
        out = io.StringIO()
        uci = UCI(out=out)
        uci.handle("position startpos moves e2e4 e7e5")
        uci.handle("go depth 3")
        uci.thread.join()
        self.assertIn("bestmove ", out.getvalue())


if __name__ == "__main__":
    unittest.main()
