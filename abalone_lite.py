#!/usr/bin/env python3
"""abalone-lite: 极简 Abalone 推珠棋（纯标准库）。

规则（简化版）：
- 六角棋盘（轴向坐标，半径 3，共 37 格），双方各 8 子。
- 每回合选 1~3 枚同色、沿一条直线相连的棋子，沿 6 个方向之一走一格。
- 直线推进（inline）：若前方是空位直接走；若前方是 1~2 枚敌子且
  己方数量严格大于敌方数量，可将其推挤（sumito）；被推出棋盘的敌子被吃掉。
- 侧移（broadside）：所有落点必须为空。
- 先吃掉对方 4 子者获胜（标准版是 6 子，这里棋盘更小故取 4）。
"""

import argparse
import random
import sys

R = 3                      # 棋盘半径（37 格）
PUSH_TO_WIN = 4            # 吃掉 4 子获胜
MAX_HALF = 400             # 半回合上限，防无限对局

BLACK, WHITE, EMPTY = "B", "W", "."

# 轴向坐标 6 个方向
DIRS = [(1, 0), (-1, 0), (1, -1), (-1, 1), (0, -1), (0, 1)]


def on_board(cell):
    q, r = cell
    return max(abs(q), abs(r), abs(q + r)) <= R


def all_cells():
    return [(q, r) for q in range(-R, R + 1)
            for r in range(-R, R + 1) if on_board((q, r))]


def setup():
    """开局：黑在上两排，白在下两排，各 8 子。"""
    board = {c: EMPTY for c in all_cells()}
    for q in range(0, 4):
        board[(q, -3)] = BLACK
    for q in range(-1, 3):
        board[(q, -2)] = BLACK
    for q in range(-3, 1):
        board[(q, 3)] = WHITE
    for q in range(-2, 2):
        board[(q, 2)] = WHITE
    return board


def other(p):
    return WHITE if p == BLACK else BLACK


class Abalone:
    def __init__(self):
        self.board = setup()
        self.captured = {BLACK: 0, WHITE: 0}  # 各方吃掉的敌子数
        self.turn = BLACK
        self.halfmoves = 0

    # ---------- 基础 ----------

    def marbles(self, p):
        return [c for c, v in self.board.items() if v == p]

    def lines(self, p):
        """枚举该方所有 1~3 子直线组合（有序，去重）。"""
        seen = set()
        out = []
        for (q, r) in self.marbles(p):
            for d in DIRS:
                line = [(q, r)]
                for _ in range(2):
                    nq, nr = line[-1][0] + d[0], line[-1][1] + d[1]
                    if self.board.get((nq, nr)) == p:
                        line.append((nq, nr))
                    else:
                        break
                key = frozenset(line)
                if key not in seen:
                    seen.add(key)
                    out.append(line)
        return out

    # ---------- 走法 ----------

    def _try_move(self, p, line, d):
        """尝试把 line 沿 d 走一格；合法返回 (线集合, 方向, 新旧对, 吃子数, 是否推挤)。"""
        opp = other(p)
        if len(line) == 1:
            t = (line[0][0] + d[0], line[0][1] + d[1])
            if on_board(t) and self.board[t] == EMPTY:
                return (frozenset(line), d, [(line[0], t)], 0, False)
            return None
        ax = (line[1][0] - line[0][0], line[1][1] - line[0][1])
        if d == ax or d == (-ax[0], -ax[1]):
            # 直线推进（含推挤）
            ordered = sorted(line, key=lambda c: c[0] * d[0] + c[1] * d[1])
            head = ordered[-1]
            front = (head[0] + d[0], head[1] + d[1])
            if not on_board(front):
                return None  # 不能把自己的子走出棋盘
            fv = self.board[front]
            if fv == p:
                return None
            if fv == EMPTY:
                pairs = [(c, (c[0] + d[0], c[1] + d[1])) for c in line]
                return (frozenset(line), d, pairs, 0, False)
            # 推挤：数敌子
            n = len(line)
            oc = []
            c = front
            while on_board(c) and self.board[c] == opp:
                oc.append(c)
                c = (c[0] + d[0], c[1] + d[1])
            m = len(oc)
            if n <= m:
                return None  # 数量不占优，不能推
            landing = c
            if on_board(landing) and self.board[landing] != EMPTY:
                return None  # 后面被堵住
            moving = list(line) + oc
            pairs = [(x, (x[0] + d[0], x[1] + d[1])) for x in moving]
            captured = sum(1 for _, t in pairs if not on_board(t))
            return (frozenset(line), d, pairs, captured, True)
        # 侧移：落点全空且在盘内
        targets = [(c[0] + d[0], c[1] + d[1]) for c in line]
        if all(on_board(t) and self.board[t] == EMPTY for t in targets):
            return (frozenset(line), d, list(zip(line, targets)), 0, False)
        return None

    def gen_moves(self, p):
        moves = []
        for line in self.lines(p):
            for d in DIRS:
                mv = self._try_move(p, line, d)
                if mv:
                    moves.append(mv)
        return moves

    def apply(self, mv):
        """执行走法，返回本方（走完后轮到对方）。"""
        _, _, pairs, captured, _ = mv
        mover = self.board[pairs[0][0]]
        colors = {old: self.board[old] for old, _new in pairs}
        for old, _new in pairs:
            self.board[old] = EMPTY
        for old, new in pairs:
            if on_board(new):
                self.board[new] = colors[old]
        self.captured[mover] += captured
        self.halfmoves += 1
        self.turn = other(mover)
        return mover

    def winner(self):
        for p in (BLACK, WHITE):
            if self.captured[p] >= PUSH_TO_WIN:
                return p
        return None

    # ---------- AI ----------

    def _eval(self, p, mv):
        opp = other(p)
        b = dict(self.board)
        _, _, pairs, captured, pushed = mv
        for old, _new in pairs:
            b[old] = EMPTY
        for _old, new in pairs:
            if on_board(new):
                b[new] = p
        my_on = sum(1 for v in b.values() if v == p)
        op_on = sum(1 for v in b.values() if v == opp)
        my_c = self.captured[p] + captured
        op_c = self.captured[opp]
        center = sum(max(abs(q), abs(r), abs(q + r))
                     for (q, r), v in b.items() if v == p)
        return (50 * (my_c - op_c) + (my_on - op_on)
                - 0.2 * center + (3 if pushed else 0))

    def ai_pick(self, p, moves, rng):
        best = None
        bestkey = None
        for mv in moves:
            k = (self._eval(p, mv), rng.random())
            if bestkey is None or k > bestkey:
                bestkey = k
                best = mv
        return best

    # ---------- 渲染 ----------

    def render(self):
        name = {BLACK: "黑", WHITE: "白", EMPTY: "·"}
        lines = []
        for r in range(-R, R + 1):
            cells = [(q, r) for q in range(-R, R + 1) if on_board((q, r))]
            indent = "  " * (R - r)
            row = indent + " ".join(name[self.board[c]] for c in cells)
            lines.append(f"{r + R + 1:>2} {row}")
        return "\n".join(lines)

    def move_str(self, mv):
        line, d, _pairs, cap, pushed = mv
        cells = sorted(line)
        tag = "推挤" if pushed else "走子"
        extra = f" 吃{cap}" if cap else ""
        return f"{tag}{cells}→{d}{extra}"


def play_auto_game(rng, verbose=False):
    g = Abalone()
    while g.halfmoves < MAX_HALF:
        moves = g.gen_moves(g.turn)
        if not moves:
            return (other(g.turn), "困死", g)
        mv = g.ai_pick(g.turn, moves, rng)
        p = g.turn
        if verbose:
            print(f"[{g.halfmoves}] {'黑' if p == BLACK else '白'}: {g.move_str(mv)}")
        g.apply(mv)
        w = g.winner()
        if w:
            return (w, f"吃子达到{PUSH_TO_WIN}", g)
    nb = len(g.marbles(BLACK))
    nw = len(g.marbles(WHITE))
    if nb > nw:
        return (BLACK, "子多", g)
    if nw > nb:
        return (WHITE, "子多", g)
    return (None, "和棋", g)


def play_interactive(side, seed):
    rng = random.Random(seed)
    human = BLACK if side == "b" else WHITE
    g = Abalone()
    print("abalone-lite：输入走法编号，q 退出。")
    while True:
        print()
        print(g.render())
        print(f"已吃：黑吃白 {g.captured[BLACK]} / 白吃黑 {g.captured[WHITE]}"
              f"（{PUSH_TO_WIN} 子胜）")
        w = g.winner()
        if w:
            print(f"{'黑' if w == BLACK else '白'}方获胜！")
            return
        if g.halfmoves >= MAX_HALF:
            print("达到步数上限，对局结束。")
            return
        moves = g.gen_moves(g.turn)
        if not moves:
            print(f"{'黑' if g.turn == BLACK else '白'}方无棋可走，判负。")
            return
        if g.turn == human:
            for i, mv in enumerate(moves):
                print(f"  {i:>3}: {g.move_str(mv)}")
            s = input(f"轮到你（{'黑' if human == BLACK else '白'}），选 0-{len(moves)-1}：").strip()
            if s.lower() == "q":
                print("退出。")
                return
            try:
                idx = int(s)
                mv = moves[idx]
            except (ValueError, IndexError):
                print("编号无效，重选。")
                continue
            g.apply(mv)
        else:
            mv = g.ai_pick(g.turn, moves, rng)
            print(f"AI（{'黑' if g.turn == BLACK else '白'}）走：{g.move_str(mv)}")
            g.apply(mv)


def main(argv=None):
    ap = argparse.ArgumentParser(description="abalone-lite：极简推珠棋")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=5, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--side", choices=["b", "w"], default="b", help="人机对战时人类执子")
    ap.add_argument("--verbose", action="store_true", help="自动演示打印每步")
    args = ap.parse_args(argv)

    if args.auto:
        rng = random.Random(args.seed)
        res = {BLACK: 0, WHITE: 0, None: 0}
        for i in range(args.games):
            w, why, g = play_auto_game(rng, verbose=args.verbose)
            res[w] += 1
            print(f"第 {i+1}/{args.games} 局："
                  f"{'黑胜' if w == BLACK else '白胜' if w == WHITE else '和棋'}"
                  f"（{why}，{g.halfmoves} 半回合，"
                  f"黑吃 {g.captured[BLACK]} 白吃 {g.captured[WHITE]}）")
        print(f"总计：黑胜 {res[BLACK]}，白胜 {res[WHITE]}，和棋 {res[None]}")
        return

    if not sys.stdin.isatty():
        print("交互模式需要终端；无头演示请用 --auto", file=sys.stderr)
        sys.exit(2)
    play_interactive(args.side, args.seed)


if __name__ == "__main__":
    main()
