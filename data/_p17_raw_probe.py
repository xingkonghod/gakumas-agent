"""P1-7 探针：raw masterTrans 描述分段（找 delay 字段）+ yaml 结构（不提交）。"""
import json
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_p_items as bpi

out = io.open("data/_p17_raw_out.txt", "w", encoding="utf-8")
local = bpi.load_master("ProduceItem.json")
yaml_items = bpi.parse_yaml_items(bpi.YAML)

WANT = [
    "pitem_02-3-130-0", "pitem_02-3-130-1",
    "pitem_02-1-023-0", "pitem_02-1-023-1",
    "pitem_01-3-161-0", "pitem_01-3-161-1",
    "pitem_01-3-044-0", "pitem_01-3-044-1",
    "pitem_02-0-002-0-002",
    "pitem_02-2-066-challenge", "pitem_02-2-067-challenge",
    "pitem_03-0-007-0-012", "pitem_03-0-007-0-014",
    "pitem_01-3-245-challenge",
    "pitem_01-3-294-0",
    "pitem_01-2-049-challenge",
]
by_id = {row["id"]: row for row in local}
for iid in WANT:
    row = by_id.get(iid)
    out.write(f"\n===== {iid} =====\n")
    if row is None:
        out.write("  (not in local master)\n")
    else:
        out.write(f"name: {row.get('name')}\n")
        for k, v in row.items():
            if k not in ("produceDescriptions", "name", "id"):
                out.write(f"  {k}: {v}\n")
        for d in row.get("produceDescriptions", []):
            out.write("  DESC " + json.dumps(d, ensure_ascii=False) + "\n")
    y = yaml_items.get(iid)
    if y:
        out.write("  YAML keys: " + ", ".join(k for k in y.keys()) + "\n")
        for k, v in y.items():
            if k != "descriptions":
                out.write(f"  yaml.{k}: {v}\n")
        for d in y.get("descriptions", []):
            out.write("  YDESC " + json.dumps(d, ensure_ascii=False) + "\n")
out.close()
print("written data/_p17_raw_out.txt")
