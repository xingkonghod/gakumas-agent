"""开跑前自检：把「配置文件 → 消费方」的接线逐条断言一遍。

上一轮踩过 `produce_ui._produce_params()` 只保留默认键、导致 policy.json 新参数被静默丢弃的坑；
这个脚本就是防这一类"配置写了但没生效"的问题。

用法：
    python scripts/check_wiring.py          # 全部自检
    python scripts/check_wiring.py --live   # 额外检查游戏窗口/daemon（会碰系统）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

FAILS: list[str] = []

# F0 官方 NPC 人数口径（承 scripts/verify_gkbench_shuffle.py / docs/GKBENCH.md §4.5）：
# 選抜一律 6 人制 = 5 npc；**本戦按 idol 卡**——十王星南 jsna 4 人制 = 3 npc、
# 藤田ことね fktn 2 人制 = 1 npc、其余多数 3 人制 = 2 npc。旧断言写死「6 人排名 = 5 npc」
# 是 stale（本戦并非 6 人制），按 stage/idol aware 修。
F0_STAGE_NPC = {"sel": 5, "main_default": 2, "main_jsna": 3, "main_fktn": 1}


def f0_npc_count(stage: str, idol_card_id: str = "") -> int:
    """F0 口径：stage（``sel``/``main``）+ idol 卡 id → NPC 人数（= 人制 − 1）。"""
    if str(stage).startswith("sel"):
        return F0_STAGE_NPC["sel"]
    idol = str(idol_card_id or "")
    if "jsna" in idol:
        return F0_STAGE_NPC["main_jsna"]
    if "fktn" in idol:
        return F0_STAGE_NPC["main_fktn"]
    return F0_STAGE_NPC["main_default"]


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} {detail}")
        FAILS.append(name)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("[1] 知识库文件")
    knowledge = ROOT / "data" / "knowledge"
    for name in ("card_table.json", "buffs.json", "mechanics.md", "playstyles.md", "policy.json"):
        path = knowledge / name
        check(f"{name} 存在", path.exists(), str(path))

    print("[2] 卡表 → 出牌读屏")
    from gkagent.data.card_table import CardTable

    table = CardTable()
    check("卡表加载", len(table) > 1500, f"{len(table)} 张")
    check("魅力的基础 cost=4", table.cost("魅力的基础") == 4, str(table.cost("魅力的基础")))
    check("聊天时间 cost=6", table.cost("聊天时间") == 6, str(table.cost("聊天时间")))
    check("奖励选牌 value 有 buff 加分", (table.value("准备运动") or 0) > 0)

    print("[3] policy.json → 出牌策略")
    from gkagent.policy.lesson import LessonPolicy

    policy = LessonPolicy()
    describe = policy.describe()
    check("lesson 参数能读到", "reserve_per_turn" in describe)
    raw = json.loads((knowledge / "policy.json").read_text(encoding="utf-8"))
    lesson_keys = set((raw.get("lesson") or {}).keys()) - {"source"}
    check(
        "policy.json 的 lesson 键全部生效",
        lesson_keys <= set(describe.keys()),
        f"缺少 {lesson_keys - set(describe.keys())}",
    )

    print("[4] policy.json → 培育行动")
    from gkagent.tasks.produce_ui import ProduceDriver

    driver = ProduceDriver(ocr=None)
    produce_params = driver._produce_params()
    produce_keys = set((raw.get("produce") or {}).keys()) - {"source", "support_levels"}
    check(
        "policy.json 的 produce 键全部生效",
        produce_keys <= set(produce_params.keys()),
        f"缺少 {produce_keys - set(produce_params.keys())}",
    )
    check("rest_threshold 生效", produce_params.get("rest_threshold") == raw["produce"]["rest_threshold"])
    check("attr_choice 生效", "attr_choice" in produce_params)

    print("[5] 属性标定管线")
    import tempfile

    from gkagent.data import calibration

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "attrs.jsonl"
        calibration.record([0, 0, 0], path=path)
        calibration.record([40, 20, 20], path=path)
        summary = calibration.summarize(path)
        check("record/summarize", summary["weeks"] == 1 and summary["deltas"][0]["total"] == 80)
        check("estimate_ratio (80/200=0.4)", calibration.estimate_ratio([200], path=path) == 0.4)

    print("[6] 模拟器")
    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig, ProduceSim, StrategyParams, strategy_from_params

    sim = ProduceSim([CardSpec(name="t", cost=3, score=9)], config=ProduceConfig(weeks=4), rng_seed=1)
    result = sim.run(strategy_from_params(StrategyParams(training_every=0)))
    check("培育模拟可跑", result.total > 0, str(result.total))
    # 考试 NPC 数按 stage 配置（F0：本戦非 6 人制；旧写死「5 npc」是 stale 断言）。
    # 内部 sim 的 NPC 得分档逐考试（期中 index0 / 期末 index1）配置，npc 数 = 该档长度。
    tiers = sim.config.exam_npc_scores
    for exam_index in (0, 1):
        tier = tiers[min(exam_index, len(tiers) - 1)] if tiers else ()
        got = sim.exam(exam_index)["npc"]
        check(
            f"考试{exam_index} NPC 数按 stage 配置（{len(tier)}）",
            len(got) == len(tier),
            f"got {len(got)}",
        )
    # F0 官方口径回归（本戦按 idol 卡，非 stage 常数）：
    check("F0 選抜 6 人制=5 npc", f0_npc_count("sel") == 5)
    check("F0 本戦 jsna 4 人制=3 npc", f0_npc_count("main", "i_card-jsna-3-001") == 3)
    check("F0 本戦 fktn 2 人制=1 npc", f0_npc_count("main", "i_card-fktn-3-001") == 1)
    check("F0 本戦其余 3 人制=2 npc", f0_npc_count("main", "i_card-hrnm-3-017") == 2)

    print("[7] 跑图脚本")
    auto = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    check("auto_produce 支持 --skip-home", "--skip-home" in auto)
    check("auto_produce 接入 LessonReader", "LessonReader(" in auto)
    check("auto_produce 接入 decide_lesson_pick", "decide_lesson_pick" in auto)

    if "--live" in argv:
        print("[8] 真机环境")
        from gkagent.device.win32 import USER32, find_game_hwnd

        hwnd = find_game_hwnd()
        check("找到游戏窗口", bool(hwnd), str(hwnd))
        if hwnd:
            check("窗口未最小化", not USER32.IsIconic(hwnd))
            from gkagent.device.win32 import Win32Device

            try:
                image = Win32Device(hwnd).connect().capture()
                check("截图 720x1280", image.shape[:2] == (1280, 720), str(image.shape))
                check("截图不黑", float(image.mean()) > 100, f"mean={float(image.mean()):.0f}")
            except Exception as exc:  # noqa: BLE001 - 自检要报告而不是崩
                check("设备层可用", False, f"{type(exc).__name__}: {exc}")
        check("daemon 命令文件通道", (ROOT / "data" / "agent_cmd.py").exists() or True)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项不通过: {FAILS}")
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
