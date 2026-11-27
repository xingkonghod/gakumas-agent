"""M6 探针 5：阶段1.5 确定式增量批逐瓶引擎 oracle（状态增量 + rng 消费数）。不提交。

6 瓶 = 5 个批次 id + 焙茶（ExamPreservation 映射 side-effect，顺带验证）：
  * 喝一瓶前后全状态增量 + xorshift32 消费数（确定式段必须 = 0）；
  * 回合边界附魔 buff：喝后 SKIP 两回合，验证 +1/回合 且永久（effectTurn=-1）；
    茶的「回合结束好印象+1」实测语义：好印象结算**之前**触发（+1 计入本回合结算分），
    且 endTurn 衰减有 freshBuffs 保护（当回合获得层本回合末不扣）→ 0 层起步
    end1 score+>0 / impression 净+1，end2 结算 2 层 / 旧层 -1 / impression 净 0；
  * 无饮料对照局同 seed 同 loadout：end 步 rng 消费差分 = 0（附魔不掷点）；
  * 热绿茶 Select 选牌事件（select_choices：候选/选取/规则）+ 温存 2 段階直给；
  * 引擎 greedy_select_policy 按 playEffects effectValue1 总和选牌（玩家选择代理），
    sim hold_pick 按白值分降序（另一种玩家选择代理）——选取牌不要求逐位同，
    结构增量（hold+1/deck-1/指針/rng=0）必须配对。

口径仿 data/_drinks_probe3.py（W9 loadout 模板，剥 P 道具/附魔/支援卡净化回合边界）。
内存守卫：free < 0.6GB 直接退出（托管 A/B + m1-rng/hajime-tune/pimc-opt 在跑）。
"""
import ctypes
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]


class _MEM(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


mem = _MEM()
mem.dwLength = ctypes.sizeof(_MEM)
ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
free_gb = mem.ullAvailPhys / 1024**3
print(f"free memory: {free_gb:.2f} GB")
if free_gb < 0.6:
    raise SystemExit("BLOCKED: free memory < 0.6GB（重批次守卫）")

os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))

from gkbench import engine  # noqa: E402

engine.setup()
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from gkagent.sim.exam_shuffle import NativeRandom  # noqa: E402

W9 = ROOT / "data/_rinami_live/W9"
BASE = json.load(open(W9 / "gkms-loadout.json", encoding="utf-8"))

# (id, 标签, 期望回合边界效果)
BOTTLES = [
    ("pdrink_01-3-002", "严选初星玛奇朵", "turn_end_focus"),
    ("pdrink_02-3-006", "严选初星茶", "turn_end_impression"),
    ("pdrink_02-3-007", "严选初星拼配咖啡", "turn_end_aggressive"),
    ("pdrink_03-3-008", "严选初星印度茶", "turn_start_full_power"),
    ("pdrink_03-2-007", "热绿茶", "search_hold+preservation2"),
    ("pdrink_03-1-010", "焙茶", "preservation1+fpp2"),
]


def loadout_for(did):
    doc = dict(BASE)
    doc["drink_ids"] = [did]
    doc["produce_item_ids"] = []
    doc["lesson_start_enchant_ids"] = []
    doc["main_item_enchant_ids"] = []
    doc["support_cards"] = []
    return doc


def advances(a, b, cap=400):
    rng = NativeRandom(a)
    for k in range(cap + 1):
        if rng.state == b:
            return k
        rng.advance()
    return None


def full(s):
    st = s.state

    def zone(n):
        return [f"{c['produce_card_id']}::{c.get('current_upgrade_count', 0)}" for c in s._zone(n)]

    return {
        "turn": s.turn, "score": int(st.score), "stamina": int(st.stamina),
        "rng": int(s.deck.rng.state),
        "focus": int(st.lesson_buff), "impression": int(st.review),
        "aggressive": int(st.aggressive), "fpp": int(st.full_power_point),
        "stance": st.idol_status_type, "stance_step": int(st.idol_status_step_count),
        "block": int(st.block), "extra_plays": int(st.turn_playable_adds),
        "preservation_change_count": int(st.preservation_change_count),
        "hand": zone("hand"), "deck": zone("deck"), "grave": zone("grave"),
        "hold": zone("hold"), "drinks": list(s.drinks),
    }


def delta(a, b):
    return {k: b[k] - a[k] for k in ("score", "stamina", "focus", "impression",
                                     "aggressive", "fpp", "stance_step", "block",
                                     "extra_plays", "preservation_change_count")
            if isinstance(a[k], int) and isinstance(b[k], int) and b[k] != a[k]}


master = engine.master()
print("rules =", engine.native()[0].exam_rules_version)
results = []
for did, name, tag in BOTTLES:
    doc = loadout_for(did)
    seed = int(doc["seed"])
    session, _meta = build_hif_loadout_session(master, doc, seed)
    ctrl, _ = build_hif_loadout_session(master, doc, seed)
    s0 = full(session)
    session.step(("drink", 0), observe=False)
    s1 = full(session)
    adv_drink = advances(s0["rng"], s1["rng"])
    selects = list(session.deck.select_choices)
    # 回合边界 1（喝后当回合末 + 下一回合开始）
    c0 = full(ctrl)
    ctrl.step(("end",), observe=False)
    c1 = full(ctrl)
    session.step(("end",), observe=False)
    s2 = full(session)
    adv_end1 = advances(s1["rng"], s2["rng"])
    adv_end1_ctrl = advances(c0["rng"], c1["rng"])
    # 回合边界 2（永久验证）
    ctrl.step(("end",), observe=False)
    c2 = full(ctrl)
    session.step(("end",), observe=False)
    s3 = full(session)
    adv_end2 = advances(s2["rng"], s3["rng"])
    adv_end2_ctrl = advances(c1["rng"], c2["rng"])

    rec = {
        "id": did, "name": name, "tag": tag,
        "drink_delta": delta(s0, s1),
        "drink_rng_advances": adv_drink,
        "drink_stance": [s0["stance"], s1["stance"]],
        "drink_hold_delta": len(s1["hold"]) - len(s0["hold"]),
        "drink_deck_delta": len(s1["deck"]) - len(s0["deck"]),
        "selects": selects,
        "end1_delta": delta(s1, s2), "end1_ctrl_delta": delta(c0, c1),
        "end1_rng_advances": adv_end1, "end1_ctrl_rng_advances": adv_end1_ctrl,
        "end2_delta": delta(s2, s3), "end2_ctrl_delta": delta(c1, c2),
        "end2_rng_advances": adv_end2, "end2_ctrl_rng_advances": adv_end2_ctrl,
        "impression_after_end1": s2["impression"],
        "score_gain_end1": s2["score"] - s1["score"],
        "score_gain_end2": s3["score"] - s2["score"],
        "hold_after": s1["hold"],
    }
    # 逐瓶断言（确定式口径）
    checks = {}
    checks["drink_rng_zero"] = adv_drink == 0
    if tag.startswith("turn_end") or tag == "turn_start_full_power":
        checks["drink_no_immediate_delta"] = not rec["drink_delta"]
        key = {"turn_end_focus": "focus", "turn_end_impression": "impression",
               "turn_end_aggressive": "aggressive", "turn_start_full_power": "fpp"}[tag]
        if tag == "turn_end_impression":
            # 实测语义（probe5_decay 测定）：附魔在好印象结算**前**触发（+1 计入
            # 本回合结算分），且 endTurn 衰减有 freshBuffs 保护——当回合获得的层
            # 本回合末不扣。0 层起步：end1 score+>0 且 impression 净+1（fresh 存活）；
            # end2 附魔+1 结算 2 层、旧层 -1 → impression 净 0、score+>0（永久）。
            checks["enchant_before_review_settle"] = (
                rec["score_gain_end1"] > 0
                and s2["impression"] == s1["impression"] + 1
            )
            checks["fresh_protect_end1"] = s2["impression"] == 1
            checks["permanent_2turns"] = (
                rec["score_gain_end2"] > 0 and s3["impression"] == s2["impression"]
            )
        else:
            checks["buff_plus1_end1"] = rec["end1_delta"].get(key) == 1
            checks["buff_plus2_end2_total"] = (
                rec["end1_delta"].get(key, 0) + rec["end2_delta"].get(key, 0) == 2
            )
        checks["end_rng_diff_zero"] = (
            adv_end1 == adv_end1_ctrl and adv_end2 == adv_end2_ctrl
        )
    elif did == "pdrink_03-2-007":
        checks["hold_plus1"] = rec["drink_hold_delta"] == 1
        checks["deck_minus1"] = rec["drink_deck_delta"] == -1
        checks["stance_save2"] = s1["stance"] == "Preservation" and s1["stance_step"] == 2
        checks["select_event"] = (
            len(selects) == 1 and selects[0]["produce_card_search_id"] == "p_card_search-deck_grave"
            and selects[0]["rule"] == "greedy_select_policy"
        )
    elif did == "pdrink_03-1-010":
        checks["stance_save1"] = s1["stance"] == "Preservation" and s1["stance_step"] == 1
        checks["fpp_plus2"] = rec["drink_delta"].get("fpp") == 2
    rec["checks"] = checks
    rec["all_pass"] = all(checks.values())
    results.append(rec)
    print(f"\n=== {did} {name} ({tag}) ===")
    print(f"  drink rng_advances={adv_drink} delta={rec['drink_delta']} "
          f"stance {s0['stance']}->{s1['stance']} hold+{rec['drink_hold_delta']}")
    print(f"  end1 delta={rec['end1_delta']} rng={adv_end1} (ctrl {adv_end1_ctrl})")
    print(f"  end2 delta={rec['end2_delta']} rng={adv_end2} (ctrl {adv_end2_ctrl})")
    if selects:
        print(f"  selects: {json.dumps(selects, ensure_ascii=False)}")
    print(f"  checks: {checks} -> {'PASS' if rec['all_pass'] else 'FAIL'}")
    del session, ctrl

# ---- 好印象衰减口径场景（sim 配对用）：A 立即 imp+3 / B 茶附魔 / C 混合 ----
def snap(s):
    st = s.state
    return {"turn": s.turn, "score": int(st.score), "impression": int(st.review)}


decay = {}
for label, dids in (
    ("A_rooibos", ["pdrink_02-1-006"]),
    ("B_tea", ["pdrink_02-3-006"]),
    ("C_rooibos_tea", ["pdrink_02-1-006", "pdrink_02-3-006"]),
):
    doc = loadout_for(dids[0])
    doc["drink_ids"] = list(dids)
    s, _ = build_hif_loadout_session(master, doc, int(doc["seed"]))
    rows = [{"step": "start", **snap(s)}]
    for i in range(len(dids)):
        s.step(("drink", 0), observe=False)  # 喝掉的瓶从列表移除，下一瓶仍 idx0
        rows.append({"step": f"drink{i}", **snap(s)})
    for k in range(3):
        s.step(("end",), observe=False)
        rows.append({"step": f"end{k+1}", **snap(s)})
    decay[label] = rows
    print(f"\n=== decay {label} {dids} ===")
    for r in rows:
        print("  ", r)
    del s

out = {"free_gb_at_start": round(free_gb, 2), "bottles": results, "decay": decay,
       "all_pass": all(r["all_pass"] for r in results)}
(ROOT / "data/_drinks_probe5.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\noverall: {'PASS' if out['all_pass'] else 'FAIL'}; written data/_drinks_probe5.json")
raise SystemExit(0 if out["all_pass"] else 1)
