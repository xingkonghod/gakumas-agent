"""M6 探针 6：阶段2 batch2 逐瓶引擎 oracle（rng/增量/出牌交互）。不提交。

4 瓶：姜汁汽水（强气1）/ 超级苏打（强气2）/ 黑醋汁（Select→hand +  next2 cost0）/
特制精华（下一张主动卡再发动）。对照局同 seed 同 loadout 无饮料，逐出牌比对
score/stamina/block 增量（精华再发动倍率 / 黑醋汁 cost0 口径）。
内存守卫：free < 0.9GB 退出（lead 阶段2 阈值）。
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
if free_gb < 0.9:
    raise SystemExit("BLOCKED: free memory < 0.9GB（阶段2 守卫）")

os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
from gkbench import engine  # noqa: E402

engine.setup()
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from gkagent.sim.exam_shuffle import NativeRandom  # noqa: E402

BASE = json.load(open(ROOT / "data/_rinami_live/W9/gkms-loadout.json", encoding="utf-8"))
master = engine.master()
print("rules =", engine.native()[0].exam_rules_version)

BOTTLES = [
    ("pdrink_03-1-009", "姜汁汽水", "concentration1"),
    ("pdrink_03-3-009", "初星超级苏打水", "concentration2"),
    ("pdrink_01-3-012", "初星黑醋汁", "select_hand_cost0"),
    ("pdrink_02-3-010", "特制初星精华", "encore_active"),
]


def loadout_for(dids):
    doc = dict(BASE)
    doc["drink_ids"] = list(dids)
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
        "rng": int(s.deck.rng.state), "block": int(st.block),
        "focus": int(st.lesson_buff), "impression": int(st.review),
        "aggressive": int(st.aggressive), "fpp": int(st.full_power_point),
        "stance": st.idol_status_type, "stance_step": int(st.idol_status_step_count),
        "concentration_change_count": int(st.concentration_change_count),
        "stamina_reduce_change": bool(st.stamina_reduce_change),
        "stamina_reduce_change_threshold": int(st.stamina_reduce_change_threshold),
        "current_card_effect_repeat": int(st.current_card_effect_repeat),
        "hand": zone("hand"), "deck": zone("deck"), "grave": zone("grave"),
        "hold": zone("hold"), "drinks": list(s.drinks),
    }


def card_category(inst):
    # 主数据 decoded 行类别字段名不定；id 段编码可靠（-act-/-men-/-ido-）。
    cid = inst["produce_card_id"]
    if "-act-" in cid:
        return "ActiveSkill"
    if "-men-" in cid:
        return "MentalSkill"
    if "-ido-" in cid:
        return "IdolUnique"
    return "?"


def play_seq(s, n=4):
    """出牌（扫首个合法 play 下标），记录逐出牌增量 + 卡类别 + rng 消费。"""
    rows = []
    for k in range(n):
        legal = s.legal_actions()
        plays = [a for a in legal if a[0] == "play"]
        if not plays:
            rows.append({"k": k, "skipped": True, "legal": [list(a) for a in legal]})
            break
        idx = plays[0][1]
        inst = s._zone("hand")[idx]
        b = full(s)
        s.step(("play", idx), observe=False)
        a = full(s)
        rows.append({
            "k": k, "idx": idx, "card": inst["produce_card_id"],
            "upgrade": int(inst.get("current_upgrade_count") or 0),
            "category": card_category(inst),
            "d_score": a["score"] - b["score"], "d_stamina": a["stamina"] - b["stamina"],
            "d_block": a["block"] - b["block"], "d_focus": a["focus"] - b["focus"],
            "d_impression": a["impression"] - b["impression"],
            "d_aggressive": a["aggressive"] - b["aggressive"], "d_fpp": a["fpp"] - b["fpp"],
            "rng_advances": advances(b["rng"], a["rng"]),
            "repeat_after": a["current_card_effect_repeat"],
            "reduce_change_after": a["stamina_reduce_change"],
            "reduce_threshold_after": a["stamina_reduce_change_threshold"],
        })
    return rows


def play_seq_multi(s, n=8):
    """跨回合出牌（无合法 play 时 end turn 继续），锁步对照用。"""
    rows = []
    while len([r for r in rows if not r.get("skipped")]) < n:
        legal = s.legal_actions()
        plays = [a for a in legal if a[0] == "play"]
        if not plays:
            if s.finished or ("end",) not in legal:
                break
            s.step(("end",), observe=False)
            continue
        idx = plays[0][1]
        inst = s._zone("hand")[idx]
        b = full(s)
        s.step(("play", idx), observe=False)
        a = full(s)
        rows.append({
            "k": len(rows), "idx": idx, "turn": b["turn"], "card": inst["produce_card_id"],
            "category": card_category(inst),
            "d_score": a["score"] - b["score"], "d_stamina": a["stamina"] - b["stamina"],
            "d_block": a["block"] - b["block"], "d_focus": a["focus"] - b["focus"],
            "d_impression": a["impression"] - b["impression"],
            "d_aggressive": a["aggressive"] - b["aggressive"], "d_fpp": a["fpp"] - b["fpp"],
            "rng_advances": advances(b["rng"], a["rng"]),
            "repeat_after": a["current_card_effect_repeat"],
        })
    return rows


results = []
for did, name, tag in BOTTLES:
    doc = loadout_for([did])
    seed = int(doc["seed"])
    session, _ = build_hif_loadout_session(master, doc, seed)
    ctrl, _ = build_hif_loadout_session(master, loadout_for([]), seed)
    s0 = full(session)
    session.step(("drink", 0), observe=False)
    s1 = full(session)
    adv_drink = advances(s0["rng"], s1["rng"])
    selects = list(session.deck.select_choices)
    rec = {
        "id": did, "name": name, "tag": tag,
        "drink_rng_advances": adv_drink,
        "drink_d_score": s1["score"] - s0["score"],
        "drink_d_stamina": s1["stamina"] - s0["stamina"],
        "drink_d_fpp": s1["fpp"] - s0["fpp"],
        "drink_stance": [s0["stance"], s1["stance"]],
        "drink_stance_step": [s0["stance_step"], s1["stance_step"]],
        "drink_d_conc_count": s1["concentration_change_count"] - s0["concentration_change_count"],
        "drink_hand_delta": len(s1["hand"]) - len(s0["hand"]),
        "drink_deck_delta": len(s1["deck"]) - len(s0["deck"]),
        "reduce_change": [s0["stamina_reduce_change"], s1["stamina_reduce_change"]],
        "reduce_threshold": [s0["stamina_reduce_change_threshold"], s1["stamina_reduce_change_threshold"]],
        "repeat": [s0["current_card_effect_repeat"], s1["current_card_effect_repeat"]],
        "selects": selects,
    }
    if tag == "select_hand_cost0":
        rec["plays"] = play_seq(session, 6)
        rec["ctrl_plays"] = play_seq(ctrl, 6)
    elif tag == "encore_active":
        # 跨回合找正分主动卡（W9 开局手牌可能全 buff）；两局锁步（同手牌无 move）。
        rec["plays"] = play_seq_multi(session, 8)
        rec["ctrl_plays"] = play_seq_multi(ctrl, 8)
    checks = {"drink_rng_zero": adv_drink == 0}
    if tag == "concentration1":
        checks["stance_strong1"] = s1["stance"] == "Concentration" and s1["stance_step"] == 1
        checks["fpp_plus1"] = rec["drink_d_fpp"] == 1
        checks["conc_count_plus1"] = rec["drink_d_conc_count"] == 1
    elif tag == "concentration2":
        checks["stance_strong2"] = s1["stance"] == "Concentration" and s1["stance_step"] == 2
        checks["conc_count_plus1"] = rec["drink_d_conc_count"] == 1
    elif tag == "select_hand_cost0":
        checks["hand_plus1"] = rec["drink_hand_delta"] == 1
        checks["deck_minus1"] = rec["drink_deck_delta"] == -1
        checks["select_event"] = (
            len(selects) == 1 and selects[0]["produce_card_search_id"] == "p_card_search-deck_grave"
            and selects[0]["rule"] == "greedy_select_policy"
        )
        # cost0 口径：对照局正费牌（d_stamina<0）的前 2 张在目标局 stamina/block
        # 增量全 0（整费归零，先于元气吸收）；第 3 张正费牌恢复正常扣费。
        # 0 费牌（对照 d_stamina==0）不消耗次数。引擎不暴露标量字段（效果层追踪）。
        tp = [p for p in rec["plays"] if not p.get("skipped")]
        cp = [p for p in rec["ctrl_plays"] if not p.get("skipped")]
        pos = [(t, c) for t, c in zip(tp, cp) if c["d_stamina"] < 0]
        rec["cost0_positive_cost_plays"] = [
            {"k": t["k"], "card": t["card"], "ctrl_stamina": c["d_stamina"],
             "target_stamina": t["d_stamina"], "target_block": t["d_block"]}
            for t, c in pos
        ]
        if len(pos) >= 3:
            # 整费归零（先于元气吸收）：前 2 张正费牌 stamina 增量 0；block 增量含
            # 卡自身元气授予，不与 0 比（k2 men-3_012 +5 是卡效果）。
            checks["cost0_first2_zero"] = all(t["d_stamina"] == 0 for t, c in pos[:2])
            checks["cost0_third_normal"] = (
                pos[2][0]["d_stamina"] == pos[2][1]["d_stamina"]
                and pos[2][0]["d_block"] == pos[2][1]["d_block"]
            )
    elif tag == "encore_active":
        tp, cp = rec["plays"], rec["ctrl_plays"]
        # 再发动 = 第一张主动卡直接效果 ×2（打分/buff 层数）；0 分 buff 卡也能观测
        # （focus/impression/aggressive/fpp 增量翻倍）。牌费不翻倍。
        first_active = None
        for t, c in zip(tp, cp):
            if t["category"] == "ActiveSkill":
                first_active = {
                    "k": t["k"], "card": t["card"],
                    "target": {x: t[x] for x in ("d_score", "d_focus", "d_impression",
                                                 "d_aggressive", "d_fpp")},
                    "ctrl": {x: c[x] for x in ("d_score", "d_focus", "d_impression",
                                               "d_aggressive", "d_fpp")},
                }
                break
        rec["encore_observed"] = first_active
        # W9 牌堆首张主动卡是 enchant 型（act-3_049，focus 是费用），直接增量不可观；
        # 再发动倍率断言放在下面纯打分卡干净实验（encore_clean）。此处仅记录。
    rec["checks"] = checks
    rec["all_pass"] = all(checks.values())
    results.append(rec)
    print(f"\n=== {did} {name} ({tag}) ===")
    print(f"  drink rng={adv_drink} d_stamina={rec['drink_d_stamina']} d_fpp={rec['drink_d_fpp']} "
          f"stance {s0['stance']}->{s1['stance']} step {s0['stance_step']}->{s1['stance_step']}")
    print(f"  reduce_change={rec['reduce_change']} threshold={rec['reduce_threshold']} repeat={rec['repeat']}")
    if selects:
        print(f"  selects: {json.dumps(selects, ensure_ascii=False)[:300]}")
    for p in rec.get("plays", []):
        print(f"  play: {p}")
    if "encore_observed" in rec:
        print(f"  encore_observed: {rec['encore_observed']}")
    print(f"  checks: {checks} -> {'PASS' if rec['all_pass'] else 'FAIL'}")
    del session, ctrl

# ---- 精华再发动干净实验：纯打分主动卡自定义牌堆（排除 enchant/timer 干扰）----
CLEAN_CARD = "p_card-01-act-2_003"  # 純 ExamLesson +18，0 费
clean_doc = loadout_for(["pdrink_02-3-010"])
clean_doc["deck_cards"] = [{"produce_card_id": CLEAN_CARD, "current_upgrade_count": 0} for _ in range(10)]
clean_doc["include_produce_default"] = False
ctrl_doc = loadout_for([])
ctrl_doc["deck_cards"] = list(clean_doc["deck_cards"])
ctrl_doc["include_produce_default"] = False
cs, _ = build_hif_loadout_session(master, clean_doc, int(clean_doc["seed"]))
cc, _ = build_hif_loadout_session(master, ctrl_doc, int(ctrl_doc["seed"]))
cs.step(("drink", 0), observe=False)
clean_rows = []
for k in range(3):
    if k == 2:  # 第 3 张在下一回合（验证 effectTurn=1 过期）
        cs.step(("end",), observe=False)
        cc.step(("end",), observe=False)
    bt, bc = full(cs), full(cc)
    cs.step(("play", 0), observe=False)
    cc.step(("play", 0), observe=False)
    at, ac = full(cs), full(cc)
    clean_rows.append({
        "k": k, "turn": bt["turn"],
        "target_score": at["score"] - bt["score"], "ctrl_score": ac["score"] - bc["score"],
        "target_rng": advances(bt["rng"], at["rng"]),
    })
clean_checks = {
    "first_doubled": clean_rows[0]["target_score"] == 2 * clean_rows[0]["ctrl_score"] > 0,
    "second_normal": clean_rows[1]["target_score"] == clean_rows[1]["ctrl_score"] > 0,
    "third_expired_normal": clean_rows[2]["target_score"] == clean_rows[2]["ctrl_score"] > 0,
}
clean = {"card": CLEAN_CARD, "rows": clean_rows, "checks": clean_checks,
         "all_pass": all(clean_checks.values())}
print(f"\n=== encore clean ({CLEAN_CARD}) ===")
for r in clean_rows:
    print("  ", r)
print(f"  checks: {clean_checks} -> {'PASS' if clean['all_pass'] else 'FAIL'}")
del cs, cc

out = {"free_gb_at_start": round(free_gb, 2), "bottles": results, "encore_clean": clean,
       "all_pass": all(r["all_pass"] for r in results) and clean["all_pass"]}
(ROOT / "data/_drinks_probe6.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\noverall: {'PASS' if out['all_pass'] else 'FAIL'}; written data/_drinks_probe6.json")
raise SystemExit(0 if out["all_pass"] else 1)
