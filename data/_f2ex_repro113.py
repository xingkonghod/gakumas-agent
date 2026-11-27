"""一次性：复现 B1#113 节点数差异（选牌/期望分一致但 nodes 4384 != 4064）。不提交。"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from dataclasses import asdict, fields
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
HERE = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"

spec = importlib.util.spec_from_file_location("expectimax_algo", HERE / "algo.py")
algo = importlib.util.module_from_spec(spec)
sys.modules["expectimax_algo"] = algo
spec.loader.exec_module(algo)
from gkagent.sim import expectimax as prod  # noqa: E402
from gkagent.sim.lesson import CardSpec as ProdCardSpec  # noqa: E402

print("field order equal:", [f.name for f in fields(algo.CardSpec)] == [f.name for f in fields(ProdCardSpec)])

SPECS = json.loads((HERE / "card_specs.json").read_text(encoding="utf-8"))["cards"]
rows = list(SPECS.values())
rng = random.Random(20261125)
STANCES = [("normal", 0, 0, 0), ("save", 0, 1, 0), ("save", 0, 2, 3),
           ("strong1", 1, 0, 0), ("strong2", 2, 0, 5), ("full", 0, 0, 12),
           ("leisure", 0, 0, 0)]


def spec_pair(row):
    kwargs = {f.name: row[f.name] for f in fields(ProdCardSpec) if f.name in row}
    return algo.CardSpec(**kwargs), ProdCardSpec(**kwargs)


def rand_cards(n):
    picks = [rng.choice(rows) for _ in range(n)]
    return tuple(spec_pair(r)[0] for r in picks), tuple(spec_pair(r)[1] for r in picks)


def rand_state():
    hand_e, hand_p = rand_cards(rng.randint(1, 4))
    deck_e, deck_p = rand_cards(rng.randint(0, 8))
    disc_e, disc_p = rand_cards(rng.randint(0, 5))
    excl_e, excl_p = rand_cards(rng.randint(0, 2))
    held_e, held_p = rand_cards(rng.randint(0, 2))
    kw = dict(
        stamina=rng.randint(0, 40), stamina_max=rng.randint(20, 60),
        vitality=rng.randint(0, 15), score=rng.randint(0, 50000),
        turns_left=rng.randint(1, 5), total_turns=rng.randint(5, 9),
        plays_used=rng.randint(0, 1), play_limit=1, extra_plays=rng.randint(0, 2),
        clear=rng.choice([0, 0, 1000, 5000]), perfect=0,
        condition_turns=rng.randint(0, 4), perfect_condition_turns=rng.randint(0, 2),
        poor_condition_turns=rng.randint(0, 2),
        focus=rng.randint(0, 12), impression=rng.randint(0, 10),
        motivation=rng.randint(0, 10),
        condition_additive=rng.randint(0, 3), condition_additive_turns=rng.randint(0, 3),
        review_multiple=rng.choice([0, 500, 2000]), review_multiple_turns=rng.choice([0, 1, -1]),
        full_power_lesson_multiple=rng.choice([0, 100, 500]),
        full_power_lesson_multiple_turns=rng.choice([0, 1, -1]),
        parameter_buff=rng.choice([0, 1500]),
        stance=rng.choice(STANCES),
        enthusiasm=rng.randint(0, 8), enthusiasm_extension_turns=rng.randint(0, 2),
        enthusiasm_bonus=rng.randint(0, 3), enthusiasm_bonus_turns=rng.choice([0, 1, -1]),
        enthusiasm_multiple=rng.choice([0, 1000]), enthusiasm_multiple_turns=rng.choice([0, 1]),
        attribute_coefficient=rng.choice([1.0, 2.07, 6.44, 38.66]),
        hand_size=3, min_cost=rng.randint(0, 3), cards_played_total=rng.randint(0, 20),
        score_growth_all=rng.choice([0, 10]),
        pride_turns=rng.randint(0, 3),
        lock_stance_turns=rng.randint(0, 2), lock_stance_fresh=rng.choice([False, True]),
        nullify_debuff=rng.randint(0, 2), nullify_genki_turns=rng.randint(0, 2),
        unease_turns=rng.randint(0, 2),
        cost_reduction=rng.randint(0, 2), cost_increase=rng.randint(0, 2),
        half_cost_turns=rng.randint(0, 2), double_cost_turns=rng.randint(0, 2),
        extra_turns=rng.randint(0, 1), extra_turns_granted=rng.randint(0, 2),
        score_buffs=rng.choice([(), ((500, 2),), ((1000, -1),)]),
        score_debuffs=rng.choice([(), ((300, 1),)]),
        hand_decreases=rng.choice([(), ((1, 2),)]),
        modifiers=rng.choice([(), (("review_times", ((1, -1),)),),
                              (("concentration_effect", ((500, 2),)),)]),
        leisure_reserves=rng.choice([(), ((-1, True),), ((3, False),)]),
        p_items=(), drinks=(), known_draw=(), discard_order=None,
    )
    se = algo.ExpectState(hand=hand_e, deck=deck_e, discard=disc_e, excluded=excl_e, held=held_e, **kw)
    sp = prod.ExpectState(hand=hand_p, deck=deck_p, discard=disc_p, excluded=excl_p, held=held_p, **kw)
    return se, sp, kw


target = None
for i in range(150):
    se, sp, kw = rand_state()
    if i == 113:
        target = (se, sp, kw)
        break

se, sp, kw = target
re_ = algo.expectimax_with_stats(se, algo.AnalyticLeafValue(sigma=80.0), time_budget_ms=None, max_nodes=20000, allow_drinks=False)
rp_ = prod.expectimax_with_stats(sp, prod.AnalyticLeafValue(sigma=80.0), time_budget_ms=None, max_nodes=20000, allow_drinks=False)
print("nodes:", re_.nodes, rp_.nodes, "utility:", re_.utility, rp_.utility, "complete:", re_.complete, rp_.complete)


def direct(mod, state, label):
    cfg = mod.ExpectimaxConfig(time_budget_ms=None, max_nodes=20000, allow_drinks=False)
    s = mod._Search(mod.AnalyticLeafValue(sigma=80.0), cfg, clock=__import__("time").perf_counter, deadline=None)
    try:
        s.root(state)
    except mod._Deadline:
        pass
    print(f"  direct {label}: nodes={s.nodes} memo={len(s.memo)} aborted={s.aborted}")


direct(algo, se, "ext in-memory")
direct(prod, sp, "prod in-memory")
direct(algo, se, "ext in-memory again")
direct(prod, sp, "prod in-memory again")
print("card equal:", (asdict(re_.card) if re_.card else None) == (asdict(rp_.card) if rp_.card else None))
print("actions equal:", re_.actions == rp_.actions)

# canonical 键一致性
print("canonical equal:", se.canonical() == sp.canonical())
# legal_cards 顺序
le = algo.legal_cards(se)
lp = prod.legal_cards(sp)
print("legal order equal:", [asdict(c) for c in le] == [asdict(c) for c in lp])
# apply_card 分布顺序
for ce, cp in zip(le, lp):
    oe = algo.apply_card(se, ce)
    op = prod.apply_card(sp, cp)
    same_probs = [p for p, _ in oe] == [p for p, _ in op]
    same_states = all(s1.canonical() == s2.canonical() for (_, s1), (_, s2) in zip(oe, op))
    print(f"  card {ce.name}: branches {len(oe)}/{len(op)} probs_order={same_probs} states_order={same_states}")
    if not same_states:
        for j, ((_, s1), (_, s2)) in enumerate(zip(oe, op)):
            if s1.canonical() != s2.canonical():
                d1, d2 = asdict(s1), asdict(s2)
                diff = {k for k in d1 if d1[k] != d2[k]}
                print(f"    branch {j} diff fields: {diff}")
                for k in list(diff)[:5]:
                    print(f"      {k}: {d1[k]!r} vs {d2[k]!r}")
                break
# 保存状态供后续
Path(r"D:\Games\gakumas-agent\data\_f2ex_state113.json").write_text(
    json.dumps({"kw": {k: (list(v) if isinstance(v, tuple) else v) for k, v in kw.items()},
                "hand": [asdict(c) for c in se.hand], "deck": [asdict(c) for c in se.deck],
                "discard": [asdict(c) for c in se.discard], "excluded": [asdict(c) for c in se.excluded],
                "held": [asdict(c) for c in se.held]}, ensure_ascii=False, default=str), encoding="utf-8")
print("saved _f2ex_state113.json")
