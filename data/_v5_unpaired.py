"""Probe (not committed): the 8 unpaired slots (no best-known oracle) — what happened there?"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
res = json.loads((ROOT / "out/_v5_lockscan.json").read_text(encoding="utf-8"))
oracle = json.loads((ROOT / "data/_v3_slots.json").read_text(encoding="utf-8"))["oracle"]
meta = {x["id"]: x for x in json.loads((ROOT / "data/_meta_probe.json").read_text(encoding="utf-8"))}
pids = ["AS-N7X62HPS", "AS-R8ES22AB", "AS-VCCRY333", "AS-ZHAN6GNN"]
for pid in pids:
    m = meta.get(pid) or {}
    print(f"\n{pid}: step_type={m.get('step_type')} limit={m.get('limit_turn')} produce={m.get('produce_id')}")
    for k, v in sorted(res.items()):
        if v["pid"] == pid:
            print(f"  slot{v['slot']}: score={v['score']:,} lock={v['lock_turn']} modes={v['modes']} "
                  f"secs={v['secs']} over={v['over']}")
# score distribution of all problems with produce-008
p8 = [(v["pid"], v["score"]) for v in res.values()
      if (meta.get(v["pid"]) or {}).get("produce_id") == "produce-008"]
print(f"\nproduce-008 problems in our 240 slots: {len({p for p, _ in p8})} problems, "
      f"{len(p8)} slots, mean={sum(s for _, s in p8)/max(1,len(p8)):,.0f}")
others = [(v["pid"], v["score"]) for v in res.values()
          if (meta.get(v["pid"]) or {}).get("produce_id") != "produce-008"]
print(f"other produce: {len(others)} slots mean={sum(s for _, s in others)/max(1,len(others)):,.0f}")