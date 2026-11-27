import csv, io, re, sys
sys.stdout = io.TextIOWrapper(open("data/_p15_dsl.out.txt", "wb"), encoding="utf-8")
rows = list(csv.DictReader(open("data/dl/gt/gakumas-tools-master/packages/gakumas-data/csv/p_items.csv", encoding="utf-8")))
pats = {
    "motivation-=": r"motivation\s*-=",
    "concentration-=": r"concentration\s*-=",
    "decreaseFullPowerCharge": r"decreaseFullPowerCharge",
    "goodConditionTurns+=": r"goodConditionTurns\s*\+=",
    "goodConditionTurns* (conversion)": r"goodConditionTurns\s*\*",
    "score+=goodConditionTurns": r"score\s*\+=\s*goodConditionTurns",
    "nullifyGenkiTurns": r"nullifyGenkiTurns",
    "uneaseTurns": r"uneaseTurns",
    "setGoodConditionTurnsBuff": r"setGoodConditionTurnsBuff",
    "setGoodConditionTurnsAdditionBuff": r"setGoodConditionTurnsAdditionBuff",
    "stamina-= (damage)": r"stamina\s*-=",
    "fixedStamina-=": r"fixedStamina\s*-=",
    "setFullPowerEffectBuff": r"setFullPowerEffectBuff",
    "setStrengthEffectBuff": r"setStrengthEffectBuff",
    "poorConditionTurns+=": r"poorConditionTurns\s*\+=",
    "noGoodConditionTurnsTurns": r"noGoodConditionTurnsTurns",
}
for label, pat in pats.items():
    rx = re.compile(pat)
    hits = [(r["id"], r["name"], r["effects"]) for r in rows if rx.search(r["effects"] or "")]
    print(f"\n===== {label}: {len(hits)} items =====")
    for id_, name, eff in hits[:6]:
        # show only matching fragments
        frags = [m for m in re.split(r"[{}]", eff) if rx.search(m)]
        print(f"  {id_} {name}: {' | '.join(f.strip() for f in frags[:3])[:200]}")
