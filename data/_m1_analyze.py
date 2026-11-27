"""M1 阶段1 分析（不提交）：探针①紧凑视图 + rinami rng 步数 + 主数据效果 oracle 抽取。

用法：.venv\\Scripts\\python.exe data\\_m1_analyze.py [part]
part: probe | rinami | master | all（默认 all）
输出：stdout + data/_m1_effects_dump.json（master 部分）
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MASK = 0xFFFFFFFF


def xs(s):
    s ^= (s << 13) & MASK
    s ^= s >> 17
    s ^= (s << 5) & MASK
    return s & MASK


def steps(before, after, cap=200000):
    if before == after:
        return 0
    s = before
    for i in range(1, cap + 1):
        s = xs(s)
        if s == after:
            return i
    return None


def part_probe():
    rows = [json.loads(l) for l in open(ROOT / "data/_engine_probe_rng_p1.jsonl", encoding="utf-8")]
    print("=== probe p1 compact steps ===")
    for r in rows:
        if r["kind"] != "step":
            continue
        ob, oa = r["obs_before"], r["obs_after"]
        ins = [(x["index"], x["card"]) for x in r.get("deck_inserted", [])]
        tr_b = ob.get("trouble_states")
        tr_a = oa.get("trouble_states")
        print(f'{r["tag"]} i={r["i"]} t{ob["turn"]}->{oa["turn"]} act={r["action"]} played={r["played"]} '
              f'mech={r["played_mech"]} cons={r["consumption"]} '
              f'deck {r["deck_len_before"]}->{r["deck_len_after"]} grave {ob["grave_count"]}->{oa["grave_count"]} '
              f'hand {len(r["hand_before"])}->{len(r["hand_after"])} ins={ins} '
              f'trouble {tr_b}->{tr_a} order_chg={r["deck_order_changed"]}')
        if r.get("insert_pred"):
            for p in r["insert_pred"]:
                if p["pred_steps"]:
                    print(f'    insert_pred {p["card"]}@{p["index"]} steps={p["pred_steps"]}')


def part_rinami():
    for w in ("W7", "W9"):
        d = ROOT / "data/_rinami_live" / w
        op = json.loads((d / "opening.json").read_text(encoding="utf-8"))
        ex = [json.loads(l) for l in open(d / "execution.jsonl", encoding="utf-8")]
        dec = [r for r in ex if r["kind"] == "decision"]
        print(f"=== rinami {w}: opening state={op['parameterScalars']['currentRandom']['state']} "
              f"seed={op['parameterScalars']['values']['Seed']} turns={op['parameterScalars']['values']['LimitTurn']} "
              f"deck={len(op['zones']['deck'])} hand={len(op['zones']['hand'])} ===")
        prev = op["parameterScalars"]["currentRandom"]["state"]
        prev_label = "open"
        for r in dec:
            dd = r["data"]
            n = steps(prev, dd["rng"])
            print(f'  i={dd["i"]:>2} t{dd["turn"]} {dd["action"]:<12} {dd.get("card",""):<28} '
                  f'rng={dd["rng"]} steps_from_{prev_label}={n}')
            prev = dd["rng"]
            prev_label = f'i{dd["i"]}'
        # 非决策行（auto-confirm 等）
        for r in ex:
            if r["kind"] != "decision":
                print(f'  [auto] i={r["data"].get("i")} kind={r["kind"]} {r["data"].get("name") or r["data"].get("id")}')


def part_master():
    os.environ["GKMS_NATIVE_LIB"] = str(ROOT / "data/_f2sl_tools/kernel/gkmscore.dll")
    WHEEL = ROOT / "data/GKMSMainWheel"
    sys.path.insert(0, str(WHEEL))
    sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
    os.chdir(WHEEL / "GakumasCLI")
    from GakumasCLI.scenario.exam_session import Master
    master = Master.load(Path("ro/master/tables"))
    print("Master attrs:", [a for a in dir(master) if not a.startswith("_")])
    enums = json.loads((WHEEL / "GakumasCLI/engine/data/exam_enums.json").read_text(encoding="utf-8"))
    etype = {int(k): v for k, v in enums.get("ProduceExamEffectType", {}).items()}

    rinami_cards = set()
    for w in ("W7", "W9"):
        op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
        for z in ("hand", "deck", "grave", "hold"):
            for c in op["zones"].get(z) or []:
                rinami_cards.add(c["id"])
        lo = json.loads((ROOT / f"data/_rinami_live/{w}/gkms-loadout.json").read_text(encoding="utf-8"))
        for c in lo["deck_cards"]:
            rinami_cards.add(c["produce_card_id"])
    probe_cards = ["p_card-01-men-2_099", "p_card-01-men-2_098", "p_card-03-men-2_103",
                   "p_card-01-men-2_110", "p_card-03-act-2_102", "p_card-01-men-3_034",
                   "p_card-03-men-2_064", "p_card-03-act-3_065", "p_card-00-sup-3_158",
                   "p_card-01-men-3_006", "p_card-03-ido-100_042", "p_card-03-act-2_082",
                   "p_card-03-ido-3_238", "p_card-03-men-3_063", "p_card-03-men-2_112",
                   "p_card-00-acc-0_002"]
    dump = {"cards": {}, "effects": {}, "searches": {}, "supports": {}, "drinks": {}, "enchants": {}}

    def eff_row(eid):
        if eid in dump["effects"]:
            return
        eff = master.effects.get(eid, {})
        t = eff.get("effectType") or {}
        tn = t.get("number") if isinstance(t, dict) else t
        row = dict(eff)
        row["_type_name"] = etype.get(int(tn), "?") if tn is not None else "?"
        dump["effects"][eid] = row
        sid = eff.get("produceCardSearchId")
        if sid and sid not in dump["searches"]:
            dump["searches"][sid] = master.searches.get(sid, {}) if hasattr(master, "searches") else {}

    for cid in sorted(rinami_cards | set(probe_cards)):
        for up in (0, 1, 2, 3):
            row = master.cards.get((cid, up))
            if not row:
                continue
            key = f"{cid}::{up}"
            dump["cards"][key] = {"name": row.get("name"), "playEffects": row.get("playEffects"),
                                  "cost": row.get("cost"), "keys": sorted(row.keys())}
            print(f"--- {key} name={row.get('name')}")
            for link in row.get("playEffects", []) or []:
                eid = link.get("produceExamEffectId")
                eff_row(eid)
                e = dump["effects"][eid]
                print(f'    {eid} type={e.get("effectType")}({e["_type_name"]}) v1={e.get("effectValue1")} '
                      f'v2={e.get("effectValue2")} search={e.get("produceCardSearchId")} '
                      f'move={e.get("movePositionType")} pick={e.get("pickCountType")},{e.get("pickMin")},{e.get("pickMax")}')

    # 支援卡 filter
    sup_ids = ["s_card-2-0007", "s_card-3-0030", "s_card-3-0070", "s_card-3-0025", "s_card-3-0064", "s_card-3-0069"]
    for sid in sup_ids:
        row = None
        for attr in ("supports", "support_cards"):
            tbl = getattr(master, attr, None)
            if tbl is not None:
                row = tbl.get(sid)
                break
        dump["supports"][sid] = row
        print(f"--- support {sid}: {json.dumps(row, ensure_ascii=False)[:400] if row else 'NOT FOUND'}")

    # 饮料
    for did in ("pdrink_00-2-010", "pdrink_00-3-001", "pdrink_00-2-009"):
        row = None
        for attr in ("drinks", "produce_drinks"):
            tbl = getattr(master, attr, None)
            if tbl is not None:
                row = tbl.get(did)
                break
        dump["drinks"][did] = row
        print(f"--- drink {did}: {json.dumps(row, ensure_ascii=False)[:600] if row else 'NOT FOUND'}")
        if isinstance(row, dict):
            for k, v in row.items():
                if isinstance(v, str) and v.startswith("e_effect"):
                    eff_row(v)

    # H.I.F memory enchant + pitem enchant 效果
    enc_ids = ["enchant-p_ef-hif_memory-p_card-01-act-2_001-enc01",
               "enchant-p_ef-hif_memory-p_card-01-men-1_034-enc01",
               "enchant-p_ef-hif_memory-p_card-01-men-2_043-enc01",
               "enchant-p_item_effect_01-3-312-0-enc01",
               "enchant-p_item_effect_01-3-136-0-enc01"]
    for enc in enc_ids:
        row = None
        tbl = getattr(master, "enchants", None) or getattr(master, "status_enchants", None)
        if tbl is not None:
            row = tbl.get(enc)
        dump["enchants"][enc] = row
        print(f"--- enchant {enc}: {json.dumps(row, ensure_ascii=False)[:500] if row else 'NOT FOUND'}")

    # 直接按 id 找关键 effect（move/create/panic/drink 相关）
    for eid in list(dump["effects"]):
        pass
    interesting = [eid for eid in master.effects if any(
        s in eid for s in ("exam_card_move-p_card_search-deck_grave-p_card-00-acc-0_002",
                           "exam_card_create", "panic", "drink"))]
    print(f"--- interesting effect ids ({len(interesting)}):")
    for eid in sorted(interesting)[:80]:
        eff_row(eid)
        e = dump["effects"][eid]
        print(f'    {eid} type={e.get("effectType")}({e["_type_name"]}) v1={e.get("effectValue1")} v2={e.get("effectValue2")} '
              f'search={e.get("produceCardSearchId")} move={e.get("movePositionType")} pick={e.get("pickCountType")},{e.get("pickMin")},{e.get("pickMax")}')

    out = ROOT / "data/_m1_effects_dump.json"
    out.write_text(json.dumps(dump, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("saved:", out)


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    if part in ("probe", "all"):
        part_probe()
    if part in ("rinami", "all"):
        part_rinami()
    if part in ("master", "all"):
        part_master()
