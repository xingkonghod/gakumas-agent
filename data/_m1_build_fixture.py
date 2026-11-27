"""M1 fixture 构建（脚本不提交；产物 tests/fixtures/m1_rinami_trace.json 提交）。

oracle 锚定牌区（引擎可选 oracle），clean-room 消费图按牌区上下文计算各消费点次数：
  create_deck_random=1/卡、move_search_random=2nf、move_pick_random=1+nf、reshuffle=grave-1。
支援掷点次数 = oracle 总消费 − 上述图计算消费（余数），并记录入手牌上下文供 support_rolls
独立复核（探针①另有全预测回归）。rng 状态纯由 xorshift32 按各事件次数正向迭代，逐决策对实机。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.sim.rng_graph import RngStream, ConsumptionGraph, create_deck_random, move_search_random, move_pick_random  # noqa: E402

SSR = {"p_card-00-men-3_003", "p_card-01-men-3_036", "p_card-00-men-3_012",
       "p_card-01-men-3_034", "p_card-01-ido-3_213", "p_card-01-men-3_006",
       "p_card-01-men-3_035", "p_card-01-act-3_049", "p_card-01-men-3_033",
       "p_card-01-ido-3_200", "p_card-01-act-3_010"}
CREATORS = {"p_card-01-men-2_099", "p_card-01-men-2_098"}


def build(w):
    d = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
    op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
    ex = [json.loads(l) for l in open(ROOT / f"data/_rinami_live/{w}/execution.jsonl", encoding="utf-8")]
    dec = [r["data"] for r in ex if r["kind"] == "decision"]
    rows = d["rows"]
    first001 = next((i for i, r in enumerate(rows) if r["live_card"] and r["live_card"].startswith("p_card-01-act-2_001")), None)
    actions = []
    for k, r in enumerate(rows):
        zb = {zn: [tuple(c) for c in r["zones_before"].get(zn, [])] for zn in ("hand", "deck", "grave", "lost")}
        za = {zn: [tuple(c) for c in r["zones_after"].get(zn, [])] for zn in ("hand", "deck", "grave", "lost")}
        played = r["live_card"]
        pid = played.split("::")[0] if played else None
        turn_changed = r["turn_after"] > r["turn_before"]
        evs = []  # (kind, count, params)
        # 生成
        if pid in CREATORS:
            deck_len = len(zb["deck"]) - 1  # draw 1 后 create
            evs.append(["create_deck_random", 1, {"deck_len": deck_len}])
        # 034 移动
        if pid == "p_card-01-men-3_034":
            nf = sum(1 for c in zb["deck"] + zb["grave"] if c[0] in SSR)
            evs.append(["move_search_random", 2 * nf, {"nf": nf, "playing": True}])
        # 001 enchant 移动 acc
        if k == first001:
            nf = sum(1 for c in zb["deck"] + zb["grave"] if c[0] == "p_card-00-acc-0_002")
            if nf:
                evs.append(["move_pick_random", 1 + nf, {"nf": nf, "pick_min": 1, "pick_max": 1}])
        # 重洗（回合转换，grave 清空）
        if turn_changed and len(za["grave"]) == 0 and len(zb["grave"]) > 0:
            discard = len(zb["hand"]) - (1 if played else 0)
            grave_count = len(zb["grave"]) + discard
            evs.append(["reshuffle", grave_count - 1, {"grave_count": grave_count}])
        non_support = sum(e[1] for e in evs)
        support_count = r["consumption"] - non_support
        if support_count < 0:
            raise ValueError(f"{w} k={k} support<0: cons={r['consumption']} non_support={non_support} evs={evs}")
        if support_count > 0:
            # 入手牌上下文（回合转换=hand_after；099/098=deck顶；饮料=soda draw）
            if turn_changed:
                cards = [list(c) for c in za["hand"]]
            elif pid in CREATORS:
                cards = [list(zb["deck"][0])] if zb["deck"] else []
            elif r["action"][0] == "drink":
                cards = [list(c) for c in zb["deck"][:2]]
            else:
                cards = []
            evs.append(["support", support_count, {"attr": r["turn_after"] and op["turnAttributes"][r["turn_after"] - 1], "cards": cards}])
        actions.append({"k": k, "action": r["action"], "live_i": dec[k]["i"] if k < len(dec) else None,
                        "live_rng": dec[k]["rng"] if k < len(dec) else None,
                        "turn_before": r["turn_before"], "turn_after": r["turn_after"],
                        "is_drink": r["action"][0] == "drink",
                        "oracle_cons": r["consumption"], "events": evs})
    return {"w": w, "opening_rng": op["parameterScalars"]["currentRandom"]["state"],
            "turn_attributes": op["turnAttributes"], "actions": actions}


if __name__ == "__main__":
    out = {w: build(w) for w in ("W7", "W9")}
    p = ROOT / "tests/fixtures/m1_rinami_trace.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", p)
    # 验证：图按事件次数迭代 rng == 实机
    for w in ("W7", "W9"):
        s = out[w]["opening_rng"]
        ok = 0
        for a in out[w]["actions"]:
            if s == a["live_rng"]:  # 决策点状态 = 动作前
                ok += 1
            else:
                print(f"  {w} k={a['k']} mismatch state={s} live={a['live_rng']} cons={a['oracle_cons']} evsum={sum(e[1] for e in a['events'])}")
            for _ in range(a["oracle_cons"]):
                s ^= (s << 13) & 0xFFFFFFFF; s ^= s >> 17; s ^= (s << 5) & 0xFFFFFFFF; s &= 0xFFFFFFFF
        print(w, "rng match", ok, "/", len(out[w]["actions"]))
