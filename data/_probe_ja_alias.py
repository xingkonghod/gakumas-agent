"""一次性探针⑧：ja_aliases 是否覆盖 柔らかな光の中で；CardMeta vs CardTable 解析差异；
期末牌里哪些卡 OCR 日文名会落空。不提交。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
from gkagent.data.card_meta import CardMetaIndex  # noqa: E402
from gkagent.data.card_table import CardTable  # noqa: E402


def main() -> int:
    meta = CardMetaIndex()
    ct = CardTable()
    raw = json.loads((ROOT / "data/knowledge/card_meta.json").read_text(encoding="utf-8"))
    ja = raw.get("ja_aliases") or {}
    print(f"ja_aliases 共 {len(ja)} 条")
    for k, v in ja.items():
        if "柔和" in k or "温柔" in k or "光" in k:
            print(f"  alias: {k!r} -> {v!r}")

    print("\n== 关键卡解析对比 ==")
    for name in ("柔らかな光の中で", "柔らかな光の中で+", "温柔的光之中", "温柔的光之中+",
                 "演出计划", "平衡感", "演出計画"):
        m = meta.meta(name)
        c = ct.get(name)
        print(f"  {name!r}: CardMeta={'HIT ' + m.card_id if m else 'None'} | CardTable={'HIT ' + c['id'] if c else 'None'}")

    # 期末牌日文名（主数据 name）vs 中文
    print("\n== 期末 23 张：中文卡名 / 日文主数据名 / CardTable.get(日文) ==")
    ids = ["p_card-01-ido-3_292", "p_card-01-men-2_034", "p_card-01-men-1_024",
           "p_card-01-men-2_038", "p_card-01-men-2_035", "p_card-00-men-3_011",
           "p_card-00-men-3_012", "p_card-01-act-3_030", "p_card-00-men-1_007"]
    # 从 ProduceCard.yaml 读日文 name
    yaml_names = {}
    yp = ROOT / "data/cache/ProduceCard.yaml"
    cur = None
    for line in yp.open(encoding="utf-8", errors="replace"):
        if line.startswith("- id: "):
            cur = line[6:].strip()
        elif line.startswith("  name: ") and cur:
            yaml_names.setdefault(cur, line[8:].strip())
    for cid in ids:
        cn = ct.name_of(cid, 0)
        jn = yaml_names.get(cid)
        hit = ct.get(jn) if jn else None
        print(f"  {cid}: 中文={cn!r} 日文={jn!r} CardTable.get(日文)={'HIT' if hit else 'MISS'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())