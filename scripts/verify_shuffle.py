"""洗牌重放验证：examSeedValue + 考试牌堆 → 精确牌序。

已验证模型（2026-11-21 期中，18/18 整段精确匹配）：
  deck = 牌堆按 number 升序（Number 升序）
  rng  = xorshift32(examSeedValue)，洗牌前先 advance K=51 次
  洗牌 = Fisher-Yates 倒序（n=len..2, j=integer(0,n), swap(a[j],a[n-1])）
  发牌 = 每回合从牌堆顶抽 turnStartDistribute(=3) 张，回合末全部进弃牌堆
  → 牌堆抽完前，牌序 = 各回合开始手牌依次拼接

期中 ✅ 18/18（K=51）。期末 ⚠️ 复现不出（见 TROUBLESHOOTING 3.6），保留搜索能力。

用法：python scripts/verify_shuffle.py [--k 51] [--max-k 2000]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from dig_deck import body, parse, walk

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
SNAP = Path(r"C:\GakumasLocal\GakumasUnlock\out\deck_snapshots.json")
MASK = 0xFFFFFFFF


class NativeRandom:
    """客户端 System.Random 替身：xorshift32（与 gakumas_exam.rng 一致）。"""

    def __init__(self, state: int) -> None:
        self.state = state & MASK

    def _advance(self) -> int:
        old = self.state
        x = (old ^ (old << 13)) & MASK
        x = (x ^ (x >> 17)) & MASK
        self.state = (x ^ (x << 5)) & MASK
        return old

    def integer(self, low: int, high: int) -> int:
        return low + ((self._advance() * (high - low)) >> 32)


def shuffle(values: list, rng: NativeRandom) -> None:
    for n in range(len(values), 1, -1):
        j = rng.integer(0, n)
        values[j], values[n - 1] = values[n - 1], values[j]


def fmap(nodes):
    out = {}
    for f, w, v, _ in nodes:
        out.setdefault(f, []).append(v)
    return out


def inner(v):
    return v[1] if isinstance(v, tuple) and len(v) == 2 else None


def card_of(v) -> tuple[str, int] | None:
    m = fmap(inner(v))
    raw = m.get(1, [None])[0]
    if raw is None:
        return None
    cid = raw[0].decode() if isinstance(raw, tuple) else raw.decode()
    return cid, m.get(2, [0])[0]


def get_seed(resp: bytes) -> int | None:
    for _path, field, wire, value, _off in walk(parse(resp)):
        if field == 600 and wire == 0 and 0 < value < 2**31:
            return value
    return None


def truth_hands(req: bytes) -> list[list[tuple[str, int]]]:
    top = fmap(parse(req))
    return [[c for c in (card_of(v) for v in fmap(inner(tl)).get(50, [])) if c] for tl in top.get(3, [])]


def load_exams(path: Path) -> list[dict]:
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    starts = [r for r in recs if r.get("path", "").endswith("StepAuditionStart")]
    ends = [r for r in recs if r.get("path", "").endswith("StepAuditionEndExamBattle")]
    snaps = json.loads(SNAP.read_text(encoding="utf-8"))
    out = []
    for i, end in enumerate(ends):
        deck = sorted(snaps[i]["deck"], key=lambda c: c["number"])
        seed = get_seed(body(starts[i], "resp_plain_hex"))
        hands = truth_hands(body(end, "req_plain_hex"))
        out.append({
            "i": i, "seed": seed, "ts": end.get("ts"), "deck": deck,
            "expected": [c for h in hands for c in h], "chunks": [{x[0] for x in h} for h in hands],
        })
    return out


def attempt(seed: int, deck: list, expected: list, chunks: list, k: int) -> tuple[int, int]:
    rng = NativeRandom(seed)
    for _ in range(k):
        rng._advance()
    sh = list(deck)
    shuffle(sh, rng)
    exact = sum(1 for a, b in zip(sh, expected) if a == b)
    sets = sum(1 for j in range(len(chunks)) if {x[0] for x in sh[j * 3 : j * 3 + 3]} == chunks[j])
    return exact, sets


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--k", type=int, default=None, help="洗牌前 RNG 消耗次数（不给则搜索）")
    ap.add_argument("--max-k", type=int, default=2000)
    args = ap.parse_args(argv)

    for ex in load_exams(Path(args.file)):
        deck = [(c["id"], c["upgrade"]) for c in ex["deck"]]
        expected = ex["expected"][: len(deck)]
        chunks = ex["chunks"][: len(deck) // 3]
        print(f"\n=== 考试{ex['i']} {ex['ts']} seed=0x{ex['seed']:08X} 牌堆 {len(deck)} 张 ===")

        if args.k is not None:
            exact, sets = attempt(ex["seed"], deck, expected, chunks, args.k)
            print(f"  k={args.k}: 整段精确 {exact}/{len(expected)}，回合集合 {sets}/{len(chunks)}")
            continue
        best = []
        for k in range(args.max_k + 1):
            exact, sets = attempt(ex["seed"], deck, expected, chunks, k)
            if sets == len(chunks):
                print(f"  ✅ k={k}: 回合集合全中，整段精确 {exact}/{len(expected)}")
                break
            best.append((sets, exact, k))
        else:
            best.sort(reverse=True)
            print(f"  ⚠️ k=0..{args.max_k} 无全中；最接近 (集合,整段,k) = {best[:3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
