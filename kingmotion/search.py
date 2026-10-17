"""Search: iterative deepening PVS alpha-beta with a transposition table,
quiescence search, null-move pruning, late move reductions, reverse
futility pruning, check extensions, killer moves and history ordering."""

import time

from .board import EMPTY, EN_PASSANT, move_to_uci
from .evaluate import evaluate, PIECE_VALUES

MATE = 100000
MATE_BOUND = MATE - 1000
INF = MATE + 1
MAX_PLY = 100

EXACT, LOWER, UPPER = 0, 1, 2

# Most-valuable-victim / least-valuable-attacker ordering weights
_MVV = [0, 1, 3, 3, 5, 9, 20]


def score_to_uci(score):
    if score >= MATE_BOUND:
        return f"mate {(MATE - score + 1) // 2}"
    if score <= -MATE_BOUND:
        return f"mate -{(MATE + score) // 2}"
    return f"cp {score}"


DEFAULT_HASH_MB = 64
TT_ENTRY_BYTES = 200  # rough size of one Python dict entry with its tuple


def tt_entries_for(megabytes):
    return megabytes * 1024 * 1024 // TT_ENTRY_BYTES


class Searcher:
    def __init__(self, hash_mb=DEFAULT_HASH_MB):
        self.tt = {}
        self.tt_max = tt_entries_for(hash_mb)
        self.stop = False
        self.history = [[0] * 120 for _ in range(13)]
        self.killers = [[0, 0] for _ in range(MAX_PLY + 1)]
        self.nodes = 0
        self.deadline = None
        self.max_nodes = None
        self.root_best = 0

    def new_game(self):
        self.tt.clear()
        self.history = [[0] * 120 for _ in range(13)]

    # ----------------------------------------------------------------- driver

    def search(self, board, max_depth=None, soft_time=None, hard_time=None,
               max_nodes=None, on_info=None):
        """Search `board` and return (best_move, score). Times are seconds.

        soft_time: don't start a new iteration once this much time has passed.
        hard_time: abort mid-iteration at this point.
        """
        self.stop = False
        self.nodes = 0
        self.start = time.monotonic()
        self.deadline = self.start + hard_time if hard_time else None
        self.max_nodes = max_nodes
        self.killers = [[0, 0] for _ in range(MAX_PLY + 1)]
        for row in self.history:
            for i in range(120):
                row[i] //= 8
        if len(self.tt) > self.tt_max:
            self.tt.clear()

        legal = board.legal_moves()
        if not legal:
            return None, 0
        self.root_best = legal[0]
        if len(legal) == 1 and (soft_time or hard_time):
            return legal[0], 0

        max_depth = min(max_depth or MAX_PLY - 1, MAX_PLY - 1)
        best_move, best_score = legal[0], 0
        for depth in range(1, max_depth + 1):
            score = self._aspiration(board, depth, best_score)
            if self.stop:
                # A partial iteration still searched the previous best
                # move first, so any newer root_best is a real improvement.
                best_move = self.root_best
                break
            best_move, best_score = self.root_best, score
            elapsed = time.monotonic() - self.start
            if on_info:
                pv = self._pv(board, depth)
                on_info(depth, score, self.nodes, elapsed, pv)
            if soft_time and elapsed >= soft_time:
                break
            if abs(score) >= MATE_BOUND and depth >= MATE - abs(score):
                break  # found the shortest mate
        return best_move, best_score

    def _aspiration(self, board, depth, guess):
        """Search with a narrow window around the previous score, widening
        it on failure. Narrow windows cut more of the tree."""
        if depth < 4 or abs(guess) >= MATE_BOUND:
            return self._negamax(board, depth, -INF, INF, 0, True)
        delta = 40
        alpha, beta = guess - delta, guess + delta
        safe_best = self.root_best
        while True:
            score = self._negamax(board, depth, alpha, beta, 0, True)
            if self.stop:
                return score
            if score <= alpha:
                # Fail-low: every move looked bad, so root_best is just
                # whichever lost least against a wrong bound. Keep the old one.
                self.root_best = safe_best
                alpha = max(score - delta, -INF)
            elif score >= beta:
                beta = min(score + delta, INF)
            else:
                return score
            delta *= 2
            if delta > 1000:
                alpha, beta = -INF, INF

    def _check_limits(self):
        if self.deadline and time.monotonic() >= self.deadline:
            self.stop = True
        if self.max_nodes and self.nodes >= self.max_nodes:
            self.stop = True

    # ----------------------------------------------------------------- search

    def _negamax(self, board, depth, alpha, beta, ply, allow_null):
        self.nodes += 1
        if not self.nodes & 1023:
            self._check_limits()
        if self.stop:
            return 0

        pv_node = beta - alpha > 1
        if ply:
            if board.halfmove >= 100 or board.is_repetition():
                return 0
            if ply >= MAX_PLY:
                return evaluate(board)
            # Mate distance pruning
            alpha = max(alpha, -MATE + ply)
            beta = min(beta, MATE - ply - 1)
            if alpha >= beta:
                return alpha

        in_check = board.in_check()
        if in_check:
            depth += 1
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply)

        tt_move = 0
        entry = self.tt.get(board.hash)
        if entry:
            tt_depth, tt_score, tt_flag, tt_move = entry
            if ply and not pv_node and tt_depth >= depth:
                tt_score = _score_from_tt(tt_score, ply)
                if (tt_flag == EXACT or (tt_flag == LOWER and tt_score >= beta)
                        or (tt_flag == UPPER and tt_score <= alpha)):
                    return tt_score

        if not in_check and not pv_node:
            static = evaluate(board)
            # Reverse futility pruning: far above beta at shallow depth.
            if depth <= 3 and static - 120 * depth >= beta and abs(beta) < MATE_BOUND:
                return static
            # Null move pruning: if passing still beats beta, we can cut.
            if (allow_null and depth >= 3 and static >= beta
                    and board.has_non_pawn_material(board.side)):
                r = 2 + depth // 4
                board.make_null()
                score = -self._negamax(board, depth - 1 - r, -beta, -beta + 1, ply + 1, False)
                board.unmake_null()
                if self.stop:
                    return 0
                if score >= beta:
                    return beta if score >= MATE_BOUND else score

        moves = self._order(board, board.gen_moves(), tt_move, ply)
        us = board.side
        sq = board.sq
        best_score, best_move = -INF, 0
        original_alpha = alpha
        legal = 0

        for m in moves:
            to = (m >> 7) & 127
            quiet = sq[to] == EMPTY and not (m >> 14) & 7 and (m >> 17) != EN_PASSANT
            board.make(m)
            if board.is_attacked(board.king[us], -us):
                board.unmake()
                continue
            legal += 1

            if legal == 1:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1, True)
            else:
                reduction = 0
                if depth >= 3 and legal > 3 and quiet and not in_check and not board.in_check():
                    reduction = 1 if legal <= 8 else 2
                    if reduction >= depth - 1:
                        reduction = depth - 2
                score = -self._negamax(board, depth - 1 - reduction, -alpha - 1, -alpha,
                                       ply + 1, True)
                if score > alpha and (reduction or score < beta):
                    score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1, True)
            board.unmake()
            if self.stop:
                return 0

            if score > best_score:
                best_score, best_move = score, m
                if ply == 0:
                    self.root_best = m
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        if quiet:
                            killers = self.killers[ply]
                            if killers[0] != m:
                                killers[1], killers[0] = killers[0], m
                            row = self.history[sq[m & 127]]
                            row[to] += depth * depth
                            if row[to] > 500_000:
                                for r in self.history:
                                    for i in range(120):
                                        r[i] //= 2
                        break

        if legal == 0:
            return -MATE + ply if in_check else 0

        flag = LOWER if best_score >= beta else EXACT if best_score > original_alpha else UPPER
        self.tt[board.hash] = (depth, _score_to_tt(best_score, ply), flag, best_move)
        return best_score

    def _quiesce(self, board, alpha, beta, ply):
        self.nodes += 1
        if not self.nodes & 1023:
            self._check_limits()
        if self.stop:
            return 0

        if ply >= MAX_PLY:
            return evaluate(board)

        # In check, standing pat is not an option: every evasion must be
        # searched, and having none means we are mated.
        in_check = board.in_check()
        if in_check:
            stand_pat = -INF
            moves = board.gen_moves()
        else:
            stand_pat = evaluate(board)
            if stand_pat >= beta:
                return stand_pat
            if stand_pat > alpha:
                alpha = stand_pat
            moves = board.gen_moves(captures_only=True)

        us = board.side
        sq = board.sq
        legal = 0
        for m in self._order(board, moves, 0, ply):
            if not in_check:
                victim = sq[(m >> 7) & 127]
                gain = PIECE_VALUES[abs(victim)] if victim else 100
                # Delta pruning: even winning this piece can't lift us to alpha.
                if stand_pat + gain + 200 < alpha and not (m >> 14) & 7:
                    continue
            board.make(m)
            if board.is_attacked(board.king[us], -us):
                board.unmake()
                continue
            legal += 1
            score = -self._quiesce(board, -beta, -alpha, ply + 1)
            board.unmake()
            if self.stop:
                return 0
            if score > alpha:
                alpha = score
                if alpha >= beta:
                    break
        if in_check and not legal:
            return -MATE + ply
        return alpha

    # ---------------------------------------------------------------- helpers

    def _order(self, board, moves, tt_move, ply):
        sq = board.sq
        k1, k2 = self.killers[ply] if ply <= MAX_PLY else (0, 0)
        history = self.history
        scored = []
        for m in moves:
            if m == tt_move:
                s = 10_000_000
            else:
                frm, to = m & 127, (m >> 7) & 127
                victim = sq[to]
                if victim:
                    s = 1_000_000 + 10 * _MVV[abs(victim)] - abs(sq[frm])
                elif (m >> 17) == EN_PASSANT:
                    s = 1_000_009
                elif (m >> 14) & 7:
                    s = 900_000 + ((m >> 14) & 7)
                elif m == k1:
                    s = 800_000
                elif m == k2:
                    s = 700_000
                else:
                    s = history[sq[frm]][to]
            scored.append((s, m))
        scored.sort(reverse=True)
        return [m for _, m in scored]

    def _pv(self, board, depth):
        pv, seen = [], set()
        while len(pv) < depth:
            entry = self.tt.get(board.hash)
            if not entry or not entry[3] or board.hash in seen:
                break
            m = entry[3]
            if m not in board.legal_moves():
                break
            seen.add(board.hash)
            board.make(m)
            pv.append(m)
        for _ in pv:
            board.unmake()
        return pv


def _score_to_tt(score, ply):
    if score >= MATE_BOUND:
        return score + ply
    if score <= -MATE_BOUND:
        return score - ply
    return score


def _score_from_tt(score, ply):
    if score >= MATE_BOUND:
        return score - ply
    if score <= -MATE_BOUND:
        return score + ply
    return score


def format_pv(pv):
    return " ".join(move_to_uci(m) for m in pv)
