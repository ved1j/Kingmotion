"""Board representation, move generation and FEN handling.

Kingmotion uses a 10x12 "mailbox" board: 120 squares where the inner 8x8
holds the real board and the border is filled with OFF sentinels, so that
sliding pieces and knights can detect the edge without bounds checks.

Pieces are signed ints: positive for white, negative for black.
Moves are packed ints: from | to << 7 | promo << 14 | flag << 17.
"""

import random

EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 0, 1, 2, 3, 4, 5, 6
OFF = 7
WHITE, BLACK = 1, -1

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def square(file, rank):
    return 21 + file + 10 * rank


def file_of(s):
    return (s - 21) % 10


def rank_of(s):
    return (s - 21) // 10


def square_name(s):
    return "abcdefgh"[file_of(s)] + str(rank_of(s) + 1)


def parse_square(name):
    return square("abcdefgh".index(name[0]), int(name[1]) - 1)


SQUARES = [square(f, r) for r in range(8) for f in range(8)]

KNIGHT_DIRS = (21, 19, 12, 8, -8, -12, -19, -21)
BISHOP_DIRS = (11, 9, -9, -11)
ROOK_DIRS = (10, -10, 1, -1)
KING_DIRS = BISHOP_DIRS + ROOK_DIRS

# Castling rights bits
WK, WQ, BK, BQ = 1, 2, 4, 8
CASTLE_MASK = [15] * 120
CASTLE_MASK[square(4, 0)] = 15 & ~(WK | WQ)
CASTLE_MASK[square(7, 0)] = 15 & ~WK
CASTLE_MASK[square(0, 0)] = 15 & ~WQ
CASTLE_MASK[square(4, 7)] = 15 & ~(BK | BQ)
CASTLE_MASK[square(7, 7)] = 15 & ~BK
CASTLE_MASK[square(0, 7)] = 15 & ~BQ

# Move flags
NORMAL, EN_PASSANT, CASTLE, DOUBLE_PUSH = 0, 1, 2, 3


def encode_move(frm, to, promo=0, flag=NORMAL):
    return frm | (to << 7) | (promo << 14) | (flag << 17)


def move_from(m):
    return m & 127


def move_to(m):
    return (m >> 7) & 127


def move_promo(m):
    return (m >> 14) & 7


def move_flag(m):
    return m >> 17


def move_to_uci(m):
    promo = move_promo(m)
    s = square_name(move_from(m)) + square_name(move_to(m))
    return s + " pnbrqk"[promo] if promo else s


# Zobrist keys. Indexing Z_PIECE with a negative piece wraps to the end of
# the list, which gives black pieces their own keys for free.
_rng = random.Random(0x4B696E67)
Z_PIECE = [[_rng.getrandbits(64) for _ in range(120)] for _ in range(13)]
Z_CASTLE = [_rng.getrandbits(64) for _ in range(16)]
Z_EP = [_rng.getrandbits(64) for _ in range(8)]
Z_SIDE = _rng.getrandbits(64)


class Board:
    def __init__(self, fen=START_FEN):
        self.set_fen(fen)

    # ------------------------------------------------------------------ FEN

    def set_fen(self, fen):
        parts = fen.split()
        self.sq = [OFF] * 120
        for s in SQUARES:
            self.sq[s] = EMPTY
        self.king = [0, 0, 0]  # king[WHITE], king[BLACK] (index -1)
        for i, row in enumerate(parts[0].split("/")):
            rank, f = 7 - i, 0
            for c in row:
                if c.isdigit():
                    f += int(c)
                    continue
                kind = "pnbrqk".index(c.lower()) + 1
                piece = kind if c.isupper() else -kind
                self.sq[square(f, rank)] = piece
                if kind == KING:
                    self.king[WHITE if piece > 0 else BLACK] = square(f, rank)
                f += 1
        self.side = WHITE if len(parts) < 2 or parts[1] == "w" else BLACK
        rights = parts[2] if len(parts) > 2 else "-"
        self.castling = ((WK if "K" in rights else 0) | (WQ if "Q" in rights else 0)
                         | (BK if "k" in rights else 0) | (BQ if "q" in rights else 0))
        ep = parts[3] if len(parts) > 3 else "-"
        self.ep = parse_square(ep) if ep != "-" else 0
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1
        self.stack = []
        self.hash = self._compute_hash()
        self.history = [self.hash]

    def fen(self):
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.sq[square(f, rank)]
                if p == EMPTY:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                c = " pnbrqk"[abs(p)]
                row += c.upper() if p > 0 else c
            rows.append(row + (str(empty) if empty else ""))
        rights = "".join(c for bit, c in ((WK, "K"), (WQ, "Q"), (BK, "k"), (BQ, "q"))
                         if self.castling & bit) or "-"
        ep = square_name(self.ep) if self.ep else "-"
        side = "w" if self.side == WHITE else "b"
        return f"{'/'.join(rows)} {side} {rights} {ep} {self.halfmove} {self.fullmove}"

    def _compute_hash(self):
        h = 0
        for s in SQUARES:
            if self.sq[s] != EMPTY:
                h ^= Z_PIECE[self.sq[s]][s]
        h ^= Z_CASTLE[self.castling]
        if self.ep:
            h ^= Z_EP[file_of(self.ep)]
        if self.side == BLACK:
            h ^= Z_SIDE
        return h

    def __str__(self):
        lines = []
        for rank in range(7, -1, -1):
            row = []
            for f in range(8):
                p = self.sq[square(f, rank)]
                c = " pnbrqk"[abs(p)] if p else "."
                row.append(c.upper() if p > 0 else c)
            lines.append(f"{rank + 1}  {' '.join(row)}")
        lines.append("   a b c d e f g h")
        return "\n".join(lines)

    # -------------------------------------------------------------- attacks

    def is_attacked(self, s, by):
        """Is square s attacked by side `by`?"""
        b = self.sq
        if by == WHITE:
            if b[s - 9] == PAWN or b[s - 11] == PAWN:
                return True
        elif b[s + 9] == -PAWN or b[s + 11] == -PAWN:
            return True
        knight = KNIGHT * by
        for d in KNIGHT_DIRS:
            if b[s + d] == knight:
                return True
        king = KING * by
        for d in KING_DIRS:
            if b[s + d] == king:
                return True
        bishop, rook, queen = BISHOP * by, ROOK * by, QUEEN * by
        for d in BISHOP_DIRS:
            t = s + d
            while b[t] == EMPTY:
                t += d
            if b[t] == bishop or b[t] == queen:
                return True
        for d in ROOK_DIRS:
            t = s + d
            while b[t] == EMPTY:
                t += d
            if b[t] == rook or b[t] == queen:
                return True
        return False

    def in_check(self):
        return self.is_attacked(self.king[self.side], -self.side)

    # ------------------------------------------------------- move generation

    def gen_moves(self, captures_only=False):
        """Pseudo-legal moves. With captures_only, also queen promotions."""
        moves = []
        add = moves.append
        b = self.sq
        us = self.side
        for s in SQUARES:
            p = b[s] * us
            if p <= 0:
                continue
            if p == PAWN:
                fwd = 10 * us
                last_rank = 7 if us == WHITE else 0
                t = s + fwd
                if b[t] == EMPTY:
                    if rank_of(t) == last_rank:
                        add(encode_move(s, t, QUEEN))
                        if not captures_only:
                            for promo in (KNIGHT, ROOK, BISHOP):
                                add(encode_move(s, t, promo))
                    elif not captures_only:
                        add(encode_move(s, t))
                        start_rank = 1 if us == WHITE else 6
                        if rank_of(s) == start_rank and b[t + fwd] == EMPTY:
                            add(encode_move(s, t + fwd, 0, DOUBLE_PUSH))
                for t in (s + fwd - 1, s + fwd + 1):
                    q = b[t]
                    if q != OFF and q * us < 0:
                        if rank_of(t) == last_rank:
                            add(encode_move(s, t, QUEEN))
                            if not captures_only:
                                for promo in (KNIGHT, ROOK, BISHOP):
                                    add(encode_move(s, t, promo))
                        else:
                            add(encode_move(s, t))
                    elif t == self.ep:
                        add(encode_move(s, t, 0, EN_PASSANT))
            elif p == KNIGHT or p == KING:
                for d in (KNIGHT_DIRS if p == KNIGHT else KING_DIRS):
                    t = s + d
                    q = b[t]
                    if q == EMPTY:
                        if not captures_only:
                            add(encode_move(s, t))
                    elif q != OFF and q * us < 0:
                        add(encode_move(s, t))
            else:
                dirs = BISHOP_DIRS if p == BISHOP else ROOK_DIRS if p == ROOK else KING_DIRS
                for d in dirs:
                    t = s + d
                    while b[t] == EMPTY:
                        if not captures_only:
                            add(encode_move(s, t))
                        t += d
                    q = b[t]
                    if q != OFF and q * us < 0:
                        add(encode_move(s, t))
        if not captures_only and self.castling:
            self._gen_castles(add)
        return moves

    def _gen_castles(self, add):
        b, us, them = self.sq, self.side, -self.side
        e = square(4, 0 if us == WHITE else 7)
        if b[e] != KING * us:
            return
        short, long_ = (WK, WQ) if us == WHITE else (BK, BQ)
        if (self.castling & short and b[e + 1] == EMPTY and b[e + 2] == EMPTY
                and b[e + 3] == ROOK * us and not self.is_attacked(e, them)
                and not self.is_attacked(e + 1, them) and not self.is_attacked(e + 2, them)):
            add(encode_move(e, e + 2, 0, CASTLE))
        if (self.castling & long_ and b[e - 1] == EMPTY and b[e - 2] == EMPTY
                and b[e - 3] == EMPTY and b[e - 4] == ROOK * us and not self.is_attacked(e, them)
                and not self.is_attacked(e - 1, them) and not self.is_attacked(e - 2, them)):
            add(encode_move(e, e - 2, 0, CASTLE))

    def legal_moves(self):
        us = self.side
        legal = []
        for m in self.gen_moves():
            self.make(m)
            if not self.is_attacked(self.king[us], -us):
                legal.append(m)
            self.unmake()
        return legal

    def parse_uci(self, text):
        """Return the legal move matching a UCI string like 'e2e4', or None."""
        text = text.strip().lower()
        for m in self.legal_moves():
            if move_to_uci(m) == text:
                return m
        return None

    def san(self, m, legal=None):
        """Standard algebraic notation for a legal move, e.g. 'Nbd7', 'exd6+'."""
        b = self.sq
        frm, to, promo, flag = m & 127, (m >> 7) & 127, (m >> 14) & 7, m >> 17
        kind = abs(b[frm])
        if flag == CASTLE:
            text = "O-O" if to > frm else "O-O-O"
        else:
            capture = b[to] != EMPTY or flag == EN_PASSANT
            if kind == PAWN:
                text = ("abcdefgh"[file_of(frm)] + "x" if capture else "") + square_name(to)
                if promo:
                    text += "=" + " PNBRQK"[promo]
            else:
                text = " PNBRQK"[kind]
                if legal is None:
                    legal = self.legal_moves()
                rivals = [move_from(o) for o in legal
                          if o != m and move_to(o) == to and abs(b[move_from(o)]) == kind]
                if rivals:
                    if all(file_of(r) != file_of(frm) for r in rivals):
                        text += "abcdefgh"[file_of(frm)]
                    elif all(rank_of(r) != rank_of(frm) for r in rivals):
                        text += str(rank_of(frm) + 1)
                    else:
                        text += square_name(frm)
                text += ("x" if capture else "") + square_name(to)
        self.make(m)
        if self.in_check():
            text += "#" if not self.legal_moves() else "+"
        self.unmake()
        return text

    def parse_move(self, text):
        """Accept a move in UCI ('g1f3') or SAN ('Nf3', 'O-O', 'exd5')."""
        move = self.parse_uci(text)
        if move is not None:
            return move
        wanted = text.strip().rstrip("+#!?").replace("0", "O")
        legal = self.legal_moves()
        for m in legal:
            if self.san(m, legal).rstrip("+#") == wanted:
                return m
        return None

    # ------------------------------------------------------------ make/unmake

    def make(self, m):
        b = self.sq
        frm, to = m & 127, (m >> 7) & 127
        promo, flag = (m >> 14) & 7, m >> 17
        us = self.side
        piece = b[frm]
        captured = b[to]
        self.stack.append((m, captured, self.castling, self.ep, self.halfmove, self.hash))

        h = self.hash ^ Z_PIECE[piece][frm]
        if captured:
            h ^= Z_PIECE[captured][to]
        b[frm] = EMPTY
        if flag == EN_PASSANT:
            cs = to - 10 * us
            h ^= Z_PIECE[b[cs]][cs]
            b[cs] = EMPTY
        elif flag == CASTLE:
            rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            rook = b[rf]
            b[rt], b[rf] = rook, EMPTY
            h ^= Z_PIECE[rook][rf] ^ Z_PIECE[rook][rt]
        placed = promo * us if promo else piece
        b[to] = placed
        h ^= Z_PIECE[placed][to]
        if piece == KING * us:
            self.king[us] = to

        if self.ep:
            h ^= Z_EP[file_of(self.ep)]
        self.ep = (frm + to) // 2 if flag == DOUBLE_PUSH else 0
        if self.ep:
            h ^= Z_EP[file_of(self.ep)]

        h ^= Z_CASTLE[self.castling]
        self.castling &= CASTLE_MASK[frm] & CASTLE_MASK[to]
        h ^= Z_CASTLE[self.castling]

        if captured or piece == PAWN * us:
            self.halfmove = 0
        else:
            self.halfmove += 1
        if us == BLACK:
            self.fullmove += 1
        self.side = -us
        h ^= Z_SIDE
        self.hash = h
        self.history.append(h)

    def unmake(self):
        m, captured, self.castling, self.ep, self.halfmove, self.hash = self.stack.pop()
        self.history.pop()
        self.side = us = -self.side
        if us == BLACK:
            self.fullmove -= 1
        b = self.sq
        frm, to = m & 127, (m >> 7) & 127
        flag = m >> 17
        piece = PAWN * us if (m >> 14) & 7 else b[to]
        b[frm] = piece
        b[to] = captured
        if flag == EN_PASSANT:
            b[to - 10 * us] = -PAWN * us
        elif flag == CASTLE:
            rf, rt = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            b[rf], b[rt] = b[rt], EMPTY
        if piece == KING * us:
            self.king[us] = frm

    def make_null(self):
        self.stack.append((0, EMPTY, self.castling, self.ep, self.halfmove, self.hash))
        h = self.hash ^ Z_SIDE
        if self.ep:
            h ^= Z_EP[file_of(self.ep)]
            self.ep = 0
        self.halfmove = 0  # repetitions never span a null move
        self.side = -self.side
        self.hash = h
        self.history.append(h)

    def unmake_null(self):
        _, _, self.castling, self.ep, self.halfmove, self.hash = self.stack.pop()
        self.history.pop()
        self.side = -self.side

    # ------------------------------------------------------------ game state

    def is_repetition(self):
        """True if the current position occurred before (since the last
        irreversible move). Used inside search, where one repeat is a draw."""
        h, hist = self.hash, self.history
        n = len(hist)
        for i in range(n - 3, max(-1, n - 2 - self.halfmove), -2):
            if hist[i] == h:
                return True
        return False

    def repetition_count(self):
        return self.history.count(self.hash)

    def has_non_pawn_material(self, side):
        b = self.sq
        for s in SQUARES:
            p = b[s] * side
            if KNIGHT <= p <= QUEEN:
                return True
        return False

    def insufficient_material(self):
        minors = 0
        for s in SQUARES:
            p = abs(self.sq[s])
            if p in (PAWN, ROOK, QUEEN):
                return False
            if p in (KNIGHT, BISHOP):
                minors += 1
                if minors > 1:
                    return False
        return True

    def outcome(self):
        """None if the game goes on, otherwise a human-readable result."""
        if not self.legal_moves():
            if self.in_check():
                return "0-1 (checkmate)" if self.side == WHITE else "1-0 (checkmate)"
            return "1/2-1/2 (stalemate)"
        if self.halfmove >= 100:
            return "1/2-1/2 (fifty-move rule)"
        if self.repetition_count() >= 3:
            return "1/2-1/2 (threefold repetition)"
        if self.insufficient_material():
            return "1/2-1/2 (insufficient material)"
        return None


def perft(board, depth):
    """Count leaf nodes of the legal move tree; used to verify movegen."""
    if depth == 0:
        return 1
    us = board.side
    nodes = 0
    for m in board.gen_moves():
        board.make(m)
        if not board.is_attacked(board.king[us], -us):
            nodes += perft(board, depth - 1) if depth > 1 else 1
        board.unmake()
    return nodes
