"""主数据 → 考试属性倍率配置（T5「审查倍率分段 + 联动惩罚」的数据接入层）。

主数据 ``catalog.sqlite`` 是 gakumasu-diff 快照（``data/hiro/vendor/.../master/``，
gitignore；与 F0 gkbench 校准同一份）。本模块把它需要的四张表解析成
``ExamBattleConfig``：

- ``IdolCard.produceStepAuditionDifficultyId`` → 本偶像卡用哪一行考试难度；
- ``ProduceStepAuditionDifficulty``（id + produceId + stepType）→ 考试配置 id；
- ``ProduceExamBattleConfig`` → 回合数 / 三项审查基准 / 分数表 id；
- ``ProduceExamBattleScoreConfig`` → 分段节点表（parameter → 三项 permil）；
- ``Setting`` → 惩罚上下限（本机 100/250）。

数据缺失（新偶像卡不在快照里 / 换场景）时**显式抛错**，不静默退回常数 4.11：
真机生产侧根本不用主数据——屏幕上直接读「舞蹈 207%」（``LessonState.multiplier``），
这里只服务离线模拟 / 评测 / 夹具导出。
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gkagent.sim.exam_multiplier import (
    ATTRS,
    PERMIL_COLUMNS,
    ExamBonus,
    calculate_bonus,
)

ROOT = Path(__file__).resolve().parents[3]
MASTER_DIR = ROOT / "data" / "hiro" / "vendor" / "gakumas-player" / "data" / "master"
STEP_TYPES: dict[str, str] = {
    "mid": "ProduceStepType_AuditionMid1",
    "mid1": "ProduceStepType_AuditionMid1",
    "final": "ProduceStepType_AuditionFinal",
    "ProduceStepType_AuditionMid1": "ProduceStepType_AuditionMid1",
    "ProduceStepType_AuditionFinal": "ProduceStepType_AuditionFinal",
}


class ExamConfigUnavailable(RuntimeError):
    """主数据里找不到这场考试的配置（缺表/缺偶像卡/缺难度行）。"""


def default_db_path() -> Path | None:
    """当前主数据快照路径（``master/current.json`` 优先，否则最新一份）。"""
    current = MASTER_DIR / "current.json"
    if current.is_file():
        try:
            database = json.loads(current.read_text(encoding="utf-8")).get("database")
        except (OSError, json.JSONDecodeError):
            database = None
        if database:
            path = MASTER_DIR / str(database)
            if path.is_file():
                return path
    candidates = sorted(MASTER_DIR.glob("*/catalog.sqlite"))
    return candidates[-1] if candidates else None


@lru_cache(maxsize=8)
def _load_table(db_path: str, table: str) -> tuple[dict, ...]:
    """主数据 ``records`` 表里一张表（gzip JSON payload）→ dict 元组（只读缓存）。"""
    con = sqlite3.connect(db_path)
    try:
        rows = [
            json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
            for (_row_id, _variant, payload) in con.execute(
                "select row_id, variant, payload from records where table_name=?", (table,)
            )
        ]
    finally:
        con.close()
    return tuple(rows)


@dataclass(frozen=True)
class ExamBattleConfig:
    """一场考试（某难度/某 stepType）的属性倍率配置。"""

    id: str
    turn: int
    criteria: Mapping[str, int]
    score_table: tuple[Mapping[str, int], ...]
    penalty_min_permil: int
    penalty_max_permil: int
    step_type: str = ""
    idol_card_id: str = ""

    def bonus(self, params: Mapping[str, int]) -> ExamBonus:
        """培育属性值（Vo/Da/Vi）→ 三项属性倍率（分段 + 联动惩罚）。"""
        return calculate_bonus(
            params,
            self.criteria,
            self.score_table,
            penalty_min_permil=self.penalty_min_permil,
            penalty_max_permil=self.penalty_max_permil,
        )


class ExamBonusResolver:
    """主数据 → ``ExamBattleConfig`` 的解析器（懒加载、只读）。"""

    def __init__(self, db_path: Path | str | None = None) -> None:
        path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path = path
        self.available = bool(path and Path(path).is_file())

    # ------------------------------------------------------------------ 数据
    def _rows(self, table: str) -> tuple[dict, ...]:
        if not self.available:
            raise ExamConfigUnavailable(
                f"主数据不可用（{self.db_path}）：先跑 setup/下载主数据，或只用屏幕倍率"
            )
        return _load_table(str(self.db_path), table)

    def _idol(self, idol_card_id: str) -> dict:
        for row in self._rows("IdolCard"):
            if str(row.get("id")) == str(idol_card_id):
                return row
        raise ExamConfigUnavailable(
            f"主数据缺偶像卡 {idol_card_id!r}（新卡未进快照）：这场考试只能用屏幕倍率"
        )

    def _penalty_limits(self) -> tuple[int, int]:
        settings = self._rows("Setting")
        if not settings:
            raise ExamConfigUnavailable("主数据缺 Setting 表（惩罚上下限）")
        row = settings[0]
        return (
            int(row["produceExamBattleScorePenaltyMinPermil"]),
            int(row["produceExamBattleScorePenaltyMaxPermil"]),
        )

    def _score_table(self, score_config_id: str) -> tuple[dict[str, int], ...]:
        rows = [row for row in self._rows("ProduceExamBattleScoreConfig")
                if str(row.get("id")) == str(score_config_id)]
        if not rows:
            raise ExamConfigUnavailable(f"主数据缺分数表 {score_config_id!r}")
        table = []
        for row in sorted(rows, key=lambda item: int(item["parameter"])):
            entry: dict[str, int] = {"parameter": int(row["parameter"])}
            for column in PERMIL_COLUMNS.values():
                if row.get(column) is None:
                    raise ExamConfigUnavailable(
                        f"分数表 {score_config_id!r} 缺列 {column}"
                    )
                entry[column] = int(row[column])
            table.append(entry)
        return tuple(table)

    def _difficulty_row(
        self, idol_card_id: str, produce_id: str, step_type: str
    ) -> dict:
        idol = self._idol(idol_card_id)
        difficulty_id = str(idol.get("produceStepAuditionDifficultyId") or "")
        if not difficulty_id:
            raise ExamConfigUnavailable(
                f"偶像卡 {idol_card_id!r} 没有 produceStepAuditionDifficultyId"
            )
        full_step = STEP_TYPES.get(step_type, step_type)
        matches = [
            row
            for row in self._rows("ProduceStepAuditionDifficulty")
            if str(row.get("id")) == difficulty_id
            and str(row.get("produceId")) == str(produce_id)
            and str(row.get("stepType")) == full_step
        ]
        if not matches:
            raise ExamConfigUnavailable(
                f"主数据缺难度行：{difficulty_id} / {produce_id} / {full_step}"
            )
        if len(matches) > 1:
            raise ExamConfigUnavailable(
                f"难度行不唯一：{difficulty_id} / {produce_id} / {full_step}"
                f"（{len(matches)} 行）"
            )
        return matches[0]

    # ------------------------------------------------------------------ 解析
    def battle_config(
        self, *, idol_card_id: str, produce_id: str, step_type: str
    ) -> ExamBattleConfig:
        """（偶像卡, 剧本, 期中/期末）→ 该场考试的倍率配置。"""
        row = self._difficulty_row(idol_card_id, produce_id, step_type)
        config_id = str(row.get("produceExamBattleConfigId") or "")
        configs = [c for c in self._rows("ProduceExamBattleConfig")
                   if str(c.get("id")) == config_id]
        if not configs:
            raise ExamConfigUnavailable(f"主数据缺考试配置 {config_id!r}")
        config = configs[0]
        criteria = {attr: int(config.get(attr) or 0) for attr in ATTRS}
        score_config_id = str(config.get("produceExamBattleScoreConfigId") or "")
        if not score_config_id:
            raise ExamConfigUnavailable(f"考试配置 {config_id!r} 没有分数表 id")
        penalty_min, penalty_max = self._penalty_limits()
        return ExamBattleConfig(
            id=config_id,
            turn=int(config.get("turn") or 0),
            criteria=criteria,
            score_table=self._score_table(score_config_id),
            penalty_min_permil=penalty_min,
            penalty_max_permil=penalty_max,
            step_type=STEP_TYPES.get(step_type, step_type),
            idol_card_id=idol_card_id,
        )

    def bonus(
        self,
        *,
        idol_card_id: str,
        produce_id: str,
        step_type: str,
        params: Mapping[str, int],
    ) -> ExamBonus:
        return self.battle_config(
            idol_card_id=idol_card_id, produce_id=produce_id, step_type=step_type
        ).bonus(params)


__all__ = [
    "MASTER_DIR",
    "STEP_TYPES",
    "ExamBattleConfig",
    "ExamBonusResolver",
    "ExamConfigUnavailable",
    "default_db_path",
]
