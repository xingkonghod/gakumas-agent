"""B9 覆盖率统计：catalog 全量 + gkbench hif 505 题模板 83 唯一 id。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.data.p_items_db import (  # noqa: E402
    catalog_coverage,
    get_catalog,
    resolve_produce_item_ids,
)

BENCH = ROOT / "data" / "bench_local" / "gkbench_dl"
OUT = ROOT / "data" / "_b9_coverage.txt"


def load_bench_loadouts() -> list[list[str]]:
    path = BENCH / "hif" / "saves.jsonl"
    rows: list[list[str]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        loadout = ((row.get("problem") or {}).get("archive") or {}).get("loadout") or row.get("loadout") or {}
        ids = loadout.get("produce_item_ids") or []
        if ids:
            rows.append(list(ids))
    return rows


def main() -> int:
    catalog = get_catalog()
    coverage = catalog_coverage(catalog)
    lines = ["== catalog 全量 =="]
    for key, value in coverage.items():
        if key in ("noop_reasons", "implemented_modifier_targets", "implemented_modifier_specs"):
            lines.append(f"  {key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"  {key}: {value}")
    loadouts = load_bench_loadouts()
    unique = sorted({item_id for ids in loadouts for item_id in ids})
    lines.append("")
    lines.append(f"== gkbench hif: {len(loadouts)} 题 loadout / {len(unique)} 唯一 id ==")
    total_specs = 0
    total_impl = 0
    for item_id in unique:
        specs = catalog.specs_for(item_id)
        total_specs += len(specs)
        total_impl += sum(1 for spec in specs if spec.implemented)
    lines.append(f"  spec 总数 {total_specs}，已实现 {total_impl}（B8: 153 / 59）")
    lines.append(f"  已知 id {len(unique)} / 未知 0")
    # 按题聚合覆盖率（30 题 sample 之外的 505 题都算）
    per_question = resolve_produce_item_ids(unique)
    lines.append(f"  合并解析：spec {len(per_question.specs)}, implemented {len(per_question.implemented_specs)}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
