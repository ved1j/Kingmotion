"""Static evaluation: tapered material + piece-square tables, plus a few
pawn-structure and rook terms. Scores are centipawns from the side to move."""

from .board import (EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, SQUARES,
                    WHITE, square, file_of, rank_of)

PIECE_VALUES = [0, 100, 320, 330, 500, 900, 0]

# Tables are written from white's point of view, a8 first (as on a diagram).
_PAWN = [
     0,   0,   0,   0,   0,   0,   0,   0,
    50,  50,  50,  50,  50,  50,  50,  50,
    10,  10,  20,  30,  30,  20,  10,  10,
     5,   5,  10,  25,  25,  10,   5,   5,
     0,   0,   0,  20,  20,   0,   0,   0,
     5,  -5, -10,   0,   0, -10,  -5,   5,
     5,  10,  10, -20, -20,  10,  10,   5,
     0,   0,   0,   0,   0,   0,   0,   0,
]
_KNIGHT = [
   -50, -40, -30, -30, -30, -30, -40, -50,
   -40, -20,   0,   0,   0,   0, -20, -40,
   -30,   0,  10,  15,  15,  10,   0, -30,
   -30,   5,  15,  20,  20,  15,   5, -30,
   -30,   0,  15,  20,  20,  15,   0, -30,
   -30,   5,  10,  15,  15,  10,   5, -30,
   -40, -20,   0,   5,   5,   0, -20, -40,
   -50, -40, -30, -30, -30, -30, -40, -50,
]
_BISHOP = [
   -20, -10, -10, -10, -10, -10, -10, -20,
   -10,   0,   0,   0,   0,   0,   0, -10,
   -10,   0,   5,  10,  10,   5,   0, -10,
   -10,   5,   5,  10,  10,   5,   5, -10,
   -10,   0,  10,  10,  10,  10,   0, -10,
   -10,  10,  10,  10,  10,  10,  10, -10,
   -10,   5,   0,   0,   0,   0,   5, -10,
   -20, -10, -10, -10, -10, -10, -10, -20,
]
_ROOK = [
     0,   0,   0,   0,   0,   0,   0,   0,
     5,  10,  10,  10,  10,  10,  10,   5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
     0,   0,   0,   5,   5,   0,   0,   0,
]
_QUEEN = [
   -20, -10, -10,  -5,  -5, -10, -10, -20,
   -10,   0,   0,   0,   0,   0,   0, -10,
   -10,   0,   5,   5,   5,   5,   0, -10,
    -5,   0,   5,   5,   5,   5,   0,  -5,
     0,   0,   5,   5,   5,   5,   0,  -5,
   -10,   5,   5,   5,   5,   5,   0, -10,
   -10,   0,   5,   0,   0,   0,   0, -10,
   -20, -10, -10,  -5,  -5, -10, -10, -20,
]
_KING_MG = [
   -30, -40, -40, -50, -50, -40, -40, -30,
   -30, -40, -40, -50, -50, -40, -40, -30,
   -30, -40, -40, -50, -50, -40, -40, -30,
   -30, -40, -40, -50, -50, -40, -40, -30,
   -20, -30, -30, -40, -40, -30, -30, -20,
   -10, -20, -20, -20, -20, -20, -20, -10,
    20,  20,   0,   0,   0,   0,  20,  20,
    20,  30,  10,   0,   0,  10,  30,  20,
]
_KING_EG = [
   -50, -40, -30, -20, -20, -30, -40, -50,
   -30, -20, -10,   0,   0, -10, -20, -30,
   -30, -10,  20,  30,  30,  20, -10, -30,
   -30, -10,  30,  40,  40,  30, -10, -30,
   -30, -10,  30,  40,  40,  30, -10, -30,
   -30, -10,  20,  30,  30,  20, -10, -30,
   -30, -30,   0,   0,   0,   0, -30, -30,
   -50, -30, -30, -30, -30, -30, -30, -50,
]

_MG_TABLES = [None, _PAWN, _KNIGHT, _BISHOP, _ROOK, _QUEEN, _KING_MG]
_EG_TABLES = [None, _PAWN, _KNIGHT, _BISHOP, _ROOK, _QUEEN, _KING_EG]
EG_PAWN_VALUE = 120  # pawns grow in value as the board empties

PHASE_WEIGHT = [0, 0, 1, 1, 2, 4, 0]
MAX_PHASE = 24

PASSED_BONUS_MG = [0, 5, 10, 15, 25, 40, 60, 0]
PASSED_BONUS_EG = [0, 10, 20, 35, 60, 100, 150, 0]
DOUBLED_PENALTY = 15
ISOLATED_PENALTY = 12
BISHOP_PAIR = 30
ROOK_OPEN_FILE = 20
ROOK_SEMI_OPEN_FILE = 10
TEMPO = 10


def _build(tables, eg):
    """Merge material and PST into per-square lookups for each color."""
    white = [[0] * 120 for _ in range(7)]
    black = [[0] * 120 for _ in range(7)]
    for kind in range(1, 7):
        value = EG_PAWN_VALUE if (eg and kind == PAWN) else PIECE_VALUES[kind]
        for i, bonus in enumerate(tables[kind]):
            f, r = i % 8, 7 - i // 8
            white[kind][square(f, r)] = value + bonus
            black[kind][square(f, 7 - r)] = value + bonus
    return white, black


MG_WHITE, MG_BLACK = _build(_MG_TABLES, eg=False)
EG_WHITE, EG_BLACK = _build(_EG_TABLES, eg=True)


def evaluate(board):
    b = board.sq
    mg = eg = phase = 0
    white_pawns, black_pawns, white_rooks, black_rooks = [], [], [], []
    white_bishops = black_bishops = 0
    white_minors = black_minors = 0
    heavy = False

    for s in SQUARES:
        p = b[s]
        if p == EMPTY:
            continue
        if p > 0:
            mg += MG_WHITE[p][s]
            eg += EG_WHITE[p][s]
            phase += PHASE_WEIGHT[p]
            if p == PAWN:
                white_pawns.append(s)
            elif p == ROOK:
                white_rooks.append(s)
            elif p == BISHOP:
                white_bishops += 1
            if p == KNIGHT or p == BISHOP:
                white_minors += 1
            elif p == ROOK or p == QUEEN:
                heavy = True
        else:
            k = -p
            mg -= MG_BLACK[k][s]
            eg -= EG_BLACK[k][s]
            phase += PHASE_WEIGHT[k]
            if k == PAWN:
                black_pawns.append(s)
            elif k == ROOK:
                black_rooks.append(s)
            elif k == BISHOP:
                black_bishops += 1
            if k == KNIGHT or k == BISHOP:
                black_minors += 1
            elif k == ROOK or k == QUEEN:
                heavy = True

    if not white_pawns and not black_pawns and not heavy and white_minors + black_minors <= 1:
        return 0  # insufficient material

    # Pawn structure. Per file: counts, and the extreme ranks needed to
    # decide whether a pawn is passed.
    w_count, b_count = [0] * 10, [0] * 10  # padded: index file + 1
    w_lowest, b_highest = [8] * 10, [-1] * 10
    for s in white_pawns:
        f = file_of(s) + 1
        w_count[f] += 1
        w_lowest[f] = min(w_lowest[f], rank_of(s))
    for s in black_pawns:
        f = file_of(s) + 1
        b_count[f] += 1
        b_highest[f] = max(b_highest[f], rank_of(s))

    for s in white_pawns:
        f, r = file_of(s) + 1, rank_of(s)
        if b_highest[f - 1] <= r and b_highest[f] <= r and b_highest[f + 1] <= r:
            mg += PASSED_BONUS_MG[r]
            eg += PASSED_BONUS_EG[r]
        if not w_count[f - 1] and not w_count[f + 1]:
            mg -= ISOLATED_PENALTY
            eg -= ISOLATED_PENALTY
    for s in black_pawns:
        f, r = file_of(s) + 1, rank_of(s)
        if w_lowest[f - 1] >= r and w_lowest[f] >= r and w_lowest[f + 1] >= r:
            mg -= PASSED_BONUS_MG[7 - r]
            eg -= PASSED_BONUS_EG[7 - r]
        if not b_count[f - 1] and not b_count[f + 1]:
            mg += ISOLATED_PENALTY
            eg += ISOLATED_PENALTY
    for f in range(1, 9):
        if w_count[f] > 1:
            mg -= DOUBLED_PENALTY * (w_count[f] - 1)
            eg -= DOUBLED_PENALTY * (w_count[f] - 1)
        if b_count[f] > 1:
            mg += DOUBLED_PENALTY * (b_count[f] - 1)
            eg += DOUBLED_PENALTY * (b_count[f] - 1)

    for s in white_rooks:
        f = file_of(s) + 1
        if not w_count[f]:
            mg += ROOK_OPEN_FILE if not b_count[f] else ROOK_SEMI_OPEN_FILE
    for s in black_rooks:
        f = file_of(s) + 1
        if not b_count[f]:
            mg -= ROOK_OPEN_FILE if not w_count[f] else ROOK_SEMI_OPEN_FILE

    if white_bishops >= 2:
        mg += BISHOP_PAIR
        eg += BISHOP_PAIR
    if black_bishops >= 2:
        mg -= BISHOP_PAIR
        eg -= BISHOP_PAIR

    phase = min(phase, MAX_PHASE)
    score = (mg * phase + eg * (MAX_PHASE - phase)) // MAX_PHASE
    return (score if board.side == WHITE else -score) + TEMPO
