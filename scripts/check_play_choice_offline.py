"""离线验收：PIMC 真搜索（采样未知牌序 × K 次 rollout，K 有边际收益）。

用法（venv，任何 cwd）：
    .venv\\Scripts\\python.exe scripts\\check_play_choice_offline.py

手牌来自 lead 的最终审查（ep-aud3）：
  在我发现的世界（cost 4，纯 buff）/ 试行错误+（84 分 / 5 费）/ 轻快步伐（25 分 / 4 费）。
卡片数值走真实 ``data/knowledge/card_table.json``（cost/效果），屏幕宝石分数优先。

**PIMC 需要未知牌序**：真机看不到完整牌库，验收用「已知手牌 + 基础牌组」近似：
基础牌组来自 ``scripts/sim_produce.py`` 的 14 张真实基础牌，和当前手牌合并后
扣掉手上那 3 张、截到 ``MAX_APPROX_DECK=12`` 张当 rollout 牌库。每次 rollout 用
``seed + episode * 7919`` 重洗这 12 张（只改顺序），K 次平均 = PIMC 期望分。

输出：
  1. K=1/2/4/8/16/32 的单次期望分 ± K 次样本标准差、跨 seed 估计均值 ± 标准差；
  2. 饱和点（单 seed 期望与 K=32 差 ≤2 分，且跨 seed 标准差 ≤2.5 分）；
  3. 最终选择 vs 规则 ``LessonPolicy`` 的对比日志。
退出码 0 = 所有能打出的牌都算出期望分且能给出选择。
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_produce as sp

from gkagent.data.card_table import CardTable
from gkagent.policy.lesson import LessonPolicy
from gkagent.sim.lesson import CardSpec
from gkagent.sim.play_choice import (
    MAX_APPROX_DECK,
    approx_deck,
    choose_card_via_sim,
    estimate_hand,
    specs_from_hand,
)
from gkagent.vision.lesson import LessonCard, LessonState

TURNS_LEFT = 3
# 真机审查那回合体力吃紧：只够打一张大牌（84/5 与 25/4 不能同时打）
STAMINA = 8
EPISODES = 8
KS = (1, 2, 4, 8, 16, 32)
# 跨多少个基础 seed 重复整次决策，用来量估计器稳定性（K 越大标准差应越小）
STABILITY_SEEDS = 24
TIME_BUDGET_MS = 100_000  # 离线验收不让 anytime 截断
# 饱和判据：单 seed 期望离 K=32（最大预算）≤2 分，且跨 seed 标准差 ≤2.5 分
SATURATION_TOL = 2.0
SATURATION_SD = 2.5
BAR_WIDTH = 44


def _card(
    index: int,
    name: str,
    *,
    cost: int,
    score: int | None = None,
    hits: int | None = None,
) -> LessonCard:
    return LessonCard(
        index=index,
        box=(40 + index * 200, 890, 180, 220),
        point=(140 + index * 200, 1000),
        name=name,
        score=score,
        hits=hits,
        cost=cost,
    )


HAND = [
    _card(0, "在我发现的世界", cost=4),
    _card(1, "试行错误+", cost=5, score=42, hits=2),
    _card(2, "轻快步伐", cost=4, score=25, hits=1),
]


def _base_deck() -> list[CardSpec]:
    """近似牌库：真实基础牌组（``sim_produce.build_deck``，与训练模拟器同源）。"""
    return [
        CardSpec(name=name, cost=cost, score=score, condition=condition, focus=focus)
        for name, cost, score, condition, focus in sp.build_deck()
    ]


def _stability(hand, deck, table, k: int) -> tuple[float, float]:
    """换 ``STABILITY_SEEDS`` 个基础 seed 重跑同一决策，返回最佳期望的均值/标准差。"""
    bests = []
    for seed in range(STABILITY_SEEDS):
        estimates = estimate_hand(
            hand,
            turns_left=TURNS_LEFT,
            stamina=STAMINA,
            deck=deck,
            episodes=k,
            time_budget_ms=TIME_BUDGET_MS,
            table=table,
            seed=seed,
        )
        bests.append(max((item.expected for item in estimates), default=0.0))
    return statistics.fmean(bests), statistics.pstdev(bests)


def _sweep(hand, deck, table) -> list[dict]:
    print(f"\nK 扫描（seed=0，预算 {TIME_BUDGET_MS}ms，跨 {STABILITY_SEEDS} 个 seed 量稳定性）")
    rows: list[dict] = []
    for k in KS:
        started = time.perf_counter()
        estimates = estimate_hand(
            hand,
            turns_left=TURNS_LEFT,
            stamina=STAMINA,
            deck=deck,
            episodes=k,
            time_budget_ms=TIME_BUDGET_MS,
            table=table,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not estimates:
            print(f"  K={k:2d} FAIL：一张牌都没算出期望分")
            return []
        best = max(estimates, key=lambda item: (item.expected, item.score, -item.index))
        est_mean, est_sd = _stability(hand, deck, table, k)
        row = {
            "k": k,
            "expected": best.expected,
            "stdev": best.stdev,
            "estimates": estimates,
            "est_mean": est_mean,
            "est_sd": est_sd,
            "ms": elapsed_ms,
        }
        rows.append(row)
        per_card = " | ".join(
            f"[{item.index}] {item.expected:.1f}±{item.stdev:.1f} (K={item.episodes})"
            for item in estimates
        )
        print(
            f"  K={k:2d} 最佳 {best.name} {best.expected:.1f}±{best.stdev:.1f} | "
            f"跨seed 最佳 {est_mean:.1f}±{est_sd:.1f} | {elapsed_ms:.2f}ms\n"
            f"        {per_card}"
        )
    return rows


def _report_saturation(rows: list[dict]) -> None:
    reference = rows[-1]["expected"]
    saturation = next(
        (
            row
            for row in rows
            if abs(row["expected"] - reference) <= SATURATION_TOL
            and row["est_sd"] <= SATURATION_SD
        ),
        None,
    )
    lo = min(row["expected"] for row in rows)
    hi = max(row["expected"] for row in rows)
    span = max(hi - lo, 1.0)
    print(
        f"\n饱和曲线（单 seed 期望；| = 跨 seed 估计均值，误差 ±{SATURATION_SD:.1f} 分内算饱和）："
    )
    for row in rows:
        width = max(round((row["expected"] - lo) / span * (BAR_WIDTH - 1)), 0)
        mean_pos = round((row["est_mean"] - lo) / span * (BAR_WIDTH - 1))
        mean_pos = min(max(mean_pos, 0), BAR_WIDTH - 1)
        bar = ["."] * BAR_WIDTH
        for index in range(width + 1):
            bar[index] = "#"
        bar[mean_pos] = "|"
        mark = "  <- 饱和点" if saturation is not None and row["k"] == saturation["k"] else ""
        print(f"  K={row['k']:2d} {row['expected']:6.1f} [{''.join(bar)}]{mark}")
    if saturation is None:
        print(
            f"  未饱和：没有 K 同时满足 |期望-K32|<= {SATURATION_TOL:.1f} "
            f"且跨 seed 标准差<= {SATURATION_SD:.1f}（K=32 期望 {reference:.1f}）"
        )
    else:
        row = saturation
        print(
            f"  饱和点 K={row['k']}：期望 {row['expected']:.1f}，距 K=32 {reference:.1f} "
            f"差 {abs(row['expected'] - reference):.1f} 分；跨 seed 标准差 "
            f"{row['est_sd']:.2f}（K=1 时 {rows[0]['est_sd']:.2f}）"
        )
    print(
        "  说明：PIMC 期望本身无偏，K 的收益是**估计方差**变小；单 seed 曲线会围绕"
        "跨 seed 均值波动，K 越大波动越小。"
    )


def _report_pick(hand, deck, table) -> int:
    estimates = estimate_hand(
        hand,
        turns_left=TURNS_LEFT,
        stamina=STAMINA,
        deck=deck,
        episodes=EPISODES,
        time_budget_ms=TIME_BUDGET_MS,
        table=table,
    )
    if not estimates:
        print("\nFAIL：一张牌都没算出期望分")
        return 1
    chosen = choose_card_via_sim(
        hand,
        turns_left=TURNS_LEFT,
        stamina=STAMINA,
        deck=deck,
        episodes=EPISODES,
        time_budget_ms=TIME_BUDGET_MS,
        table=table,
    )
    if chosen is None:
        print("\nFAIL：模拟器没有给出选择")
        return 1
    best = next(item for item in estimates if item.index == chosen)
    playable = {
        item.index
        for item in specs_from_hand(hand, table=table)
        if item.cost <= STAMINA
    }

    # 规则基线（LessonPolicy）对比：sim 只是在它之上做前瞻
    state = LessonState(
        kind="audition",
        turns_left=TURNS_LEFT,
        stamina=STAMINA,
        cards=tuple(hand),
    )
    rule = LessonPolicy().decide(state)
    rule_name = rule.card.name if rule.card is not None else rule.reason
    print(f"\n候选（K={EPISODES}）：")
    for item in estimates:
        print(f"  [{item.index}] {item}")

    print(
        f"\n[lesson] sim-pick {best.name} (屏幕 {best.score:.0f}分/{best.cost}费) "
        f"期望 {best.expected:.1f}±{best.stdev:.1f} (K={best.episodes}) vs 规则选 {rule_name}"
    )
    print(f"最终选择：[{chosen}] {best.name} 期望 {best.expected:.1f}±{best.stdev:.1f}")
    print(f"规则 LessonPolicy 会选：{rule.kind} {rule_name}")
    return 0 if playable == {item.index for item in estimates} else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    table = CardTable()
    play_cards = specs_from_hand(HAND, table=table)
    base_deck = _base_deck()
    deck = approx_deck([item.spec for item in play_cards], base_deck)
    print(
        f"局面：剩余 {TURNS_LEFT} 回合，体力 {STAMINA}；"
        f"PIMC 每次 rollout 用 seed + episode*7919 采样牌序"
    )
    print("手牌 → CardSpec（cost 用卡表真值，分数优先屏幕宝石）：")
    for item in play_cards:
        print(
            f"  [{item.index}] {item.name}: cost={item.cost} "
            f"score={item.spec.score:.0f} buff={item.spec.condition}/"
            f"focus={item.spec.focus}/draw={item.spec.draw} "
            f"estimated={item.estimated}"
        )
    print(
        f"近似牌库：已知手牌 {len(play_cards)} 张 + 基础牌组 "
        f"{len(base_deck)} 张 → 扣掉当前手牌、截到 MAX_APPROX_DECK={MAX_APPROX_DECK} 张"
    )
    print(f"  rollout 牌库（{len(deck)} 张，只洗顺序）：{[item.name for item in deck]}")

    # 预热：第一次 estimate_hand 会加载卡表/方案库，别把一次性开销算进 K=1 耗时
    estimate_hand(
        HAND,
        turns_left=TURNS_LEFT,
        stamina=STAMINA,
        deck=deck,
        episodes=1,
        time_budget_ms=TIME_BUDGET_MS,
        table=table,
    )
    rows = _sweep(list(HAND), deck, table)
    if not rows:
        return 1
    _report_saturation(rows)
    result = _report_pick(list(HAND), deck, table)
    print(
        f"\n性能：K=1 单次决策 {rows[0]['ms']:.2f}ms，K={EPISODES} "
        f"{rows[3]['ms']:.2f}ms，K=32 {rows[-1]['ms']:.2f}ms"
        "（3 张候选合计，不含跨 seed 稳定性重跑）"
    )

    # 真实截图（有就顺手验一遍 OCR 读数 → 期望分，没有不影响验收）
    frame = ROOT / "data" / "exam_card_overlay.png"
    if frame.exists():
        import cv2

        from gkagent.vision.lesson import LessonReader
        from gkagent.vision.ocr import OcrEngine

        image = cv2.imread(str(frame))
        if image is not None:
            reader = LessonReader(OcrEngine())
            real_state = reader.read(image, kind="audition")
            if real_state.cards:
                print(f"\n真机截图 {frame.name} 读到 {len(real_state.cards)} 张手牌：")
                for item in real_state.cards:
                    print(
                        f"  [{item.index}] {item.name} score={item.score} hits={item.hits} "
                        f"cost={item.cost}"
                    )
                real_pick = choose_card_via_sim(
                    list(real_state.cards),
                    turns_left=max(int(real_state.turns_left or TURNS_LEFT), 1),
                    stamina=int(real_state.stamina or STAMINA),
                    episodes=EPISODES,
                    time_budget_ms=TIME_BUDGET_MS,
                )
                print(f"  截图 → 模拟器选择：{real_pick}")
            else:
                print(f"\n真机截图 {frame.name} 手牌读不到（OCR 掉帧），跳过")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
