"""m1-fix3 (c)② 探针（不提交）：pitem 312 interval 抽牌 fire 口径。

重放 rinami W7/W9 实机动作（同 _m1_rinami_oracle.py 口径），逐步额外捕获 DLL
trigger_effect_states（interval44_count / limit_count / spent_total / remaining_turns）
+ stance/stance_step（好调）+ 手牌上限，刻画 interval=4 抽牌的 fire 规则与计数器复位/跳过交互。
AGPL 引擎只作 oracle，不拷源码、不重编 DLL。

用法：.venv\\Scripts\\python.exe data\\_m1b_pitem312.py [W7|W9|all]
输出：data/_m1b_pitem312_<W>.jsonl + data/_m1b_pitem312_summary.json
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
PITEM_DRAW = {"W7": [9, 15, 20], "W9": [11, 15, 21, 28, 34]}


def xs(s):
    s ^= (s << 13) & MASK; s ^= s >> 17; s ^= (s << 5) & MASK
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


def tes_lite(session):
    """trigger_effect_states 精简：只留 interval/limit/spent/remaining 等计数字段。"""
    out = []
    for t in getattr(session.state, "trigger_effect_states", []) or []:
        if not isinstance(t, dict):
            continue
        rec = {k: t.get(k) for k in ("enchant_id", "origin", "trigger", "remaining_turns",
                                     "installed_play_count", "limit_count", "limit_count_in_turn",
                                     "spent_total", "spent_in_turn", "phase_count",
                                     "interval44_count", "interval53_count", "interval52_count",
                                     "passing_turn_start", "skip_play_count_once", "skip_card_played_once")
               if t.get(k) is not None}
        out.append(rec)
    return out


def snap(session):
    d = session.deck
    zones = {name: zone_ids(getattr(d, name, None)) for name in ("hand", "deck", "grave", "lost", "hold")}
    obs = session.observe()
    return {"rng": int(d.rng.state), "turn": int(session.turn), "zones": zones,
            "stance": obs.get("stance"), "stance_step": obs.get("stance_step"),
            "review": obs.get("review"), "lesson_buff": obs.get("lesson_buff"),
            "aggressive": obs.get("aggressive"), "hand_n": len(zones["hand"]),
            "deck_n": len(zones["deck"]), "grave_n": len(zones["grave"]),
            "tes": tes_lite(session)}


def run(master, w, out):
    d = ROOT / "data/_rinami_live" / w
    lo = json.loads((d / "gkms-loadout.json").read_text(encoding="utf-8"))
    bl = json.loads((d / "battle-log.json").read_text(encoding="utf-8"))
    acts = bl["result"]["examActions"]
    seed = int(lo["seed"])
    t0 = time.perf_counter()
    session, meta = build_hif_loadout_session(master, lo, seed)
    print(f"[{w}] build {time.perf_counter()-t0:.2f}s pitems={lo.get('p_item_ids') or lo.get('pitem_ids')}", flush=True)
    rows = []
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
        played = None
        if action[0] == "play":
            h = session.deck.hand
            if action[1] < len(h):
                played = h[action[1]].get("produce_card_id")
        try:
            session.step(action, observe=False); err = None
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        after = snap(session)
        cons = steps(before["rng"], after["rng"])
        # interval44 计数器变化（任意 enchant）
        i44_b = {t.get("enchant_id"): t.get("interval44_count") for t in before["tes"] if t.get("interval44_count") is not None}
        i44_a = {t.get("enchant_id"): t.get("interval44_count") for t in after["tes"] if t.get("interval44_count") is not None}
        row = {"w": w, "k": k, "action": list(action), "played": played,
               "pitem_fire_anchor": k in PITEM_DRAW[w],
               "rng_before": before["rng"], "rng_after": after["rng"], "consumption": cons,
               "turn_before": before["turn"], "turn_after": after["turn"],
               "stance_before": before["stance"], "stance_step_before": before["stance_step"],
               "stance_after": after["stance"], "stance_step_after": after["stance_step"],
               "hand_n_before": before["hand_n"], "hand_n_after": after["hand_n"],
               "deck_n_before": before["deck_n"], "deck_n_after": after["deck_n"],
               "grave_n_before": before["grave_n"], "grave_n_after": after["grave_n"],
               "i44_before": i44_b, "i44_after": i44_a,
               "tes_before": before["tes"], "tes_after": after["tes"],
               "zones_after": after["zones"], "error": err}
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        rows.append(row)
        delta = {e: (i44_b.get(e), i44_a.get(e)) for e in set(i44_b) | set(i44_a) if i44_b.get(e) != i44_a.get(e)}
        print(f"  k={k:>2} {str(action):<12} t{before['turn']}->{after['turn']} cons={cons} "
              f"hand {before['hand_n']}->{after['hand_n']} stance={before['stance']}/{before['stance_step']} "
              f"i44Δ={delta} anchor={row['pitem_fire_anchor']} err={err}", flush=True)
        if err:
            break
    del session; gc.collect()
    return rows


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.perf_counter()
    master = Master.load(Path("ro/master/tables"))
    print(f"Master.load {time.perf_counter()-t0:.1f}s", flush=True)
    summary = {}
    for w in ("W7", "W9"):
        if which not in (w, "all"):
            continue
        op = ROOT / f"data/_m1b_pitem312_{w}.jsonl"
        with op.open("w", encoding="utf-8") as out:
            rows = run(master, w, out)
        summary[w] = {"n": len(rows), "anchors": PITEM_DRAW[w],
                      "fire_rows": [r["k"] for r in rows if r["pitem_fire_anchor"]]}
        print(f"[{w}] saved {op}", flush=True)
    (ROOT / "data/_m1b_pitem312_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()