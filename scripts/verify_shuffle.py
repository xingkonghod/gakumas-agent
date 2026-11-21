"""决定性验证：seed + 考试时刻牌堆 → xorshift32 洗牌 → 牌序与实战逐回合手牌对照。

原理：回合末手牌全进弃牌堆（ResetHand），故每回合开始手牌 = 当回合从牌堆顶抽的
turnStartDistribute(=3) 张。牌堆抽完前，洗牌后的牌序 = 各回合手牌依次拼接。
期中 18 张 = 前 6 回合正好抽完，可整段对照（无需弃牌堆重洗）。

用法：python scripts/verify_shuffle.py [--file PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from dig_deck import body, parse
from verify_seed import NativeRandom

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
SNAP = Path(r"C:\GakumasLocal\GakumasUnlock\out\deck_snapshots.json")


def fmap(nodes):
    out = {}
    for f, w, v, _ in nodes:
        out.setdefault(f, []).append(v)
    return out


def inner(v):
    return v[1] if isinstance(v, tuple) and len(v) == 2 else None


def card_id_up(v):
    inn = inner(v)
    if inn is None:
        return ("?", 0)
    m = fmap(inn)
    raw = m.get(1, [None])[0]
    cid = raw[0].decode() if isinstance(raw, tuple) else (raw.decode() if isinstance(raw, bytes) else raw)
    up = m.get(2, [0])[0]
    return (cid, up)


def get_seed(resp: bytes) -> int | None:
    for f, w, v, _ in parse(resp):
        pass
    # field 600 在 progress 里；直接全树找
    from dig_deck import walk
    for path, field, wire, value, off in walk(parse(resp)):
        if field == 600 and wire == 0 and 0 < value < 2**31:
            return value
    return None


def truth_hands(req: bytes) -> list[list[tuple[str, int]]]:
    top = fmap(parse(req))
    hands = []
    for tl in top.get(3, []):
        inn = inner(tl)
        if inn is None:
            continue
        m = fmap(inn)
        hands.append([card_id_up(v) for v in m.get(50, [])])
    return hands


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    args = ap.parse_args(argv)

    records = [json.loads(l) for l in Path(args.file).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    starts = [r for r in records if r.get("path", "").endswith("StepAuditionStart")]
    ends = [r for r in records if r.get("path", "").endswith("StepAuditionEndExamBattle")]
    snaps = json.loads(SNAP.read_text(encoding="utf-8"))
    print(f"StepAuditionStart={len(starts)}  EndExamBattle={len(ends)}  牌堆快照={len(snaps)}\n")

    for i, end in enumerate(ends):
        deck_cards = snaps[i]["deck"]
        deck_cards = sorted(deck_cards, key=lambda c: c["number"])
        deck = [(c["id"], c["upgrade"]) for c in deck_cards]
        seed = get_seed(body(starts[i], "resp_plain_hex"))
        hands = truth_hands(body(end, "req_plain_hex"))
        n = len(deck)
        # 期望牌序 = 各回合手牌拼接，取前 n 张（牌堆抽完前）
        expected = [c for h in hands for c in h][:n]
        print(f"=== 考试 {i}（{end.get('ts')}）seed=0x{seed:08X} 牌堆 {n} 张，回合数 {len(hands)} ===")

        # Mode A：直接洗牌
        rng = NativeRandom(seed)
        shuffled = list(deck)
        rng.shuffle(shuffled)
        match_id = sum(1 for a, b in zip(shuffled, expected) if a[0] == b[0])
        match_full = sum(1 for a, b in zip(shuffled, expected) if a == b)
        print(f"  Mode A（seed 直接洗牌）: id 匹配 {match_id}/{len(expected)}，id+强化 匹配 {match_full}/{len(expected)}")
        if match_full == len(expected):
            print("  ✅ 完全一致！seed + 牌堆 → 牌序 验证通过")
        else:
            print("  洗牌后前 18:", [f"{c[0].split('-', 2)[-1]}+{c[1]}" for c in shuffled[:18]])
            print("  期望前 18:  ", [f"{c[0].split('-', 2)[-1]}+{c[1]}" for c in expected[:18]])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
