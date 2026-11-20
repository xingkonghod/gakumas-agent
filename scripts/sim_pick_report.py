"""统计一局日志里的「模拟器选牌 vs 规则选牌」分歧率与改选好坏。

用法：
    python scripts/sim_pick_report.py ep-sim4

读 ``data/auto/auto_log_<ep>.log`` 里的 ``[lesson] sim-pick`` 行，输出：
- sim-pick 总条数 / 与规则一致 / 改选（分歧率）；
- 改选时比较两边「屏幕分」（卡面打分数值），判断改选偏强还是偏弱；
- 改选明细（模拟器牌、期望分、规则牌、规则估值）。

注意：模拟口径期望分和屏幕分不是同一量纲，只用于排序；本报告只比较两边的**屏幕分**。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
LOG_DIR = ROOT / "data" / "auto"

# 新格式（2df5c36 之后）：两边都带屏幕分
_NEW_AGREE = re.compile(
    r"sim-pick 与规则一致 (?P<name>.+?) \(屏幕 (?P<score>\d+)分、模拟口径期望 (?P<exp>[\d.]+)、"
    r"规则估值 (?P<val>[\d.]+)\)"
)
_NEW_PICK = re.compile(
    r"sim-pick (?P<sim>.+?) \(屏幕 (?P<sim_score>\d+)分/(?P<cost>\d+)费、模拟口径期望 (?P<exp>[\d.]+)\)"
    r" vs 规则选 (?P<rule>.+?)\(屏幕 (?P<rule_score>\d+)分、规则估值 (?P<val>[\d.]+)\)"
)
# 旧格式（只有模拟器牌面分和规则估值）
_OLD_AGREE = re.compile(r"sim-pick 与规则一致 (?P<name>.+?) \(期望 (?P<exp>[\d.]+)\)")
_OLD_PICK = re.compile(
    r"sim-pick (?P<sim>.+?) \((?P<sim_score>\d+)分/(?P<cost>\d+)费\) 期望 (?P<exp>[\d.]+)"
    r" vs 规则选 (?P<rule>.+?)\((?P<rule_score>\d+)分\)"
)


def analyze(lines: list[str]) -> dict:
    agree = 0
    picks: list[dict] = []
    for line in lines:
        if "sim-pick" not in line:
            continue
        match = _NEW_AGREE.search(line)
        if match:
            agree += 1
            continue
        match = _NEW_PICK.search(line) or _OLD_PICK.search(line)
        if match:
            picks.append(match.groupdict())
            continue
        if _OLD_AGREE.search(line):
            agree += 1
    total = agree + len(picks)
    stronger = sum(1 for pick in picks if int(pick["sim_score"]) > int(pick["rule_score"]))
    weaker = sum(1 for pick in picks if int(pick["sim_score"]) < int(pick["rule_score"]))
    equal = len(picks) - stronger - weaker
    return {
        "total": total,
        "agree": agree,
        "picks": picks,
        "stronger": stronger,
        "weaker": weaker,
        "equal": equal,
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    episode = argv[0] if argv else "ep-sim4"
    path = LOG_DIR / f"auto_log_{episode}.log"
    if not path.exists():
        print(f"没有日志：{path}")
        return 1
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    stats = analyze(lines)
    total = stats["total"]
    print(f"=== {episode} 出牌决策 ===")
    print(f"sim-pick 总条数: {total}")
    print(f"与规则一致: {stats['agree']}  改选: {len(stats['picks'])}"
          f"（分歧率 {len(stats['picks']) / total * 100 if total else 0:.0f}%）")
    print(f"改选里屏幕分更高: {stats['stronger']}  更低: {stats['weaker']}  相同: {stats['equal']}")
    for pick in stats["picks"]:
        print(
            f"  sim {pick['sim']} 屏幕 {pick['sim_score']}分/{pick['cost']}费 "
            f"期望 {pick['exp']} → 规则 {pick['rule']} 屏幕 {pick['rule_score']}分 "
            f"估值 {pick.get('val', '-')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
