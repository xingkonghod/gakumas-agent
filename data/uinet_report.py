"""生成 UINet 接入报告用的实测数据（不参与 pytest）。"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from gkagent.data.card_table import CardTable
from gkagent.policy.lesson import LessonPolicy
from gkagent.sim import uinet
from gkagent.sim.uiobs import to_uiobs
from gkagent.vision.lesson import LessonCard, LessonState

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "uinet_report.json"


def _pick_cards(table: CardTable):
    rows = []
    for name, row in table._cards.items():
        if row.get("upgrade") != 0 or not row.get("id"):
            continue
        cost = row.get("cost")
        if not isinstance(cost, int) or not 2 <= cost <= 6:
            continue
        score = 0
        for effect in row.get("effects") or []:
            if effect.get("type") == "ExamLesson":
                values = [v for v in effect.get("values") or [] if v]
                if values:
                    score = int(values[0])
                    break
        if score >= 6:
            rows.append((name, row, score))
    rows.sort(key=lambda item: (-item[2], item[0]))
    return rows[:3]


def main() -> None:
    table = CardTable()
    picked = _pick_cards(table)
    cards = tuple(
        LessonCard(
            index=index,
            box=(0, 0, 1, 1),
            point=(120 + index * 150, 900),
            name=name,
            score=score,
            cost=int(row["cost"]),
        )
        for index, (name, row, score) in enumerate(picked)
    )
    state = LessonState(
        kind="lesson",
        turns_left=4,
        total_turns=7,
        score=123,
        gauge=250,
        stamina=24,
        cards=cards,
    )
    obs = to_uiobs(state, table=table, plan="sense", plays=0)

    rules = LessonPolicy(params_path=ROOT / "data" / "knowledge" / "policy.json", engine="rules")
    rules._table = table
    net = LessonPolicy(params_path=ROOT / "data" / "knowledge" / "policy.json", engine="uinet")
    net._table = table

    # 冷启动：新进程第一次 predict（主数据 pickle + ONNX 会话 + 一次推理）
    started = time.perf_counter()
    first = uinet.predict(obs)
    cold_ms = (time.perf_counter() - started) * 1000.0

    samples = []
    outputs = []
    for _ in range(20):
        started = time.perf_counter()
        outputs.append(uinet.predict(obs))
        samples.append((time.perf_counter() - started) * 1000.0)
    assert all(item.action == first.action for item in outputs)

    rule_action = rules.decide(state)
    net_action = net.decide(state)

    report = {
        "model_bytes": uinet.model_path().stat().st_size,
        "model_path": str(uinet.model_path()),
        "master_tables": 9,
        "cold_first_predict_ms": round(cold_ms, 1),
        "warm_ms": {
            "median": round(statistics.median(samples), 1),
            "mean": round(statistics.mean(samples), 1),
            "min": round(min(samples), 1),
            "max": round(max(samples), 1),
            "p90": round(sorted(samples)[17], 1),
        },
        "uinet_top": {
            "action": list(first.action),
            "probs": [round(value, 4) for value in first.probs],
            "score_quantiles": first.score_quantiles,
        },
        "obs_sample_head": json.dumps(obs, ensure_ascii=False)[:200],
        "obs": obs,
        "hand": [
            {
                "index": card.index,
                "name": card.name,
                "score": card.score,
                "cost": card.cost,
            }
            for card in cards
        ],
        "rules": {
            "kind": rule_action.kind,
            "index": rule_action.index,
            "reason": rule_action.reason,
        },
        "uinet": {
            "kind": net_action.kind,
            "index": net_action.index,
            "reason": net_action.reason,
        },
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "obs"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
