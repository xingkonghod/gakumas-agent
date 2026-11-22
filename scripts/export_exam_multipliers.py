"""导出 T5「考试属性倍率（审查倍率）」真机/主数据配对夹具。

产物：``tests/fixtures/t5_exam_multipliers.json`` —— 从**本机采集**（不入库）里
解出每场考试的：

- 偶像卡 id（``Produce/Start`` 请求 field 3）、剧本 id（``StepAuditionStart``
  响应 ``UserProduceProgress.produceId``，field 3）、
- 考试开始时的培育三维（``UserProduceProgress.vocal/dance/visual``，field 200/201/202），
- 本场配置（主数据 ``ProduceStepAuditionDifficulty`` → ``ProduceExamBattleConfig``
  → ``ProduceExamBattleScoreConfig``：回合数 / 审查基准 / 分段分数表），
- 用 ``sim.exam_multiplier.calculate_bonus`` 算出的三项属性倍率（千分比）与中间量
  （components / penalties / common）。

用途：``tests/test_exam_multiplier.py`` 用这份夹具把「分段曲线 + 联动惩罚」的
计算结果锁死（主数据 ``data/hiro/...`` 是 gitignore，测试不能现场读它）。

数据源（本机）：
- ``C:\\GakumasLocal\\GakumasUnlock\\out\\traffic.jsonl``：``Produce/Start`` /
  ``StepAuditionStart`` / ``StepAuditionEndExamBattle``；
- 主数据 ``catalog.sqlite``（gakumasu-diff 快照，gitignore；快照 commit 见夹具
  ``source`` 字段）。

主数据缺新偶像卡（如 2026-11-21 的 ``i_card-hkne-3-000``）时该场考试**跳过并记进
``skipped``**，不猜配置（真机生产侧直接用屏幕读到的倍率，不需要主数据）。

用法::

    .venv\\Scripts\\python.exe scripts/export_exam_multipliers.py            # 生成
    .venv\\Scripts\\python.exe scripts/export_exam_multipliers.py --check    # 只校验
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dig_deck import body, parse

from gkagent.data.exam_bonus import (
    ExamBonusResolver,
    ExamConfigUnavailable,
    default_db_path,
)
from gkagent.sim.exam_multiplier import ATTRS

DEFAULT_TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
DEFAULT_OUT = ROOT / "tests" / "fixtures" / "t5_exam_multipliers.json"
FORMAT = "gkagent.exam_multipliers.v1"


def field_map(nodes: list) -> dict:
    """field → 值列表（重复字段收成 list）。"""
    out: dict[int, list] = {}
    for field, _wire, value, *_ in nodes:
        out.setdefault(field, []).append(value)
    return out


def find_progress(nodes: list, depth: int = 0) -> dict | None:
    """递归找 ``UserProduceProgress``：同时有 200/201/202/220（vocal/dance/visual/stamina）。"""
    fields = field_map(nodes)
    if 200 in fields and 201 in fields and 202 in fields and 220 in fields:
        return fields
    if depth > 9:
        return None
    for values in fields.values():
        for value in values:
            if isinstance(value, tuple) and len(value) == 2 and value[1]:
                found = find_progress(value[1], depth + 1)
                if found:
                    return found
    return None


def first_string(nodes: list, field: int) -> str:
    """深度优先找第一个 wire2 字符串字段（例如 produceId / 卡 id）。"""
    for _path, node_field, wire, value in _walk(nodes):
        if node_field != field or wire != 2 or not isinstance(value, tuple):
            continue
        raw = value[0]
        if not raw or value[1]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        return text
    return ""


def _walk(nodes: list, path: tuple = ()):
    for field, wire, value, *_ in nodes:
        yield path + (field,), field, wire, value
        if wire == 2 and isinstance(value, tuple) and len(value) == 2 and value[1]:
            yield from _walk(value[1], path + (field,))


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def exam_turn_count(record: dict) -> int:
    """``StepAuditionEndExamBattle`` 请求里 ``turnEndLogs``（field 3）的条数。"""
    request = body(record, "req_plain_hex")
    if not request:
        return 0
    nodes = parse(request)
    return sum(1 for field, wire, value, *_ in nodes if field == 3 and wire == 2)


def idol_card_id(records: list[dict], before: int) -> str:
    """最近一次 ``Produce/Start`` 请求里的偶像卡 id（field 3）。"""
    for index in range(before, -1, -1):
        record = records[index]
        if not record.get("path", "").endswith("Produce/Start"):
            continue
        request = body(record, "req_plain_hex")
        if not request:
            continue
        return first_string(parse(request), 3)
    return ""


def collect_exams(records: list[dict]) -> list[dict]:
    """配对 ``StepAuditionStart``（三维/剧本）与 ``StepAuditionEndExamBattle``（回合数）。"""
    exams = []
    for index, record in enumerate(records):
        if not record.get("path", "").endswith("StepAuditionEndExamBattle"):
            continue
        start_index = next(
            (
                position
                for position in range(index - 1, -1, -1)
                if records[position].get("path", "").endswith("StepAuditionStart")
            ),
            None,
        )
        if start_index is None:
            continue
        start = records[start_index]
        response = body(start, "resp_plain_hex")
        progress = find_progress(parse(response)) if response else None
        if not progress:
            continue
        exams.append(
            {
                "end_index": index,
                "start_index": start_index,
                "ts": record.get("ts"),
                "played_turns": exam_turn_count(record),
                "produce_id": first_string(parse(response), 3),
                "idol_card_id": idol_card_id(records, start_index),
                "params": {
                    "vocal": int(progress[200][0]),
                    "dance": int(progress[201][0]),
                    "visual": int(progress[202][0]),
                },
                "stamina": int(progress[220][0]),
                "max_stamina": int(progress[221][0]) if 221 in progress else None,
            }
        )
    return exams


def score_table_rows(config) -> list[list[int]]:
    """分数表 → 紧凑 ``[[parameter, vocalPermil, dancePermil, visualPermil], ...]``。"""
    rows = []
    for row in config.score_table:
        rows.append(
            [
                int(row["parameter"]),
                int(row["vocalPermil"]),
                int(row["dancePermil"]),
                int(row["visualPermil"]),
            ]
        )
    return rows


def build(traffic: Path, db_path: Path | None) -> dict:
    resolver = ExamBonusResolver(db_path)
    if not resolver.available:
        raise SystemExit(f"❌ 主数据不可用：{resolver.db_path}")
    records = load_records(traffic)
    exams = collect_exams(records)
    out_exams = []
    skipped = []
    for index, exam in enumerate(exams):
        if not exam["idol_card_id"] or not exam["produce_id"]:
            skipped.append(
                {"index": index, "ts": exam["ts"], "reason": "缺偶像卡/剧本 id（采集头部被截断）"}
            )
            continue
        matched = None
        attempts = []
        for step in ("mid", "final"):
            try:
                config = resolver.battle_config(
                    idol_card_id=exam["idol_card_id"],
                    produce_id=exam["produce_id"],
                    step_type=step,
                )
            except ExamConfigUnavailable as exc:
                attempts.append(f"{step}: {exc}")
                continue
            if config.turn == exam["played_turns"]:
                matched = (step, config)
                break
            attempts.append(
                f"{step}: 配置回合 {config.turn} != 实战 {exam['played_turns']}"
            )
        if matched is None:
            skipped.append(
                {
                    "index": index,
                    "ts": exam["ts"],
                    "idol_card_id": exam["idol_card_id"],
                    "produce_id": exam["produce_id"],
                    "reason": "；".join(attempts) or "没有匹配的考试配置",
                }
            )
            continue
        step, config = matched
        bonus = config.bonus(exam["params"])
        out_exams.append(
            {
                "index": index,
                "ts": exam["ts"],
                "idol_card_id": exam["idol_card_id"],
                "produce_id": exam["produce_id"],
                "step_type": step,
                "played_turns": exam["played_turns"],
                "params": exam["params"],
                "start_stamina": exam["stamina"],
                "start_max_stamina": exam["max_stamina"],
                "config": {
                    "id": config.id,
                    "turn": config.turn,
                    "criteria": dict(config.criteria),
                    "penalty_min_permil": config.penalty_min_permil,
                    "penalty_max_permil": config.penalty_max_permil,
                    # 紧凑分数表：[[parameter, vocalPermil, dancePermil, visualPermil], ...]
                    "score_table": score_table_rows(config),
                },
                "expected": {
                    "permil": dict(bonus.permil),
                    "components": dict(bonus.components),
                    "penalties": dict(bonus.penalties),
                    "common_permil": int(bonus.common_permil),
                },
            }
        )
    return {
        "format": FORMAT,
        "source": {
            "traffic": str(traffic),
            "master_db": str(resolver.db_path),
            "generated_by": "scripts/export_exam_multipliers.py",
            "note": (
                "主数据表：ProduceStepAuditionDifficulty → ProduceExamBattleConfig → "
                "ProduceExamBattleScoreConfig，惩罚上下限来自 Setting；"
                "分段折线 + 联动惩罚公式见 src/gkagent/sim/exam_multiplier.py。"
                "采集/主数据都在仓库外或 gitignore，本夹具只是计算结果的回归快照。"
            ),
        },
        "attribute_order": list(ATTRS),
        "exams": out_exams,
        "skipped": skipped,
    }


def summarize(doc: dict) -> str:
    lines = [
        f"考试 {len(doc['exams'])} 场可解析 / 跳过 {len(doc['skipped'])} 场",
    ]
    for exam in doc["exams"]:
        permil = exam["expected"]["permil"]
        lines.append(
            f"  #{exam['index']} {exam['step_type']:5s} {exam['config']['id']} "
            f"turn={exam['config']['turn']} 参数={exam['params']} "
            f"倍率 Vo/Da/Vi = {permil['vocal']}/{permil['dance']}/{permil['visual']}‰ "
            f"(common={exam['expected']['common_permil']})"
        )
    for item in doc["skipped"]:
        lines.append(f"  ⏭ #{item['index']} {item['ts']}: {item['reason']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traffic", default=str(DEFAULT_TRAFFIC))
    parser.add_argument("--master-db", default=None, help="主数据 catalog.sqlite（默认 current.json）")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check", action="store_true", help="只校验现有夹具是否与重算一致")
    args = parser.parse_args(argv)

    db_path = Path(args.master_db) if args.master_db else default_db_path()
    doc = build(Path(args.traffic), db_path)
    print(summarize(doc))
    out = Path(args.out)
    payload = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if args.check:
        existing = out.read_text(encoding="utf-8") if out.exists() else ""
        if existing.strip() != payload.strip():
            print(f"❌ {out} 与重算结果不一致（重新运行不带 --check 以更新）")
            return 1
        print(f"✅ {out} 与重算结果一致")
        return 0
    out.write_text(payload, encoding="utf-8")
    print(f"✅ 已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
