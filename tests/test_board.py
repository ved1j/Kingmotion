import unittest

from kingmotion.board import Board, START_FEN, perft, move_to_uci

# Standard perft suite (chessprogramming.org/Perft_Results)
PERFT_CASES = [
    (START_FEN, [20, 400, 8902, 197281]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
]


class PerftTest(unittest.TestCase):
    def test_perft(self):
        for fen, expected in PERFT_CASES:
            board = Board(fen)
            for depth, count in enumerate(expected, start=1):
                with self.subTest(fen=fen, depth=depth):
                    self.assertEqual(perft(board, depth), count)
            self.assertEqual(board.fen(), fen, "make/unmake must restore the position")


class BoardTest(unittest.TestCase):
    def test_fen_round_trip(self):
        for fen, _ in PERFT_CASES:
            self.assertEqual(Board(fen).fen(), fen)

    def test_incremental_hash_matches_full_hash(self):
        board = Board()
        for text in ["e2e4", "d7d5", "e4d5", "c7c5", "d5c6", "g8f6", "g1f3", "e7e6", "f1e2", "f8e7", "e1g1"]:
            board.make(board.parse_uci(text))
            self.assertEqual(board.hash, board._compute_hash(), text)

    def test_checkmate_and_stalemate(self):
        fools_mate = Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
        self.assertTrue(fools_mate.in_check())
        self.assertEqual(fools_mate.outcome(), "0-1 (checkmate)")
        stalemate = Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertEqual(stalemate.outcome(), "1/2-1/2 (stalemate)")

    def test_threefold_repetition(self):
        board = Board()
        for text in ["g1f3", "g8f6", "f3g1", "f6g8"] * 2:
            board.make(board.parse_uci(text))
        self.assertEqual(board.outcome(), "1/2-1/2 (threefold repetition)")

    def test_promotion_moves(self):
        board = Board("8/P6k/8/8/8/8/8/K7 w - - 0 1")
        promos = sorted(move_to_uci(m) for m in board.legal_moves() if m >> 14 & 7)
        self.assertEqual(promos, ["a7a8b", "a7a8n", "a7a8q", "a7a8r"])


if __name__ == "__main__":
    unittest.main()
