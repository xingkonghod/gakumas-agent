"""B9 预分析 3：目标记录的 values/trigger_params/max_uses/中文描述 细查。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "_b9_records.txt"

IDS = [
    "pitem_00-3-012-0",  # 悔しさの象徴 score buff 50% turn? 
    "pitem_00-0-004-0-002",
    "pitem_00-0-004-0-007",
    "pitem_02-3-062-0",
    "pitem_03-3-337-0",
    "pitem_3-258-research-event-010",
    "pitem_02-0-002-0-018",
    "pitem_02-0-002-0-023",
    "pitem_02-0-002-0-024",
    "pitem_01-3-079-0",
    "pitem_02-3-074-0",
    "pitem_02-3-321-0",
    "pitem_01-3-349-0",
    "pitem_03-3-345-0",
    "pitem_01-0-001-0-002",
    "pitem_01-1-020-0",
    "pitem_01-3-157-1",
    "pitem_03-0-007-0-001",
    "pitem_00-2-100-challenge-exam_concentration",
    "pitem_03-3-159-0",
    "pitem_03-0-003-0-017",
    "pitem_01-0-001-0-018",
    "pitem_01-0-001-0-011",
    "pitem_02-0-002-0-009",
    "pitem_02-3-167-0",
    "pitem_03-0-007-0-007",
    "pitem_01-0-005-0-014",
    "pitem_00-2-116-0",
    "pitem_02-3-043-0",
    "pitem_00-0-004-0-003",
    "pitem_00-0-004-0-013",
    "pitem_02-3-130-0",
    "pitem_03-3-132-0",
    "pitem_03-1-069-0",
]


def main() -> int:
    payload = json.loads(
        (ROOT / "data" / "knowledge" / "p_items.json").read_text(encoding="utf-8-sig")
    )
    by_id = {row["id"]: row for row in payload["items"]}
    lines: list[str] = []
    for item_id in IDS:
        row = by_id.get(item_id)
        if row is None:
            lines.append(f"### {item_id} NOT FOUND")
            continue
        lines.append(f"### {item_id}  name={row.get('name')} rarity={row.get('rarity')}")
        lines.append(
            f"  trigger={row.get('trigger')} family={row.get('trigger_family')} "
            f"params={json.dumps(row.get('trigger_params'), ensure_ascii=False)} "
            f"condition={row.get('condition')!r} condition_known={row.get('condition_known', True)} "
            f"trigger_known={row.get('trigger_known', True)}"
        )
        lines.append(f"  zh={row.get('text_zh', '')!r}")
        lines.append(f"  ja={row.get('text_ja', '')!r}")
        lines.append(f"  max_uses={row.get('max_uses')}  value={row.get('value')} unit={row.get('value_unit')}")
        lines.append(f"  effects={json.dumps(row.get('effects'), ensure_ascii=False)}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
