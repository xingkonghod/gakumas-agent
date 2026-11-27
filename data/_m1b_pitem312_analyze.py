"""m1-fix3 (c)② 分析（不提交）：从 _m1b_pitem312_<W>.jsonl 提取 pitem312 enchant 计数器轨迹，
刻画 interval=4 抽牌 fire 规则。关键发现：rules=69 下 interval44_count 未填充（has_interval44=False），
实际计数器是 phase_count；trigger=exam_play_count_interval-4-...-effect_group-visible-exam_parameter_buff。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ENC = "enchant-p_item_effect_01-3-312-0-enc01"


def find(tes):
    for t in tes:
        if t.get("enchant_id") == ENC:
            return t
    return {}


def analyze(w):
    rows = [json.loads(l) for l in open(ROOT / f"data/_m1b_pitem312_{w}.jsonl", encoding="utf-8")]
    print(f"\n=== {w} ===  k action played | phase(b->a) spent(b->a) | hand(b->a) deck(b->a) | fire? anchor?")
    fires = []
    increments = []
    for r in rows:
        b, a = find(r["tes_before"]), find(r["tes_after"])
        pb, pa = b.get("phase_count", 0), a.get("phase_count", 0)
        sb, sa = b.get("spent_total", 0), a.get("spent_total", 0)
        fired = sa > sb
        inc = pa > pb
        if fired:
            fires.append((r["k"], r["played"], pb, pa, sb, sa, r["hand_n_before"], r["hand_n_after"]))
        if inc:
            increments.append((r["k"], r["played"], pb, pa))
        mark = ("FIRE" if fired else "") + ("*" if r["pitem_fire_anchor"] else "")
        print(f"  k={r['k']:>2} {str(r['action']):<11} {str(r['played']):<26} "
              f"phase {pb}->{pa} spent {sb}->{sa} hand {r['hand_n_before']}->{r['hand_n_after']} "
              f"deck {r['deck_n_before']}->{r['deck_n_after']} {mark}")
    print(f"  fires (k, played, phase_b->a, spent_b->a, hand_b->a): {fires}")
    print(f"  phase increments (k, played, pb->pa): {increments}")
    # 假设检验：fire 当 phase_after % 4 == 0 且 spent < limit(5)
    ok = all(pa % 4 == 0 for (_k, _p, _pb, pa, _sb, _sa, _hb, _ha) in fires)
    print(f"  H1 fire⇒phase_after%4==0: {ok}")
    # qualifying play = phase 增量；列出哪些卡增量（effect_group 过滤）
    qual_cards = sorted({p for (_k, p, _pb, _pa) in increments})
    nonqual = sorted({r["played"] for r in rows if r["played"] and r["played"] not in qual_cards})
    print(f"  qualifying cards (phase++): {qual_cards}")
    print(f"  non-qualifying cards: {nonqual}")
    return {"w": w, "fires": fires, "increments": increments, "H1": ok,
            "qual_cards": qual_cards, "nonqual": nonqual}


def main():
    out = {}
    for w in ("W7", "W9"):
        if (ROOT / f"data/_m1b_pitem312_{w}.jsonl").exists():
            out[w] = analyze(w)
    (ROOT / "data/_m1b_pitem312_analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved data/_m1b_pitem312_analysis.json")


if __name__ == "__main__":
    main()