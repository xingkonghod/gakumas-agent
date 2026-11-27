"""H.I.F 题集结构探查（只读本地落盘 JSON）。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

P = Path("data/bench_local/problems_hif.json")
rows = json.loads(P.read_text(encoding="utf-8"))
print("type", type(rows).__name__, "len", len(rows))
r = rows[0]
print("TOP KEYS", sorted(r))
print(json.dumps(r, ensure_ascii=False, indent=1)[:4500])


def dist(name, values):
    c = Counter(values)
    print(f"\n{name} ({len(c)} distinct):")
    for k, v in c.most_common(40):
        print(f"  {str(k):40s} {v}")


dist("scene.kind", [(row.get("scene") or {}).get("kind") for row in rows])
dist("scene.round", [(row.get("scene") or {}).get("round") for row in rows])
dist("scene.stage", [(row.get("scene") or {}).get("stage") for row in rows])
dist("scene.exam", [(row.get("scene") or {}).get("exam") for row in rows])
dist("scene.turns", [(row.get("scene") or {}).get("turns") for row in rows])
dist(
    "loadout.round",
    [((row.get("archive") or {}).get("loadout") or {}).get("round") for row in rows],
)
dist(
    "loadout.produce_id",
    [((row.get("archive") or {}).get("loadout") or {}).get("produce_id") for row in rows],
)
dist(
    "loadout.step_type",
    [((row.get("archive") or {}).get("loadout") or {}).get("step_type") for row in rows],
)
dist("scene.plan", [(row.get("scene") or {}).get("plan") for row in rows])
dist("scene.mechanic", [(row.get("scene") or {}).get("mechanic") for row in rows])
dist("core", [row.get("core") for row in rows])
dist("has archive", [bool(row.get("archive")) for row in rows])
dist("deck_cards count", [len(((row.get("archive") or {}).get("loadout") or {}).get("deck_cards") or []) for row in rows])
dist(
    "loadout keys",
    ["|".join(sorted(((row.get("archive") or {}).get("loadout") or {}).keys())) for row in rows],
)
dist("tags.produce", [(row.get("tags") or {}).get("produce") for row in rows])
