"""一次性提取脚本：把生产 expectimax 回合内搜索核心**逐字**提取进投稿 algo.py。

不提交。来源（commit 8131cfd，只读）：
  src/gkagent/sim/expectimax.py  回合内搜索路径（排除 rollout/beam/全知重洗/sim 桥）
  src/gkagent/sim/stance.py      指針纯函数（全量）
  src/gkagent/sim/enthusiasm.py  熱意/解除纯函数（全量）
  src/gkagent/sim/hold.py        HOLD_LIMIT/HOLD_SELECT_ZONES/hold_pick
  src/gkagent/sim/lesson.py      safe_ceil/genki_gate/CardSpec/DrinkSpec/DRINK_EFFECTS
  src/gkagent/sim/p_items.py     事件常量 + timed 倍率纯函数 + intercept_debuff_entries
  submissions/gkagent-ei-r13/algo.py  _num/_as_int/_status_fields/_stance_from_obs/正则

P 道具**效果结算**（apply_passive/触发求值/card_meta 索引）有意不提取：投稿与 r13
同口径 p_items=()，生产 fire_p_items 在 p_items=() 时首行返回，提取版逐字保留该路径；
非空 p_items/delayed 会触到显式抛错的守卫 stub（绝不静默算错）。

同时用生产链（sim_produce._effect_fields + _spec_from_row + eval_expectimax._with_once）
预计算全字段 card_specs.json（r13 card_profiles 同来源，保留 turns/hold/熱意 等全部字段）。

    .venv\\Scripts\\python.exe data\\_f2ex_extract.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
SIM = ROOT / "src" / "gkagent" / "sim"
SUB = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
R13 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ei-r13" / "algo.py"
COMMIT = "8131cfd"


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def take(lines: list[str], start: int, end: int) -> str:
    """1-based inclusive 行范围，逐字。"""
    return "\n".join(lines[start - 1:end])


def main() -> None:
    ex = lines_of(SIM / "expectimax.py")
    st = lines_of(SIM / "stance.py")
    en = lines_of(SIM / "enthusiasm.py")
    ho = lines_of(SIM / "hold.py")
    le = lines_of(SIM / "lesson.py")
    pi = lines_of(SIM / "p_items.py")
    r13 = lines_of(R13)
    adapter = (ROOT / "data" / "_f2ex_adapter_part.py").read_text(encoding="utf-8")

    header = f'''"""gkbench 投稿：回合内 expectimax 搜索引擎（public-safe，只读 UIObs 出牌）。

决策 = 对每个合法 play 动作跑**回合内 expectimax**：枚举本回合合法有序出牌序列，
抽牌走精确超几何机会节点（deck/grave 是无序多重集 → 期望），回合末解析式 V_leaf
估未来得分，取期望分最高的首牌（不是网 argmax）。

搜索核心**逐字提取**自生产 gkagent（commit {COMMIT}，只读参考，不改生产代码）：
sim/expectimax.py 的回合内路径（ExpectState/_Search/apply_card/_apply_card_effects/
_card_award/_draw_distribution/end_turn_state/expectimax_with_stats 等）+ 依赖纯函数
sim/stance.py（指針）/sim/enthusiasm.py（熱意/温存解除）/sim/hold.py（保留区）/
sim/lesson.py（safe_ceil/genki_gate/CardSpec/DrinkSpec）/sim/p_items.py（timed 倍率）。
排除：rollout 叶子、跨回合 beam、known_draw/reshuffle 全知路径、LessonSim 桥
（public-safe 用不到）。同 ExpectState + 同 AnalyticLeafValue 下与生产 search
选牌/期望分逐位对拍一致（见 test_adapter.py B 部分）。

UIObs → ExpectState 映射**复用 r13 已验证适配器**（249 项检查 + 7642 步真实观测
回放，与生产逐位误差 0）：_status_fields/_stance_from_obs/_num/_as_int 逐字取自
submissions/gkagent-ei-r13/algo.py；卡表改用**全字段 CardSpec**（card_specs.json，
生产训练链 sim_produce._effect_fields + _spec_from_row + eval_expectimax._with_once
预计算，r13 card_profiles 同来源但保留 turns/hold/熱意 等全部字段，搜索无损）；
g/c 透明子集增强与 r13 同语义（目标从画像列换成 CardSpec 字段）。

尺度适配（expectimax 相对网的关键差异）：即时出牌分按 obs.exam.permil 的**真实
属性倍率**结算（_card_award × attribute_coefficient，hajime 4–6×、hif 20–48×），
不依赖训练分布；叶子 μ（白值单位）× 剩余未来回合倍率均值换算成真实分单位
（ScoreLeaf.scale，scale_leaf=0 可 ablation）。

叶子目标 = 当前分 + 期望未来分（scripts/local_bench.py ScoreObjectiveLeaf 同口径）：
gkbench 按原始分数排名，obs 的 crit 是逐回合审查基准（课程题全 0）不是终线，
档位效用 AnalyticLeafValue.utility 在 clear=0 时恒 0 会退化 → 换期望分数目标。
搜索核心本身不改。

保守默认（画面没有 / 建模不到，如实记录不猜，r13 同局限）：
- clear/perfect=0（叶子不依赖档位线）；课程题 permil=[0,0,0]/types=[] → 倍率 1.0。
- 饮料：obs 只给 id，本地无饮料效果目录 → **从不喝饮料**（allow_drinks=False）。
- P 道具/附魔/回忆/支援卡/gimmick：不结算效果（p_items=()）。生产 fire_p_items
  在 p_items=() 时首行返回原状态（逐字保留）；非空 p_items/delayed 触到显式守卫
  抛错（_PItemsNotExtracted），绝不静默算错。
- state.parameter_buff（turn_parameter_buff）UIObs 无图标 → 0；metamorphosis ""；
  enthusiasm/lock_stance/hand_decreases 等 r13 未映射的状态 → 默认 0（保守）。
- cards_played_total 跨 decide 累计自己返回的 play（引擎强制出牌计不到，低估）；
  min_cost 用 deck+hand+grave+hold 全已知牌最小费用近似。

用户硬规矩：**有可出牌就绝不 end**（legal 里有 play 必出牌；搜索选 SKIP 时按动作
价值取最大 play）；不读种子、不用 worlds。搜索异常不偷换规则：退回 legal 里的牌
并在 meta["error"] 如实记录。deadline：anytime 预算 budget_ms（默认 4200ms，
step_seconds=5 留 IPC 余量）+ max_nodes=200000（生产默认）。
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from gkbench.algos.base import Algorithm, Decision
'''

    stubs = '''
# ---------------------------------------------------------------- P 道具效果结算边界
# 本投稿与 r13 同口径：**不结算 P 道具效果**（ExpectState.p_items 恒 ()、delayed 恒 ()）。
# 生产 fire_p_items 在 p_items=() 时第一行即返回原状态（上方逐字保留），所以下面这些
# 名字在适配器状态空间内永远不会被调用。若有人塞了非空 p_items/delayed，显式抛错，
# 绝不静默算错（apply_passive 的触发条件求值依赖 gkagent.data.card_meta 主数据索引，
# 不在自包含提取范围内）。
class _PItemsNotExtracted(RuntimeError):
    """P 道具效果结算未提取进本投稿（p_items 恒 ()，r13 同局限）。"""


def apply_passive(*_args: Any, **_kwargs: Any) -> Any:
    raise _PItemsNotExtracted("apply_passive 未提取：本投稿 p_items 恒 ()（r13 同局限）")


class PassiveEvent:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise _PItemsNotExtracted("PassiveEvent 未提取：本投稿 p_items 恒 ()")


class PassiveState:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise _PItemsNotExtracted("PassiveState 未提取：本投稿 p_items 恒 ()")


class PItemDelta:
    @staticmethod
    def thaw(*_args: Any, **_kwargs: Any) -> Any:
        raise _PItemsNotExtracted("PItemDelta 未提取：本投稿 delayed 恒 ()")


class PItemSpec:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise _PItemsNotExtracted("PItemSpec 未提取：本投稿 p_items 恒 ()")
'''

    def banner(title: str, src: str, ranges: str) -> str:
        return f"\n\n# ================================================================ {title}\n# 逐字提取自 {src}（commit {COMMIT}），行 {ranges}。\n"

    parts: list[str] = [header]

    parts.append(banner("指針纯函数", "src/gkagent/sim/stance.py", "36-323"))
    parts.append(take(st, 36, 323))

    parts.append(banner("熱意 / 温存解除纯函数", "src/gkagent/sim/enthusiasm.py", "47-143"))
    parts.append(take(en, 47, 143))

    parts.append(banner("保留区常量 + 选牌", "src/gkagent/sim/hold.py", "45-55, 135-144"))
    parts.append(take(ho, 45, 55))
    parts.append("\n\n")
    parts.append(take(ho, 135, 144))

    parts.append(banner("取整 / 元气闸门 / CardSpec / DrinkSpec", "src/gkagent/sim/lesson.py",
                        "265, 276-303, 328-462, 465-497"))
    parts.append(take(le, 265, 265))
    parts.append("\n\n")
    parts.append(take(le, 276, 303))
    parts.append("\n\n")
    parts.append(take(le, 328, 462))
    parts.append("\n\n")
    parts.append(take(le, 465, 497))

    parts.append(banner("P 道具事件常量 + timed 倍率纯函数", "src/gkagent/sim/p_items.py",
                        "52-68, 798-892"))
    parts.append(take(pi, 52, 68))
    parts.append("\n\n")
    parts.append(take(pi, 798, 892))

    parts.append(stubs)

    parts.append(banner("搜索常量", "src/gkagent/sim/expectimax.py", "151-166"))
    parts.append(take(ex, 151, 166))

    parts.append(banner("搜索工具 / ExpectState", "src/gkagent/sim/expectimax.py",
                        "169-196, 199-494, 497-509, 512-538, 542-648"))
    for a, b in ((169, 196), (199, 494), (497, 509), (512, 538), (542, 648)):
        parts.append(take(ex, a, b))
        parts.append("\n\n")

    parts.append(banner("合法性 / 费用 / 饮料动作", "src/gkagent/sim/expectimax.py",
                        "929-956, 959-1071"))
    parts.append(take(ex, 929, 956))
    parts.append("\n\n")
    parts.append(take(ex, 959, 1071))

    parts.append(banner("出牌结算（算分/付费/buff/指針）", "src/gkagent/sim/expectimax.py",
                        "1074-1103, 1106-1174, 1177-1429"))
    for a, b in ((1074, 1103), (1106, 1174), (1177, 1429)):
        parts.append(take(ex, a, b))
        parts.append("\n\n")

    parts.append(banner("抽牌机会节点（超几何精确）", "src/gkagent/sim/expectimax.py",
                        "1433-1462, 1465-1515, 1518-1532, 1535-1611, 1614-1639, 1642-1742"))
    for a, b in ((1433, 1462), (1465, 1515), (1518, 1532), (1535, 1611), (1614, 1639), (1642, 1742)):
        parts.append(take(ex, a, b))
        parts.append("\n\n")

    parts.append(banner("apply_card / run_sequence", "src/gkagent/sim/expectimax.py",
                        "1745-1789, 1792-1803"))
    parts.append(take(ex, 1745, 1789))
    parts.append("\n\n")
    parts.append(take(ex, 1792, 1803))

    parts.append(banner("P 道具触发管道（p_items=() 时首行返回，逐字保留）",
                        "src/gkagent/sim/expectimax.py",
                        "1932-1950, 1953-1993, 1996-2027, 2030-2111, 2114-2401"))
    for a, b in ((1932, 1950), (1953, 1993), (1996, 2027), (2030, 2111), (2114, 2401)):
        parts.append(take(ex, a, b))
        parts.append("\n\n")

    parts.append(banner("回合开始 / 回合末结算", "src/gkagent/sim/expectimax.py",
                        "2404-2410, 2413-2428, 2431-2620, 2623-2654"))
    for a, b in ((2404, 2410), (2413, 2428), (2431, 2620), (2623, 2654)):
        parts.append(take(ex, a, b))
        parts.append("\n\n")

    parts.append(banner("搜索（_Search / tie-break / 入口）", "src/gkagent/sim/expectimax.py",
                        "2658-2666, 2669-2814, 2817-2844, 2847-2905, 2908-2934, "
                        "2937-2957, 2960-2966, 2969-3003"))
    for a, b in ((2658, 2666), (2669, 2814), (2817, 2844), (2847, 2905),
                 (2908, 2934), (2937, 2957), (2960, 2966), (2969, 3003)):
        parts.append(take(ex, a, b))
        parts.append("\n\n")

    parts.append(banner("r13 映射（逐字复用）", "submissions/gkagent-ei-r13/algo.py",
                        "171-173, 227-239, 580-634, 637-655"))
    for a, b in ((171, 173), (227, 239), (580, 634), (637, 655)):
        parts.append(take(r13, a, b))
        parts.append("\n\n")

    parts.append(adapter)

    SUB.mkdir(parents=True, exist_ok=True)
    out = SUB / "algo.py"
    out.write_text("".join(parts), encoding="utf-8")
    n = len(out.read_text(encoding="utf-8").splitlines())
    print(f"wrote {out} ({out.stat().st_size / 1e3:.1f} KB, {n} lines)")

    # ---- card_specs.json：生产链全字段预计算 ----
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    import sim_produce as sp  # noqa: E402
    from eval_expectimax import _master_texts, _with_once  # noqa: E402
    from gkagent.sim.lesson import CardSpec  # noqa: E402

    table = json.loads((ROOT / "data" / "knowledge" / "card_table.json").read_text(encoding="utf-8"))["cards"]
    texts = _master_texts()
    cards: dict[str, dict] = {}
    once_count = 0
    for name, row in table.items():
        cid = str(row.get("id") or "")
        if not cid:
            continue
        upgrade = int(row.get("upgrade") or 0)
        cost = int(row.get("cost") or 0)
        fields_tuple = sp._effect_fields(row)
        spec = sp._spec_from_row(sp.CardRow(name, cost, *fields_tuple))
        spec = _with_once(spec, texts)
        cards[f"{cid}|{upgrade}"] = asdict(spec)
        once_count += int(spec.once)
    payload = {
        "format": "gkagent.expectimax_card_specs.v1",
        "source": f"data/knowledge/card_table.json via scripts/sim_produce._effect_fields + "
                  f"_spec_from_row + eval_expectimax._with_once (commit {COMMIT}); full CardSpec fields",
        "cards": cards,
    }
    specs_out = SUB / "card_specs.json"
    specs_out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {specs_out} ({specs_out.stat().st_size / 1e6:.2f} MB): {len(cards)} rows, once={once_count}")

    #  sanity：提取版 CardSpec 字段集 == 生产 CardSpec 字段集
    from dataclasses import fields as dfields
    import importlib.util
    sys.path.insert(0, str(ROOT / "data" / "bench_repo"))  # gkbench.algos.base
    sp2 = importlib.util.spec_from_file_location("f2ex_algo_check", out)
    mod = importlib.util.module_from_spec(sp2)
    sys.modules["f2ex_algo_check"] = mod
    sp2.loader.exec_module(mod)
    assert {f.name for f in dfields(mod.CardSpec)} == {f.name for f in dfields(CardSpec)}, "CardSpec 字段集不一致"
    sample = next(iter(cards.values()))
    rebuilt = mod.CardSpec(**{f.name: sample[f.name] for f in dfields(mod.CardSpec) if f.name in sample})
    prod = CardSpec(**{f.name: sample[f.name] for f in dfields(CardSpec) if f.name in sample})
    assert asdict(rebuilt) == asdict(prod), "CardSpec 重建不一致"
    print("sanity OK: CardSpec fields match production; module imports clean")


if __name__ == "__main__":
    main()
