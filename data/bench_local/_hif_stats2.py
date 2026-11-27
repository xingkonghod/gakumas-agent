"""H.I.F 题集结构探查 2：round / stage / produce / step_type 交叉，以及编成字段。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

rows = json.loads(Path("data/bench_local/problems_hif.json").read_text(encoding="utf-8"))


def lo(row):
    return (row.get("archive") or {}).get("loadout") or {}


combos = Counter(
    (
        row["scene"].get("kind"),
        row["scene"].get("round"),
        row["scene"].get("stage"),
        row["scene"].get("exam"),
        row["scene"].get("turns"),
        lo(row).get("step_type"),
        lo(row).get("step_number"),
        lo(row).get("step_id"),
        lo(row).get("audition_number"),
    )
    for row in rows
)
print("=== (kind, round, stage, exam, turns, step_type, step_number, step_id, audition_number) ===")
for k, v in sorted(combos.items(), key=lambda kv: (str(kv[0][2]), kv[0][1] or "")):
    print(f"{v:4d}  {k}")

print("\n=== scene.plan x mechanic x stage ===")
pc = Counter((row["scene"].get("plan"), row["scene"].get("mechanic"), row["scene"].get("stage")) for row in rows)
for k, v in sorted(pc.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][2]))):
    print(f"{v:4d}  {k}")

print("\n=== step_type x round ===")
st = Counter((lo(row).get("step_type"), lo(row).get("round")) for row in rows)
for k, v in sorted(st.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
    print(f"{v:4d}  {k}")

print("\n=== selection subset sample ids/stages ===")
sel = [r for r in rows if r["scene"]["kind"] == "selection"]
print("selection count", len(sel))
for r in sel[:3]:
    print(r["id"], r["scene"]["stage"], r["scene"]["round"], r["scene"]["turns"], lo(r).get("step_type"))
main = [r for r in rows if r["scene"]["kind"] == "main"]
print("main count", len(main))
for r in main[:3]:
    print(r["id"], r["scene"]["stage"], r["scene"]["round"], r["scene"]["turns"], lo(r).get("step_type"))

print("\n=== seeds info ===")
seed_counts = Counter(len(r.get("seeds") or []) for r in rows)
print("seeds per problem:", dict(seed_counts))
print("splits:", dict(Counter(s.get("split") for r in rows for s in (r.get("seeds") or []))))

print("\n=== deck card entry patterns ===")
entries = [e for r in rows for e in lo(r).get("deck_cards") or []]
print("total entries", len(entries), "unique", len(set(entries)))
print("with customization", sum(1 for e in entries if "/" in e))
print("with *", sum(1 for e in entries if "*" in e))
print("sample customized:", [e for e in entries if "/" in e][:3])
print("sample plain:", [e for e in entries if "/" not in e][:3])

print("\n=== other loadout presence ===")
for key in (
    "main_item_enchant_ids",
    "lesson_start_enchant_ids",
    "memory_ability_ids",
    "research_card_ids",
    "produce_item_ids",
    "drink_ids",
    "support_cards",
):
    vals = [lo(r).get(key) for r in rows]
    print(f"{key}: present={sum(1 for v in vals if v is not None)} nonempty={sum(1 for v in vals if v)} sample={next((v for v in vals if v), None)}")

print("\n=== scene.plan PLAN1 sample ===")
for r in [r for r in rows if r["scene"].get("plan") == "PLAN1"][:5]:
    print(r["id"], r["scene"]["stage"], r["scene"]["mechanic"], lo(r).get("produce_id"), lo(r).get("idol_card_id"))

print("\n=== turn vs stage ===")
tv = Counter((r["scene"]["stage"], r["scene"]["turns"]) for r in rows)
print(dict(tv))

print("\n=== id duplicates ===")
print("unique ids", len({r["id"] for r in rows}), "of", len(rows))
print("names", len({r["name"] for r in rows}))

# family/core
print("\nfamilies", len({r.get("family") for r in rows}), "core", dict(Counter(r.get("core") for r in rows)))
