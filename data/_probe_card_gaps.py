"""一次性探针⑦：诊断 ep-t31 期末 23 张牌在 card_table / produce_cards master / ProduceCard.yaml
三层各缺哪些；定位 v3.6.1 新卡。不提交。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\Games\gakumas-agent")

DECK = [
    ("p_card-01-ido-3_292", 1), ("p_card-00-act-0_001", 1), ("p_card-00-act-0_001", 0),
    ("p_card-00-act-0_002", 0), ("p_card-00-men-0_003", 0), ("p_card-00-men-0_003", 0),
    ("p_card-01-men-0_008", 0), ("p_card-01-men-0_008", 0), ("p_card-01-act-0_006", 0),
    ("p_card-01-act-1_020", 0), ("p_card-01-men-2_043", 0), ("p_card-01-act-1_023", 0),
    ("p_card-01-act-1_020", 0), ("p_card-01-men-2_039", 0), ("p_card-01-act-3_030", 0),
    ("p_card-01-men-1_024", 0), ("p_card-00-men-3_012", 0), ("p_card-01-men-2_039", 1),
    ("p_card-01-men-2_038", 0), ("p_card-01-men-2_034", 0), ("p_card-00-men-1_007", 0),
    ("p_card-01-men-2_035", 0), ("p_card-00-men-3_011", 0),
]


def main() -> int:
    ct = json.loads((ROOT / "data/knowledge/card_table.json").read_text(encoding="utf-8"))
    cards = ct["cards"]
    by_key = {}
    for name, row in cards.items():
        by_key.setdefault((row["id"], int(row.get("upgrade") or 0)), name)
    print(f"card_table.json: {ct['count']} 条（按名），唯一 (id,upgrade) {len(by_key)}")

    master = json.loads((ROOT / "data/master/produce_cards.json").read_text(encoding="utf-8"))
    mkeys = {(r["id"], int(r.get("upgrade") or 0)): r.get("name") for r in master}
    mids = {r["id"] for r in master}
    print(f"produce_cards.json master: {len(master)} 行 / {len(mids)} id")

    yaml_path = ROOT / "data/cache/ProduceCard.yaml"
    print(f"ProduceCard.yaml: {yaml_path.stat().st_size if yaml_path.exists() else 'MISSING'}")
    yaml_ids = set()
    if yaml_path.exists():
        for line in yaml_path.open(encoding="utf-8", errors="replace"):
            if line.startswith("- id: "):
                yaml_ids.add(line[6:].strip())
    print(f"  YAML id 数: {len(yaml_ids)}")

    print("\n== 期末 23 张牌三层诊断 ==")
    seen = set()
    for cid, up in DECK:
        if (cid, up) in seen:
            continue
        seen.add((cid, up))
        in_ct = by_key.get((cid, up))
        in_m = mkeys.get((cid, up))
        in_y = cid in yaml_ids
        flag = "OK" if in_ct else "MISSING"
        print(f"  [{flag}] {cid}+{up}: card_table={in_ct!r} master名={in_m!r} yaml_id={in_y}")

    # 也查 base id（不限强化）在 master 的存在性
    print("\n== 缺卡 base id 在 master 任意强化 ==")
    for cid in ("p_card-01-men-2_034", "p_card-01-men-1_024", "p_card-01-ido-3_292",
                "p_card-01-men-2_038", "p_card-01-men-2_035", "p_card-00-men-3_011", "p_card-00-men-3_012"):
        rows = [(k[1], v) for k, v in mkeys.items() if k[0] == cid]
        print(f"  {cid}: master={sorted(rows)} yaml={cid in yaml_ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())