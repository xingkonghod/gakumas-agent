"""M1 oracle 探针（不提交）：用我们的 DLL（rules=69）重放 rinami W7/W9 实机动作序列，
逐步记录 rng state + 牌区，与 execution.jsonl 的实机 data.rng 对比。
AGPL 引擎只作外部 oracle，不拷源码。

用法：.venv\\Scripts\\python.exe data\\_m1_rinami_oracle.py [W7|W9|all]
输出：data/_m1_rinami_oracle_<W>.json + stdout 摘要
"""
from __future__ import annotations
import gc, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["GKMS_NATIVE_LIB"] = str(ROOT / "data/_f2sl_tools/kernel/gkmscore.dll")
WHEEL = ROOT / "data/GKMSMainWheel"
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(WHEEL / "GakumasCLI")

from GakumasCLI.scenario.exam_session import Master  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402

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


def zone_ids(zone):
    out = []
    for c in zone or []:
        if isinstance(c, dict):
            out.append((c.get("produce_card_id"), int(c.get("current_upgrade_count") or 0)))
        else:
            out.append(str(c))
    return out


def snap(session):
    d = session.deck
    zones = {}
    for name in ("hand", "deck", "grave", "lost", "hold", "remove"):
        z = getattr(d, name, None)
        if z is not None:
            zones[name] = zone_ids(z)
    return {"rng": int(d.rng.state), "turn": int(session.turn),
            "score": int(session.state.score), "stamina": int(session.state.stamina),
            "playable": int(getattr(session.state, "playable", -1)),
            "finished": bool(session.finished), "zones": zones}


def run(master, w):
    d = ROOT / "data/_rinami_live" / w
    lo = json.loads((d / "gkms-loadout.json").read_text(encoding="utf-8"))
    op = json.loads((d / "opening.json").read_text(encoding="utf-8"))
    bl = json.loads((d / "battle-log.json").read_text(encoding="utf-8"))
    ex = [json.loads(l) for l in open(d / "execution.jsonl", encoding="utf-8")]
    dec = [r["data"] for r in ex if r["kind"] == "decision"]
    acts = bl["result"]["examActions"]
    seed = int(lo["seed"])
    t0 = time.perf_counter()
    session, meta = build_hif_loadout_session(master, lo, seed)
    print(f"[{w}] build {time.perf_counter()-t0:.2f}s supports={len(meta.get('eligible_supports') or [])} "
          f"permils={meta.get('effective_permils')}", flush=True)
    s0 = snap(session)
    op_rng = op["parameterScalars"]["currentRandom"]["state"]
    op_deck = [(c["id"], c["upgradeCount"]) for c in op["zones"]["deck"]]
    op_hand = [(c["id"], c["upgradeCount"]) for c in op["zones"]["hand"]]
    print(f"[{w}] opening rng engine={s0['rng']} live={op_rng} match={s0['rng']==op_rng}")
    print(f"[{w}] opening deck match={s0['zones']['deck']==op_deck} hand match={s0['zones']['hand']==op_hand}")
    if s0["zones"]["deck"] != op_deck:
        print("  engine deck:", s0["zones"]["deck"])
        print("  live   deck:", op_deck)
    rows = []
    n_match = 0
    for k, a in enumerate(acts):
        at = a["actionType"].replace("ExamActionType_", "")
        if at == "UseHand":
            action = ("play", int(a["indexes"][0]))
        elif at == "UseDrink":
            action = ("drink", int(a["indexes"][0]))
        elif at == "TurnEnd":
            action = ("end",)
        else:
            raise ValueError(at)
        before = snap(session)
        live_rng = dec[k]["rng"] if k < len(dec) else None
        match = before["rng"] == live_rng
        n_match += match
        try:
            session.step(action, observe=False)
            err = None
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        after = snap(session)
        cons = steps(before["rng"], after["rng"])
        row = {"k": k, "action": list(action), "live_i": dec[k]["i"] if k < len(dec) else None,
               "live_card": dec[k].get("card") if k < len(dec) else None,
               "live_turn": dec[k]["turn"] if k < len(dec) else None,
               "rng_before": before["rng"], "rng_after": after["rng"],
               "live_rng": live_rng, "match": match, "consumption": cons,
               "turn_before": before["turn"], "turn_after": after["turn"],
               "zones_before": before["zones"], "zones_after": after["zones"],
               "score_after": after["score"], "stamina_after": after["stamina"],
               "finished": after["finished"], "error": err}
        rows.append(row)
        zb, za = before["zones"], after["zones"]
        print(f'  k={k:>2} {str(action):<12} t{before["turn"]}->{after["turn"]} cons={cons} '
              f'rng_match={match} deck {len(zb.get("deck",[]))}->{len(za.get("deck",[]))} '
              f'grave {len(zb.get("grave",[]))}->{len(za.get("grave",[]))} '
              f'hand {len(zb.get("hand",[]))}->{len(za.get("hand",[]))} '
              f'lost {len(zb.get("lost",[]))}->{len(za.get("lost",[]))} err={err}', flush=True)
        if err:
            break
    print(f"[{w}] rng match {n_match}/{len(rows)} final score={rows[-1]['score_after'] if rows else '?'} "
          f"live={bl['result']['score']}", flush=True)
    out = {"w": w, "dll_rules": 69, "opening_rng_match": s0["rng"] == op_rng,
           "opening_deck_match": s0["zones"]["deck"] == op_deck,
           "opening_hand_match": s0["zones"]["hand"] == op_hand,
           "n_match": n_match, "n_steps": len(rows), "rows": rows}
    (ROOT / f"data/_m1_rinami_oracle_{w}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    del session
    gc.collect()


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.perf_counter()
    master = Master.load(Path("ro/master/tables"))
    print(f"Master.load {time.perf_counter()-t0:.1f}s", flush=True)
    for w in ("W7", "W9"):
        if which in (w, "all"):
            run(master, w)


if __name__ == "__main__":
    main()
