"""P1-5 盘点：no-op 段按 effect_type / trigger / 原因分布（不提交）。"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gkagent.sim import p_items as P  # noqa: E402

records = json.loads(Path("data/knowledge/p_items.json").read_text(encoding="utf-8"))
if isinstance(records, dict):
    records = records.get("items") or records.get("records")
specs: list[P.PItemSpec] = []
for rec in records:
    specs.extend(P.record_to_specs(rec))

impl = [s for s in specs if s.implemented]
noop = [s for s in specs if not s.implemented]
print(f"total specs={len(specs)} implemented={len(impl)} noop={len(noop)}")
print(f"trigger_unknown items={sum(1 for r in records for s in P.record_to_specs(r) if not s.trigger_known)}")

# no-op 原因分解
reasons = Counter()
by_type = defaultdict(list)
for s in noop:
    if not s.trigger_known:
        r = "trigger_unknown"
    elif not s.condition_known:
        r = "condition_unknown"
    elif s.trigger not in P.SUPPORTED_TRIGGERS:
        r = f"unsupported_trigger:{s.trigger}"
    elif s.create_random:
        r = "create_random(RNG)"
    elif not s.target:
        r = f"no_target:{s.effect_type}"
    elif s.value <= 0 and s.target not in P.FLAG_TARGETS:
        r = f"no_value:{s.effect_type}->{s.target}"
    else:
        r = f"other:{s.effect_type}->{s.target}"
    reasons[r] += 1
    by_type[s.effect_type].append(s)

print("\n== no-op 原因 ==")
for r, n in reasons.most_common():
    print(f"{n:5d}  {r}")

print("\n== no-op 按 effect_type（top 40）==")
for t, ss in sorted(by_type.items(), key=lambda kv: -len(kv[1]))[:40]:
    triggers = Counter(s.trigger for s in ss)
    targets = Counter(s.target for s in ss)
    tk = sum(1 for s in ss if not s.trigger_known)
    ck = sum(1 for s in ss if not s.condition_known)
    print(f"{len(ss):4d}  {t}  triggers={dict(triggers)} targets={dict(targets)} trig_unknown={tk} cond_unknown={ck}")

# gkbench loadout 覆盖
try:
    saves = Path("data/bench_local/gkbench_dl/hif/saves.jsonl")
    if saves.exists():
        ids = Counter()
        for line in saves.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            lo = rec.get("loadout") or {}
            for pid in lo.get("produce_item_ids") or []:
                ids[pid] += 1
        spec_by_item = defaultdict(list)
        for s in specs:
            spec_by_item[s.item_id].append(s)
        uniq = set(ids)
        total_seg = sum(len(spec_by_item.get(i, [])) for i in uniq)
        impl_seg = sum(sum(1 for s in spec_by_item.get(i, []) if s.implemented) for i in uniq)
        print(f"\n== gkbench hif loadout: {len(uniq)} 唯一 id / {total_seg} 段 / implemented {impl_seg} ==")
        noop_loadout = Counter()
        for i in uniq:
            for s in spec_by_item.get(i, []):
                if not s.implemented:
                    noop_loadout[(s.effect_type, s.trigger, s.target)] += 1
        for k, n in noop_loadout.most_common(40):
            print(f"{n:4d}  {k}")
except Exception as e:  # noqa: BLE001
    print("loadout probe skipped:", e)
