import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from sprt import elo_estimate, elo_to_score, llr, pair_stats, score_to_elo  # noqa: E402


class SprtStatsTest(unittest.TestCase):
    def test_elo_score_round_trip(self):
        for elo in (-200, -15, 0, 15, 200):
            self.assertAlmostEqual(score_to_elo(elo_to_score(elo)), elo, places=6)

    def test_empty_run_does_not_crash(self):
        self.assertEqual(pair_stats([0] * 5), (0, 0.5, 0.0))
        self.assertEqual(llr([0] * 5, 0, 15), 0.0)
        elo_estimate([0] * 5)

    def test_even_match_is_zero_elo(self):
        elo, err = elo_estimate([10, 40, 100, 40, 10])
        self.assertAlmostEqual(elo, 0.0, places=6)
        self.assertGreater(err, 0)

    def test_llr_direction(self):
        strong = [5, 20, 80, 60, 35]   # test engine clearly better
        weak = list(reversed(strong))
        self.assertGreater(llr(strong, 0, 15), 2.94)
        self.assertLess(llr(weak, 0, 15), -2.94)


if __name__ == "__main__":
    unittest.main()
