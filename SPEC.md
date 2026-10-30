# Kingmotion — Spec

## Goal

Make Kingmotion as strong as possible, proving every change with self-play
statistics instead of intuition, and put it on Lichess where people can play it.

Every engine change goes through the same gate:

1. Make one change (search, eval, speed, NNUE…).
2. Tests must pass: `python3 -m unittest discover -s tests`.
3. SPRT self-play match, candidate vs. current `main`:
   accepted only if the SPRT accepts H1 (the change gains Elo).
4. Accepted → commit, log the result in `elo/history.csv`, re-plot.
   Rejected → discard the change, still log it (a negative result is data).
   *(The CSV log and plot script are part of milestone 1 and not built yet;
   until then, each run's result is saved to `.builds/last_result.json`.)*

## How success is measured

The exact command for a single change (candidate = uncommitted working tree):

```bash
python3 tools/sprt.py --base HEAD --test WORKTREE --change "short description"
```

The long-run metric is Elo relative to the anchor build `v0.2.0`
(the first bug-fixed version), measured directly rather than summed:

```bash
python3 tools/sprt.py --base v0.2.0 --test HEAD --fixed-games 400 --kind anchor --change "anchor check"
```

`elo/history.csv` will hold every result, and `python3 tools/plot_elo.py`
will render `docs/elo.svg`, the README hero chart (both still to build).

### Match settings (keep fixed so results are comparable)

| Setting | Value |
|---|---|
| Time control | 5s + 0.05s per move (`--tc 5+0.05`) |
| Concurrency | 8 games at once |
| Openings | `tools/openings.txt` (1600 balanced 8-ply openings), each played twice with colors swapped |
| SPRT | elo0 = 0, elo1 = 15, α = β = 0.05, pentanomial GSPRT |
| Cap | 3000 games; an undecided test counts as rejected |
| Adjudication | resign at −800cp agreed for 3 moves; draw at ≤ 8cp for 8 moves after ply 60; 400 plies = draw |

The elo1 = 15 bound is wider than top engines use (they test ±2–5 Elo with
tens of thousands of games). A pure-Python engine plays about 0.45 games per
second across 8 cores (measured: 16 games in 0.6 min), so a full 3000-game
test takes about 2 hours and a tighter bound would need days. As
the engine matures and gains get smaller, tighten to [0, 5].

Elo figures are self-play Elo: they overstate strength against other engines,
and summing SPRT estimates is biased upward because only winners are kept.
That is why the chart's headline line comes from anchor measurements.

## Milestones

1. **Testing infrastructure** — SPRT runner (done: `tools/sprt.py`,
   `tools/match.py`), Elo CSV log and chart (to do). Complete when the first
   change has been accepted or rejected through it.
2. **Speed** — incremental evaluation, cheaper move generation and legality
   checks. Python nodes/sec translate directly into depth.
3. **Search** — SEE, futility and late-move pruning, better LMR, TT
   replacement, improved time management.
4. **Evaluation** — mobility, king safety, tuned PSTs (Texel tuning on
   self-play positions).
5. **Lichess bot** — `tools/lichess_bot.py` (to build), running on a Lichess
   BOT account. You create the account and API token yourself; the bot reads
   the token from the `LICHESS_TOKEN` environment variable.
6. **NNUE** — split across machines:
   - **Data (Mac, CPU):** self-play positions labeled with search scores
     and game results, written to a file.
   - **Training (Google Colab, GPU):** upload the file to Google Drive,
     train a small network (768→N→1) in PyTorch in
     `notebooks/train_nnue.ipynb` (to build), export the weights.
   - **Inference (engine):** load the weights into Kingmotion. Pure-Python
     inference may cost more speed than the better eval gains, so this needs
     a decision first: allow numpy, or port the hot path to a compiled
     language. Merged only if it passes SPRT like everything else.

## Rules for working sessions

- Read `PROGRESS.md` first; append to it last.
- One idea per SPRT test. Commit after every green test run.
- Never commit an engine change that has not passed SPRT; tooling, tests and
  docs don't need one.
