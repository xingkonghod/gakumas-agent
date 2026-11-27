"""B9 预分析：按 gkbench hif loadout 权重 + catalog 挑持续倍率/modifier 类效果。

只读本地数据，输出 UTF-8 报告（data/_b9_analysis.txt）。
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.p_items import record_to_specs, summarize  # noqa: E402

BENCH = ROOT / "data" / "bench_local" / "gkbench_dl"
OUT = ROOT / "data" / "_b9_analysis.txt"


def load_items():
    payload = json.loads(
        (ROOT / "data" / "knowledge" / "p_items.json").read_text(encoding="utf-8-sig")
    )
    items = {row["id"]: row for row in payload["items"]}
    return payload, items


def load_bench_loadouts():
    """hif 题模板 loadout.produce_item_ids（去重后的题 loadout）。"""
    path = BENCH / "hif" / "saves.jsonl"
    rows = []
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
        loadout = ((row.get("problem") or {}).get("archive") or {}).get("loadout") or row.get(
            "loadout"
        ) or {}
        ids = loadout.get("produce_item_ids") or []
        if ids:
            rows.append(ids)
    return rows


def main() -> int:
    payload, items = load_items()
    lines: list[str] = []
    add = lines.append

    specs_by_type = collections.Counter()
    value_by_type = collections.Counter()
    items_by_type = collections.Counter()
    for item in payload["items"]:
        for eff in item.get("effects") or []:
            t = eff.get("type")
            specs_by_type[t] += 1
            v = (eff.get("values") or {}).get("value1") or 0
            value_by_type[t] += int(v)
            items_by_type[t] += 1

    add("== catalog 全量 effect type（specs / items / Σvalue1）==")
    for t, n in specs_by_type.most_common():
        add(f"{n:5d} specs {items_by_type[t]:5d} items {t:45s} sum(value1)={value_by_type[t]}")
    add("")

    # 当前实现状态
    all_specs = []
    for item in payload["items"]:
        all_specs.extend(record_to_specs(item))
    stats = summarize(all_specs)
    add(f"== 当前实现状态 specs={stats['specs']} implemented={stats['implemented']} noop={stats['noop']}")
    add(f"implemented_effect_types={stats['implemented_effect_types']}")
    add(f"noop_effect_types={stats['noop_effect_types']}")
    add("")

    # gkbench loadout 权重
    loadouts = load_bench_loadouts()
    add(f"== gkbench hif 带 produce_item_ids 的题 loadout 数：{len(loadouts)}")
    id_freq = collections.Counter()
    for ids in loadouts:
        for i in set(ids):
            id_freq[i] += 1
    add(f"唯一 P 道具 id：{len(id_freq)}")
    add("")
    add("== 按题频次排序的 id（题数, 稀有度, 名称, trigger, 效果）==")
    unknown = []
    for item_id, freq in id_freq.most_common():
        item = items.get(item_id)
        if item is None:
            unknown.append(item_id)
            continue
        eff_desc = []
        for eff in item.get("effects") or []:
            vals = eff.get("values") or {}
            eff_desc.append(f"{eff.get('type')}:{vals}")
        add(
            f"{freq:4d}  {item_id:28s} {item.get('rarity','?'):4s} {item.get('name','?')[:22]:22s} "
            f"trigger={item.get('trigger','?'):22s} cond={item.get('condition','')!r} "
            f"effects={'; '.join(eff_desc)}"
        )
    add(f"未知 id: {unknown}")
    add("")

    # 按 loadout 加权统计：每个 effect type 在多少题 loadout 里出现、目前是否 implemented
    add("== effect type 按题权重（题频次 * spec）==")
    type_weight = collections.Counter()
    type_questions = collections.Counter()
    type_impl_weight = collections.Counter()
    for ids in loadouts:
        seen_types = set()
        for item_id in set(ids):
            item = items.get(item_id)
            if item is None:
                continue
            for eff in item.get("effects") or []:
                t = eff.get("type")
                type_weight[t] += 1
                seen_types.add(t)
        for t in seen_types:
            type_questions[t] += 1
    # 当前 implemented 判定
    for item_id, item in items.items():
        for spec in record_to_specs(item):
            if spec.implemented and spec.item_id in id_freq:
                type_impl_weight[spec.effect_type] += id_freq[spec.item_id]
    for t, w in type_weight.most_common(60):
        add(
            f"{w:5d} specs  {type_questions[t]:4d} 题  impl_weight={type_impl_weight[t]:5d}  {t}"
        )
    add("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {OUT} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
