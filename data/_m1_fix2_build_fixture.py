"""m1-fix2 fixture 生成（不提交脚本，产出 tests/fixtures/m1_rinami_predictive.json 提交）。

从 oracle/live/loadout/card_table 抽取黄金 zones/rng/cons + loadout + 主数据卡效果规格
+ 显式 unknown 锚点（pitem 312 抽牌时机 / 饮料侧 soda 支援强化）。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.data.card_meta import card_meta_index

idx = card_meta_index()
ct = json.loads((ROOT / "data/knowledge/card_table.json").read_text(encoding="utf-8"))["cards"]
drinks = json.loads((ROOT / "data/knowledge/drinks.json").read_text(encoding="utf-8"))
drows = drinks.get("drinks") or drinks
if isinstance(drows, dict):
    drows = list(drows.values())
drink_by_id = {r["id"]: r for r in drows}

GRAVE_CARDS = ["p_card-01-men-2_037", "p_card-01-act-2_001", "p_card-01-men-2_011"]
SSR = ["p_card-00-men-3_003", "p_card-01-men-3_036", "p_card-00-men-3_012",
       "p_card-01-men-3_034", "p_card-01-ido-3_213", "p_card-01-men-3_006",
       "p_card-01-men-3_035", "p_card-01-act-3_049", "p_card-01-men-3_033",
       "p_card-01-ido-3_200", "p_card-01-act-3_010"]
# unknown 锚点（如实记录）：pitem 312 interval 抽牌时机（DLL 内部计数器+手牌上限交互，
# 两局样本不足以可靠反推 → 显式 unknown，留 (c) 探针）；饮料侧 soda 支援强化（独立饮料 rng）。
PITEM_DRAW = {"W7": [9, 15, 20], "W9": [11, 15, 21, 28, 34]}
DRINK_UPG = {"W7": {}, "W9": {"7": {"p_card-01-men-3_035": 1}}}


def card_effect_spec(pid):
    """从 card_table 抽一张卡的牌区相关效果规格（主数据驱动）。"""
    for upg in (0, 1, 2, 3):
        nm = idx.name_of(pid, upg)
        if nm and nm in ct:
            effs = ct[nm].get("effects", [])
            return [{"type": e.get("type"), "values": e.get("values") or {}} for e in effs]
    return []


def zones_sorted(z):
    return sorted([list(c) for c in z])


def opening_pairs(z):
    out = []
    for c in z or []:
        if isinstance(c, dict):
            out.append([c["id"], int(c.get("upgradeCount") or 0)])
        else:
            out.append(list(c))
    return out  # 保留原始顺序（hand play idx / deck 抽牌序依赖顺序）


out = {}
for w in ("W7", "W9"):
    op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
    lo = json.loads((ROOT / f"data/_rinami_live/{w}/gkms-loadout.json").read_text(encoding="utf-8"))
    oracle = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
    base_upg = {c["produce_card_id"]: int(c.get("current_upgrade_count") or 0) for c in lo["deck_cards"]}
    base_upg["p_card-00-acc-0_002"] = 0
    supports = [{"id": s["support_card_id"], "permil": s["permil"]} for s in lo["support_cards"]]
    # filter 从主数据支援卡（card_table 无支援 filter；用 dev probe 已验证口径）
    filt = {"s_card-2-0007": 2, "s_card-3-0030": 2, "s_card-3-0070": 2,
            "s_card-3-0025": 3, "s_card-3-0064": 3, "s_card-3-0069": 2}
    for s in supports:
        s["filter"] = filt.get(s["id"], 0)
    max_upg = {pid: (0 if pid == "p_card-00-acc-0_002" else 3) for pid in base_upg}
    played = sorted({r["live_card"].split("::")[0] for r in oracle["rows"] if r["live_card"]})
    card_effects = {pid: card_effect_spec(pid) for pid in played}
    actions = []
    for r in oracle["rows"]:
        actions.append({
            "k": r["k"], "action": r["action"], "turn_before": r["turn_before"],
            "turn_after": r["turn_after"], "live_rng": r["live_rng"],
            "oracle_cons": r["consumption"], "is_drink": r["action"][0] == "drink",
            "live_card": r["live_card"],
            "zones_after": {zn: zones_sorted(r["zones_after"].get(zn, [])) for zn in ("hand", "deck", "grave", "lost")},
        })
    out[w] = {
        "opening_rng": op["parameterScalars"]["currentRandom"]["state"],
        "opening_zones": {zn: opening_pairs(op["zones"].get(zn, [])) for zn in ("hand", "deck", "grave", "lost")},
        "turn_attrs": op["turnAttributes"],
        "supports": supports, "base_upg": base_upg, "max_upg": max_upg,
        "grave_cards": GRAVE_CARDS, "ssr": SSR, "drinks": lo["drink_ids"],
        "card_effects": card_effects,
        "pitem_draw_unknown": PITEM_DRAW[w], "drink_upg_unknown": DRINK_UPG[w],
        "actions": actions,
    }
dest = ROOT / "tests/fixtures/m1_rinami_predictive.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", dest, dest.stat().st_size, "bytes")