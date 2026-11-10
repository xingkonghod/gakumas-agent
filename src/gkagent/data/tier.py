"""网上攻略 Tier 表（game8 H.I.F 2026-11）与升级优先级。

说明：偶像名已通过本地化字典转成中文；部分支援卡名暂时保留日文，
等补全日→中名称对照后即可直接匹配游戏中文 UI。
"""

from __future__ import annotations

from dataclasses import dataclass

TIER_SCORE = {"SS": 4.0, "S": 3.0, "A": 2.0, "B": 1.0}

# P 偶像（H.I.F 环境，game8 最強キャラ）
IDOL_TIERS: dict[str, str] = {
    "仓本千奈": "SS",
    "秦谷美铃": "SS",
    "筱泽广": "SS",
}

# 支援卡（H.I.F 环境 SS 档，game8 最強サポカ）
SUPPORT_TIERS_SS: tuple[str, ...] = (
    "ふわふわでワクワク",
    "もうすぐ本番ですね",
    "･･････騒々しいお祭りね",
    "上かッ！！",
    "堂々とサボってる！？",
    "なぜこんなところにッ！？",
    "やっと見つけたぞ！",
    "月村手毬、興味深いわね",
    "おっと、危ないよ",
    "おい、来てやったぞ！",
    "いつまでも続けばいいのに",
    "放っておけない気になる子",
    "いつも頑張ってるね。",
    "よくやったな、倉本。",
)

SUPPORT_TIERS: dict[str, str] = {name: "SS" for name in SUPPORT_TIERS_SS}


@dataclass(frozen=True)
class UpgradeTarget:
    name: str
    level: int
    tier: str
    score: float


def tier_of(name: str) -> str:
    if name in IDOL_TIERS:
        return IDOL_TIERS[name]
    if name in SUPPORT_TIERS:
        return SUPPORT_TIERS[name]
    for table in (IDOL_TIERS, SUPPORT_TIERS):
        for key, tier in table.items():
            if key and (key in name or name in key):
                return tier
    return "?"


def plan_upgrades(
    owned: list[tuple[str, int]],
    *,
    limit: int = 3,
) -> list[UpgradeTarget]:
    """按 Tier 高→低、同 Tier 等级低→高排序，返回优先升级目标。"""
    targets: list[UpgradeTarget] = []
    for name, level in owned:
        tier = tier_of(name)
        score = TIER_SCORE.get(tier, 0.0)
        targets.append(UpgradeTarget(name, int(level), tier, score))
    targets.sort(key=lambda t: (-t.score, t.level))
    return [t for t in targets if t.score > 0][:limit]
