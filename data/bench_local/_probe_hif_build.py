"""H.I.F 题集 -> LessonSim 静态构建探针（只读，不改仓库数据）。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench as lb  # noqa: E402

rows = json.loads(Path("data/bench_local/problems_hif.json").read_text(encoding="utf-8"))
card_rows, card_index, refs = lb.load_card_table()
print("card table", len(card_rows), "index", len(card_index))

ok = 0
fail: list[tuple[str, str]] = []
unresolved_entries = 0
customized = 0
entries = 0
unmodeled = Counter()
effect_count = 0
modeled = 0
plans = Counter()
for raw in rows:
    lo = (raw.get("archive") or {}).get("loadout") or {}
    plans[(raw["scene"].get("plan"), lo.get("produce_id"))] += 1
    for entry in lo.get("deck_cards") or []:
        entries += 1
        parsed = lb.parse_deck_entry(str(entry))
        if parsed is None:
            unresolved_entries += 1
            continue
        cid, up, cust = parsed
        if cust:
            customized += 1
        name = card_index.get((cid, up))
        if name is None:
            unresolved_entries += 1
            print("UNRESOLVED", raw["id"], entry, "cid/up", cid, up)
            continue
        row = card_rows[name]
        for effect in row.get("effects") or []:
            effect_count += 1
            if effect["type"] in lb.sp.MODELED_EFFECTS:
                modeled += 1
            else:
                unmodeled[effect["type"]] += 1
    try:
        spec = lb.build_problem(raw, card_rows, card_index, refs)
    except SystemExit as exc:
        fail.append((raw["id"], str(exc)))
        continue
    ok += 1

print("built", ok, "of", len(rows), "fail", len(fail))
print("entries", entries, "unresolved", unresolved_entries, "customized", customized)
print("effects", effect_count, "modeled", modeled, "rate", round(modeled / effect_count, 4))
print("unmodeled", unmodeled.most_common(20))
print("plans", dict(plans))
for pid, msg in fail[:10]:
    print("FAIL", pid, msg)
