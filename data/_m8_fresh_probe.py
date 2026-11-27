"""M8 通用 fresh buff 保护 oracle 探针（engine-gap M8，rules=69 DLL 不重编）。不提交。

逐渠道（卡效果 / 立即饮料 / P 道具 / 附魔）× 逐 buff（impression / condition /
review_multiple / score_buff / lock_stance / half_cost / focus / aggressive / fpp）
构造「当回合获得层」→ 回合末衰减轨迹。3 局串行（≤3 局），内存守卫 wait_free(1024)。

观测：observe() + 解码标量（review_added_this_turn / parameter_buff_remaining /
parameter_buff_until_turn / parameter_buff_passing_turn_start / stance_lock_turns /
stance_lock_passing_turn_start / stamina_consumption_*_until_turn）+ 原始 timed 层
（value, until_turn, fresh）。permils=1000 → 属性倍率 ×1.0，好印象结算分=层数。

G1 card_imp_cond：卡渠道好印象（t1/t2 两次获得测 fresh 累积+旧层衰减）+ 好调（t3，110）。
G2 timed_lock_cost：好印象强化/打分上升量倍率/指針固定/体力消耗减少/干劲（永久核对）。
G3 drink_pitem：立即饮料好印象+3 / P 道具好印象（status_gain+turn_end）/ P 道具好调。
附魔渠道已由 data/_drinks_probe5_decay.py（B_tea/C）覆盖，本探针不重复。
"""
from __future__ import annotations
import ctypes, gc, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
DLL = ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"
os.environ["GKMS_NATIVE_LIB"] = str(DLL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")

from GakumasCLI.scenario.exam_session import (Master, ExamLoading, ProduceState,  # noqa: E402
                                              SegmentConfig, open_exam)
from GakumasCLI.engine.semantics import MasterCatalog  # noqa: E402


def free_mb():
    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = M(); m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1048576


def wait_free(min_mb=1024, cap_s=600):
    t0 = time.perf_counter()
    while free_mb() < min_mb and time.perf_counter() - t0 < cap_s:
        print(f"  [mem] free {free_mb():.0f}MB, wait 20s", flush=True); time.sleep(20)


def build(master, deck, seed, *, enchants=(), limit_turn=10, initial=None, drinks=()):
    produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck,
                           item_enchant_ids=list(enchants), plan_type=1)
    cfg = SegmentConfig(segment_id="m8fresh", segment_type="Audition Mid1", limit_turn=limit_turn,
                        score_cap=None, parameter_type=None, seed=seed, gimmick_group_id=None,
                        audition_permils={1: 1000, 2: 1000, 3: 1000},
                        audition_parameter_values={1: 100, 2: 100, 3: 100},
                        audition_npc_rng_advances=0, turn_start_distribute=3,
                        eligible_supports=(), resolve_initial_cards=True,
                        initial_card_ids=list(initial) if initial else None,
                        upgrade_tiers=set(master.cards), drink_ids=list(drinks),
                        lesson_start_enchant_ids=list(enchants))
    return open_exam(ExamLoading(master, produce, cfg))


LAYER_LISTS = ("review_multiple_layers", "lesson_parameter_multiple_layers",
               "lesson_buff_multiple_layers", "review_count_add_layers")
SCALARS = ("review", "review_added_this_turn", "review_turn_start",
           "review_turn_end_reduce_lock_turn", "lesson_buff", "aggressive",
           "full_power_point", "parameter_buff_remaining", "parameter_buff_until_turn",
           "parameter_buff_passing_turn_start", "stance_lock_turns",
           "stance_lock_passing_turn_start", "stamina_consumption_down_until_turn",
           "stamina_consumption_add_until_turn", "score", "stamina", "turn")


def snap(s):
    o = s.observe()
    out = {"turn": o.get("turn"), "score": o.get("score"), "stamina": o.get("stamina"),
           "hand_ids": [c.get("produce_card_id") for c in o.get("hand", [])],
           "finished": o.get("finished")}
    st = s.state
    for name in SCALARS:
        try:
            out[name] = getattr(st, name)
        except Exception:  # noqa: BLE001
            out[name] = None
    for name in LAYER_LISTS:
        try:
            rows = s._decoded_state(name)
            out[name] = [list(r) for r in rows]
        except Exception:  # noqa: BLE001
            out[name] = None
    return out


def _norm(s):
    return s.replace("PRODUCE_EXAM_EFFECT_TYPE_", "").replace("_", "").lower()


def find_cards(cat, type_name, *, single=True, no_trigger=True, limit=8):
    want = _norm(type_name)
    out = []
    for (cid, up), cd in cat.cards.items():
        if up != 0:
            continue
        eids = cd.play_effect_ids
        if not eids:
            continue
        if no_trigger and any(cd.play_effect_trigger_ids):
            continue
        types = [cat.effects[e].type_name for e in eids if e in cat.effects]
        if not types or not all(_norm(t) == want for t in types):
            continue
        if single and len(types) != 1:
            continue
        e = cat.effects[eids[0]]
        out.append({"id": cid, "name": cd.name, "value1": e.value1, "turn": e.turn,
                    "count": e.count, "n_effects": len(types)})
        if len(out) >= limit:
            break
    return out


def run(master, deck, seed, script, tag, *, enchants=(), limit_turn=10, initial=None,
        drinks=(), out=None):
    wait_free()
    s = build(master, deck, seed, enchants=enchants, limit_turn=limit_turn,
              initial=initial, drinks=drinks)
    rows = [{"tag": tag, "kind": "open", "hand_raw": [dict(c) for c in s.deck.hand], **snap(s)}]
    prev = snap(s)
    n = 0
    while not s.finished and n < 60:
        turn = prev["turn"]
        mode = script.get(turn, "skip")
        hand = list(s.deck.hand)
        action = ("end",); played = None
        if isinstance(mode, tuple) and mode[0] == "drink":
            action = ("drink", int(mode[1]))
        elif isinstance(mode, tuple) and mode[0] == "play_id":
            for i, inst in enumerate(hand):
                if inst.get("produce_card_id") == mode[1] and s.can_play(inst):
                    action = ("play", i); played = mode[1]; break
        elif isinstance(mode, tuple) and mode[0] == "play_any":
            for want in mode[1]:
                done = False
                for i, inst in enumerate(hand):
                    if inst.get("produce_card_id") == want and s.can_play(inst):
                        action = ("play", i); played = want; done = True; break
                if done:
                    break
        before = snap(s)
        s.step(action, observe=False)
        after = snap(s)
        rows.append({"tag": tag, "kind": "step", "i": n, "action": list(action),
                     "played": played, "turn_before": turn, "turn_after": after["turn"],
                     "score_delta": after["score"] - before["score"],
                     "before": before, "after": after})
        prev = after; n += 1
    fin = {"tag": tag, "kind": "final", "steps": n, "score": int(s.state.score),
           "finished": bool(s.finished)}
    for r in rows:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.write(json.dumps(fin, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{tag}] score={fin['score']} steps={n}", flush=True)
    del s; gc.collect()
    return rows, fin


def main():
    master = Master.load(Path("ro/master/tables"))
    cat = MasterCatalog(Path("ro/master/tables"))
    SEED = 880001
    plain = {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0}

    def deck_of(ids):
        return [{"produce_card_id": i, "base_upgrade_count": 0} for i in ids]

    # 发现卡（打印候选，取首个单效果无触发）
    disc = {}
    for tn in ("ExamReview", "ExamReviewMultiple", "ExamLessonValueMultiple",
               "ExamStaminaConsumptionDown", "ExamCardPlayAggressive", "ExamLessonBuff",
               "StanceLock"):
        found = find_cards(cat, tn)
        mode = "single+no_trigger"
        if not found:
            found = find_cards(cat, tn, no_trigger=False); mode = "single"
        if not found:
            found = find_cards(cat, tn, single=False, no_trigger=False); mode = "multi"
        disc[tn] = found
        print(f"\n== {tn} candidates ({mode}) ==")
        for c in found[:6]:
            print("  ", c)

    def pick(tn, pref_value=None):
        cands = disc[tn]
        if not cands:
            return None
        if pref_value is not None:
            for c in cands:
                if c["value1"] == pref_value:
                    return c
        return cands[0]

    imp = pick("ExamReview")  # p_card-02-ido-1_057 imp+6
    cond_id = "p_card-01-men-2_110"  # 好调3回合 + 集中5 + 次数+1 + 睡意生成
    lock_id = "p_card-03-men-2_079"  # 切磋琢磨：fpp+2 / hold / 次数+1 / 指針固定1回合
    # G2 硬编码（含值，供配对）：
    halfcost_id = "p_card-00-men-1_005"  # 元气+2 / 体力消耗减少2回合
    scorebuff_id = "p_card-01-act-3_184"  # 打分上升量+30% 1回合（cost 元气1）+ 审查基准加成
    revmult_id = "p_card-02-ido-3_171"  # 好印象+3 / 好印象强化+50% 5回合
    aggressive_id = "p_card-02-ido-1_062"  # 干劲+4+3

    summary = {"seed": SEED, "discover": disc,
               "picked": {"imp": imp, "cond": cond_id, "lock": lock_id,
                          "halfcost": halfcost_id, "scorebuff": scorebuff_id,
                          "revmult": revmult_id, "aggressive": aggressive_id}}
    out_path = ROOT / "data" / "_m8_fresh_probe.jsonl"
    with out_path.open("w", encoding="utf-8") as out:
        # G1：卡渠道好印象重复获得（t1..t6 每回合 +6）→ 旧层/fresh 分裂衰减
        if imp:
            g1_deck = deck_of([imp["id"]] * 10)
            run(master, g1_deck, SEED,
                {t: ("play_id", imp["id"]) for t in range(1, 7)},
                "G1_card_imp_repeat", limit_turn=9, out=out)
        # G2：好调单渠道（t1 打 110 好调3回合 + 集中5）→ condition fresh + 集中永久
        g2_deck = deck_of([cond_id] * 10)
        run(master, g2_deck, SEED, {1: ("play_id", cond_id)},
            "G2_cond_fresh", limit_turn=8, out=out)
        # G3：timed 倍率层（好印象强化171 / 打分上升量184 / 体力消耗减少005）play_any
        g3_ids = [revmult_id, scorebuff_id, halfcost_id]
        g3_deck = deck_of([revmult_id] * 3 + [scorebuff_id] * 3 + [halfcost_id] * 3
                          + ["p_card-00-act-0_001"])
        run(master, g3_deck, SEED,
            {t: ("play_any", g3_ids) for t in range(1, 7)},
            "G3_timed_layers", limit_turn=9, out=out)
    sp = ROOT / "data" / "_m8_fresh_probe_summary.json"
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved:", out_path, sp, flush=True)


if __name__ == "__main__":
    main()