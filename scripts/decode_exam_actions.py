"""解码 StepAuditionEndExamBattle 请求里的实战出牌序列（ground truth）。

结构（dump.cs）：
  Request: result=2(ExamBattleResult), turnEndLogs=3, deviceProduceUuid=4, npcResults=5
  ExamBattleResult: rank=1, score=2, stamina=3, vocalScore=8, danceScore=9, visualScore=10,
                    examActions=100(repeated ExamContestCommand)
  ExamContestCommand: commandType=1, phaseType=2, examActions=10(repeated ExamCommandLog),
                    useProduceCard=20(ProduceCard), useProduceDrinkId=21
  ExamCommandLog: commandType=1, phaseType=2, selectIndexes=3, useIndex=4,
                    useProduceCard=5(ProduceCard), useProduceDrinkId=6
  ProduceCard: id=1, upgradeCount=2, customizes=3, freeCustomizes=4, skin=100

用法：python scripts/decode_exam_actions.py [--file PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from dig_deck import body, parse

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")


def fmap(nodes: list) -> dict:
    """field -> value（重复字段收集成列表）。"""
    out: dict = {}
    for field, wire, value, _ in nodes:
        if field in out:
            if not isinstance(out[field], list):
                out[field] = [out[field]]
            out[field].append(value)
        else:
            out[field] = value
    return out


def as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def msg_inner(v):
    """wire2 的 value=(raw, inner)；返回 inner 解析后的 nodes 或 None。"""
    if isinstance(v, tuple) and len(v) == 2:
        return v[1]
    return None


def decode_produce_card(v) -> str:
    inner = msg_inner(v)
    if inner is None:
        return "?"
    m = fmap(inner)
    cid = m.get(1)
    if isinstance(cid, tuple):
        cid = cid[0].decode("utf-8", "replace")
    up = m.get(2, 0)
    return f"{cid}+{up}"


def decode_action(cmd_nodes: list) -> dict:
    m = fmap(cmd_nodes)
    info = {
        "commandType": m.get(1),
        "phaseType": m.get(2),
    }
    if 20 in m:
        info["card"] = decode_produce_card(m[20])
    if 21 in m:
        raw = m[21][0] if isinstance(m[21], tuple) else m[21]
        info["drink"] = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    # 嵌套 ExamCommandLog（field 10）
    sub = []
    for log in as_list(m.get(10)):
        inner = msg_inner(log)
        if inner is None:
            continue
        lm = fmap(inner)
        entry = {"commandType": lm.get(1), "phaseType": lm.get(2)}
        if 5 in lm:
            entry["card"] = decode_produce_card(lm[5])
        if 4 in lm:
            entry["useIndex"] = lm[4]
        if 3 in lm:
            entry["selectIndexes"] = as_list(lm[3])
        if 6 in lm:
            raw = lm[6][0] if isinstance(lm[6], tuple) else lm[6]
            entry["drink"] = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        sub.append(entry)
    if sub:
        info["logs"] = sub
    return info


def decode_turn_logs(top: dict) -> list[dict]:
    """请求顶层 field3 = turnEndLogs（ExamTurnEndLog）。

    turn=1, score=2, stamina=3, consumedStamina=4, block=5, additionBlock=6,
    parameterType=7, startPlayHandProduceCards=50(回合开始手牌), startPlayStatuses=51,
    startPlayHoldProduceCards=52, commands=100(本回合打出, useProduceCard=5)。
    """
    turns = []
    for tl in as_list(top.get(3)):
        inn = msg_inner(tl)
        if inn is None:
            continue
        m = fmap(inn)
        hand = [decode_produce_card(v) for v in as_list(m.get(50))]
        played = []
        for c in as_list(m.get(100)):
            ci = msg_inner(c)
            if ci is None:
                continue
            cm = fmap(ci)
            if 5 in cm:
                played.append(decode_produce_card(cm[5]))
        turns.append({
            "turn": m.get(1), "score": m.get(2), "stamina": m.get(3),
            "parameterType": m.get(7), "hand": hand, "played": played,
        })
    return turns


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--json", action="store_true", help="同时写 exam_truth.json")
    args = ap.parse_args(argv)

    records = []
    for line in Path(args.file).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    truth = []
    for n, rec in enumerate(records):
        if not rec.get("path", "").endswith("StepAuditionEndExamBattle"):
            continue
        req = body(rec, "req_plain_hex")
        if req is None:
            continue
        top = fmap(parse(req))
        result_inner = msg_inner(top.get(2))
        if result_inner is None:
            continue
        rm = fmap(result_inner)
        print(f"\n=== [{n}] {rec.get('ts')} 考试结束 ===")
        print(f"  rank={rm.get(1)} score={rm.get(2)} stamina={rm.get(3)} "
              f"Vo={rm.get(8)} Da={rm.get(9)} Vi={rm.get(10)}")
        turns = decode_turn_logs(top)
        print("  逐回合（手牌=回合开始抽到的牌，打出=本回合用卡）:")
        for t in turns:
            print(f"    T{t['turn']} param={t['parameterType']} score={t['score']} "
                  f"手牌={t['hand']} 打出={t['played']}")
        truth.append({"ts": rec.get("ts"), "rank": rm.get(1), "score": rm.get(2), "turns": turns})
    if args.json:
        out = Path(args.file).parent / "exam_truth.json"
        out.write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n逐回合 ground truth 已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
