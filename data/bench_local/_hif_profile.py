"""H.I.F 题集落盘画像：字段分布 + 可映射统计（只读，不改数据）。

输出 ``data/bench_local/_hif_profile.json``，供 REPORT_HIF.md 引用。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench as lb

PROBLEMS = ROOT / "data" / "bench_local" / "problems_hif.json"
OUT = ROOT / "data" / "bench_local" / "_hif_profile.json"


def dist(values: list) -> dict[str, int]:
    return {str(key): count for key, count in Counter(values).most_common()}


def pct_dist(values: list) -> dict[str, dict[str, float]]:
    counts = Counter(values)
    total = len(values) or 1
    return {
        str(key): {"count": count, "pct": round(count / total * 100, 2)}
        for key, count in counts.most_common()
    }


def main() -> None:
    rows = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    loadouts = [(row.get("archive") or {}).get("loadout") or {} for row in rows]
    scenes = [row.get("scene") or {} for row in rows]

    deck_entries = [len(loadout.get("deck_cards") or []) for loadout in loadouts]
    deck_total = sum(deck_entries)
    custom = sum(
        1
        for loadout in loadouts
        for entry in loadout.get("deck_cards") or []
        if "/" in str(entry)
    )
    unique_entries = len(
        {str(entry) for loadout in loadouts for entry in loadout.get("deck_cards") or []}
    )

    step_pairs = Counter(
        (loadout.get("step_type"), loadout.get("step_id")) for loadout in loadouts
    )
    step_consistent = 0
    step_consistent_checked = 0
    for step_type, step_id in step_pairs:
        by_type = lb.HIF_STEP_TYPE.get(lb._int_or_none(step_type))
        by_id = lb.HIF_STEP_ID.get(str(step_id or ""))
        if by_type is not None and by_id is not None:
            step_consistent_checked += step_pairs[(step_type, step_id)]
            if by_type == by_id:
                step_consistent += step_pairs[(step_type, step_id)]

    card_rows, card_index, refs = lb.load_card_table()
    mapped = []
    skipped = []
    for raw in rows:
        try:
            mapped.append(lb.build_problem(raw, card_rows, card_index, refs))
        except lb.UnmappableProblem as exc:
            skipped.append({"id": exc.pid, "reason": exc.reason})

    mapped_effects = sum(spec.deck_stats.effect_count for spec in mapped)
    modeled_effects = sum(spec.deck_stats.modeled_effect_count for spec in mapped)
    unmodeled = Counter(
        effect for spec in mapped for effect in spec.deck_stats.unmodeled_types
    )

    profile = {
        "source": "GET https://hiro.matto.top/gkbench/api/sets/hif/problems",
        "path": str(PROBLEMS.relative_to(ROOT)),
        "bytes": PROBLEMS.stat().st_size,
        "count": len(rows),
        "unique_ids": len({row.get("id") for row in rows}),
        "unique_names": len({row.get("name") for row in rows}),
        "core": dict(Counter(bool(row.get("core")) for row in rows)),
        "has_archive": sum(1 for row in rows if row.get("archive")),
        "has_loadout": sum(1 for loadout in loadouts if loadout),
        "has_deck_cards": sum(1 for loadout in loadouts if loadout.get("deck_cards")),
        "deck_entries": {
            "total": deck_total,
            "unique": unique_entries,
            "customized": custom,
            "per_problem_min": min(deck_entries),
            "per_problem_max": max(deck_entries),
            "per_problem_mean": round(sum(deck_entries) / len(deck_entries), 2),
        },
        "scene": {
            "kind": pct_dist([scene.get("kind") for scene in scenes]),
            "round": pct_dist([scene.get("round") for scene in scenes]),
            "stage": pct_dist([scene.get("stage") for scene in scenes]),
            "exam": pct_dist([scene.get("exam") for scene in scenes]),
            "turns": pct_dist([scene.get("turns") for scene in scenes]),
            "plan": pct_dist([scene.get("plan") for scene in scenes]),
            "mechanic": pct_dist([scene.get("mechanic") for scene in scenes]),
        },
        "loadout": {
            "round": pct_dist([loadout.get("round") for loadout in loadouts]),
            "produce_id": pct_dist([loadout.get("produce_id") for loadout in loadouts]),
            "schema": pct_dist([loadout.get("schema") for loadout in loadouts]),
            "step_type": pct_dist([loadout.get("step_type") for loadout in loadouts]),
            "step_id": pct_dist([loadout.get("step_id") for loadout in loadouts]),
            "starting_stamina": pct_dist(
                [loadout.get("starting_stamina") for loadout in loadouts]
            ),
            "max_stamina": pct_dist([loadout.get("max_stamina") for loadout in loadouts]),
            "has_parameters": sum(1 for lo in loadouts if lo.get("parameters")),
            "has_score_bonus_permils": sum(
                1 for lo in loadouts if lo.get("score_bonus_permils")
            ),
            "has_main_item_enchant_ids": sum(
                1 for lo in loadouts if lo.get("main_item_enchant_ids")
            ),
            "has_lesson_start_enchant_ids": sum(
                1 for lo in loadouts if lo.get("lesson_start_enchant_ids")
            ),
            "has_memory_ability_ids": sum(
                1 for lo in loadouts if lo.get("memory_ability_ids")
            ),
            "has_research_card_ids": sum(
                1 for lo in loadouts if lo.get("research_card_ids")
            ),
            "has_drink_ids": sum(1 for lo in loadouts if lo.get("drink_ids")),
        },
        "step_type_step_id": {
            "pairs": {str(pair): count for pair, count in step_pairs.most_common()},
            "consistent": step_consistent,
            "checked": step_consistent_checked,
        },
        "seeds_meta": {
            "per_problem": dist([len(row.get("seeds") or []) for row in rows]),
            "splits": dist(
                [seed.get("split") for row in rows for seed in row.get("seeds") or []]
            ),
        },
        "mapping": {
            "mapped": len(mapped),
            "skipped": len(skipped),
            "skipped_by_reason": dist([row["reason"] for row in skipped]),
            "mapped_plan": dist([spec.plan for spec in mapped]),
            "mapped_stage": dist([spec.stage for spec in mapped]),
            "mapped_kind": dist([spec.kind for spec in mapped]),
            "mapped_uinet_produce": dist([spec.uinet_exam[0] for spec in mapped]),
            "mapped_uinet_step": dist([spec.uinet_exam[1] for spec in mapped]),
            "mapped_core": sum(1 for spec in mapped if spec.core),
            "skipped_ids": [row["id"] for row in skipped],
            "deck_modeling": {
                "effects": mapped_effects,
                "modeled_effects": modeled_effects,
                "modeled_effect_rate": round(modeled_effects / mapped_effects, 4)
                if mapped_effects
                else 0.0,
                "unmodeled_top": dict(unmodeled.most_common(20)),
            },
        },
    }
    OUT.write_text(json.dumps(profile, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"count={profile['count']} core={profile['core']} bytes={profile['bytes']}")
    for key, value in profile["scene"].items():
        print(f"scene.{key}: {value}")
    for key in (
        "round",
        "produce_id",
        "schema",
        "step_type",
        "step_id",
    ):
        print(f"loadout.{key}: {profile['loadout'][key]}")
    print(f"deck: {profile['deck_entries']}")
    print(f"step_type/step_id consistent: {step_consistent}/{step_consistent_checked}")
    print(f"mapped={len(mapped)} skipped={len(skipped)}")
    print(f"skip reasons: {profile['mapping']['skipped_by_reason']}")
    print(f"mapped core: {profile['mapping']['mapped_core']}")
    print(f"modeled effects: {modeled_effects}/{mapped_effects}")
    print(f"JSON: {OUT}")


if __name__ == "__main__":
    main()
