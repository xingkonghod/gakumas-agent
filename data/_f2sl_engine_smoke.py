"""GKMSMainWheel 引擎冒烟：F0 已知种子建局 → 手牌/牌序核对 → 原生 GNRPA 搜索。探针不提交。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
DLL = ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(WHEEL / "GKMSUINet"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")          # 引擎按相对路径读部分表

from GakumasCLI.scenario.exam_session import Master
from GakumasCLI.scenario.hif import build_hif_loadout_session
from gkbench.save import expand_loadout
from gkagent.sim.exam_shuffle import k_before_shuffle, opening_deck_and_rng

PID = sys.argv[1] if len(sys.argv) > 1 else "AS-227HBGHS"
TRANS = int(sys.argv[2]) if len(sys.argv) > 2 else 50000

seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
group = seeds["problems"][PID][0]
seed = int(group["seed"])
check = group["check"]
lo = expand_loadout(saves[PID]["loadout"])
meta_t = saves[PID]["meta"]
print(f"题 {PID} seed={seed} turns={meta_t.get('turns')} check.hand={check['hand']}")

t0 = time.perf_counter()
master = Master.load(Path("ro/master/tables"))
print(f"Master.load: {time.perf_counter() - t0:.2f}s, cards={len(master.cards)}")

t0 = time.perf_counter()
session, meta = build_hif_loadout_session(master, lo, seed)
print(f"build session: {time.perf_counter() - t0:.2f}s  type={type(session).__name__}")
print("meta: limit_turn", meta.get("limit_turn"), "npc", meta.get("npc_count"),
      "permils", meta.get("effective_permils"), "unverified", meta.get("unverified"))

hand = [c["produce_card_id"] for c in session.deck.hand]
deck = [c["produce_card_id"] for c in session.deck.deck]
print("engine hand:", hand)
print("check.hand :", check["hand"], "MATCH" if hand == check["hand"] else "MISMATCH")
print("engine deck order (前10):", deck[:10])

# 我们的洗牌模型对拍
cards = [(c["produce_card_id"], int(c.get("current_upgrade_count") or 0)) for c in lo["deck_cards"]]
npc = int(meta.get("npc_count") or 5)
k = k_before_shuffle(int(meta_t.get("turns") or meta["limit_turn"]), npc)
_rng, shuffled = opening_deck_and_rng(seed, cards, k)
model_deck = [c[0] for c in shuffled]
print("model deck order (前10):", model_deck[:10])
print("deck order MATCH" if model_deck == deck else "deck order MISMATCH")
print("engine rng state:", getattr(session.deck, "rng", None) and session.deck.rng.state)

# 原生核心 + GNRPA
from GakumasCLI.native.diffrun import Native
from GakumasCLI.native.native_search import NativeSearch
strings = json.loads((WHEEL / "GakumasCLI" / "data" / "strings.json").read_text(encoding="utf-8"))
t0 = time.perf_counter()
nat = Native(str(DLL))
print(f"Native load: {time.perf_counter() - t0:.2f}s rules={nat.exam_rules_version}")
t0 = time.perf_counter()
nat.load_master(master, strings)
print(f"load_master: {time.perf_counter() - t0:.2f}s strings={len(nat.strings)}")
ns = NativeSearch(nat)
t0 = time.perf_counter()
path, stats = ns.policy_search(session, transitions=TRANS, seed=182, variant="gnrpa", stabilization=3)
print(f"GNRPA: {time.perf_counter() - t0:.2f}s status={stats['status']} best_score={stats['best_score']} "
      f"expansions={stats['expansions']} rollouts={stats['rollouts']}")
print("path[:12]:", path[:12])
print("unsup:", stats.get("unsup_line"), stats.get("unsup_info"))

# 用 Python 引擎回放路径核对分数
from GakumasCLI.native import portable as P
s2, _ = build_hif_loadout_session(master, lo, seed)
score = None
try:
    for a in path:
        if a[0] == "play":
            s2.play(int(a[1]))
        elif a[0] == "drink":
            s2.use_drink(int(a[1]))
        elif a[0] == "end":
            s2.end_turn()
        elif a[0] == "select":
            s2.select(list(a[1]))
    score = s2.state.score
except Exception as e:
    print("replay error:", type(e).__name__, e)
print("replay final score:", score, "vs search best:", stats["best_score"])
obs = s2.observe()
print("replay observe: turn", obs.get("turn"), "score", obs.get("score"), "finished", obs.get("finished"))
