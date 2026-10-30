# Progress log

Newest entry first. Each working session reads this first and adds an entry
when it ends: what was done, results, and what to do next.

## 2026-10-30 — Testing infrastructure, part 1

**Done**
- `SPEC.md`: goal, milestones, match settings, the commands that measure success.
- `tools/match.py`: plays games between two builds over UCI, with a referee
  board, chess clocks, and resign/draw adjudication.
- `tools/sprt.py`: pentanomial GSPRT runner (game pairs with colors swapped),
  Elo estimate with 95% error, result saved to `.builds/last_result.json`.
  Ctrl-C stops a run cleanly.
- `tools/openings.txt`: balanced random 8-ply openings.
- Tagged the anchor build `v0.2.0` (commit cf3073e).

**Results**
- No SPRT test run yet; only short smoke tests of the runner.

**Next**
1. Elo log (`elo/history.csv`) and chart (`tools/plot_elo.py` → `docs/elo.svg`).
2. First real SPRT test. Good candidates: incremental evaluation (speed),
   SEE pruning of losing captures in quiescence, mobility in the eval.
3. Lichess bot, then the NNUE pipeline (data on Mac, training on Colab).
