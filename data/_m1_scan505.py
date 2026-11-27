"""M1 静态扫 505 题 loadout（不提交）：消费图 opt-in 后多少机制题恢复全知合格。
不跑 sim，只静态扫牌组效果。用法：.venv\\Scripts\\python.exe data\\_m1_scan505.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.sim.exam_risk import deck_rng_risks, load_extra_rng_index  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

index = load_extra_rng_index()
saves = [json.loads(l) for l in open(ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl", encoding="utf-8")]
n = len(saves)
mech_old = 0      # 旧口径风险题（含额外 RNG 机制卡）
mech_new = 0      # 图口径仍风险题
recovered = 0     # 旧风险 → 图合格
still_risky = []
recovered_ids = []
effect_hist_old = {}
effect_hist_new = {}
for r in saves:
    pid = str(r.get("id"))
    lo = expand_loadout(r["loadout"])
    deck = [(c["produce_card_id"], int(c.get("current_upgrade_count") or 0)) for c in lo["deck_cards"]]
    old = deck_rng_risks(deck, index=index)
    new = deck_rng_risks(deck, index=index, use_graph=True)
    if old:
        mech_old += 1
        for risk in old:
            for e in risk["effects"]:
                effect_hist_old[e] = effect_hist_old.get(e, 0) + 1
    if new:
        mech_new += 1
        for risk in new:
            for e in risk["effects"]:
                effect_hist_new[e] = effect_hist_new.get(e, 0) + 1
        still_risky.append((pid, [risk["card_id"] for risk in new]))
    if old and not new:
        recovered += 1
        recovered_ids.append(pid)

print(f"总题数: {n}")
print(f"旧口径机制风险题（全知停用）: {mech_old}")
print(f"图口径仍风险题: {mech_new}")
print(f"恢复全知合格（旧风险→图合格）: {recovered}")
print(f"恢复率: {recovered}/{mech_old} = {recovered/mech_old*100:.1f}%")
print(f"旧口径风险效果分布: {dict(sorted(effect_hist_old.items(), key=lambda x:-x[1]))}")
print(f"图口径仍风险效果分布: {dict(sorted(effect_hist_new.items(), key=lambda x:-x[1]))}")
print(f"仍风险题样例（前10）: {still_risky[:10]}")
out = {"total": n, "mech_old": mech_old, "mech_new": mech_new, "recovered": recovered,
       "effect_hist_old": effect_hist_old, "effect_hist_new": effect_hist_new,
       "still_risky": still_risky, "recovered_ids": recovered_ids}
(ROOT / "data/_m1_scan505_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved data/_m1_scan505_result.json")
