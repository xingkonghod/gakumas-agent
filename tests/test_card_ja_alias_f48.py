"""F#48 回归：新偶像卡日文名别名解析（v3.6.1 真机 ep-t31 期末 T8 mismatch 根因）。

背景：游戏汉化 overlay（2026-09-16）滞后，v3.6.0 新偶像卡「柔らかな光の中で」
（中文「温柔的光之中」，p_card-01-ido-3_292）在游戏里显示**日文**，OCR 读日文名。
旧 ``CardTable.get`` 只按中文卡名索引 → 日文名落空 → 该卡 score=0/效果未建模 +
``ExamDrawPlan`` 手牌核对 T8 起 mismatch（known_draw 停用）。

修复：card_table.json 增 ``ja_aliases``（YAML 日文名 ⋈ 中文卡名，全量 1765 条），
``CardTable.get`` 增日文别名 fallback（精确 + 丢「+」退基础版，与 CardMetaIndex 同口径）。
这些测试只读已提交的 card_table.json，秒级完成。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.data.card_table import CardTable
from gkagent.sim.exam_plan import ExamDrawPlan, ExamSetup

TABLE = ROOT / "data" / "knowledge" / "card_table.json"
IDO_ID = "p_card-01-ido-3_292"


def test_card_table_resolves_japanese_idol_card() -> None:
    """OCR 日文名「柔らかな光の中で+」必须命中偶像卡（修复前 None）。"""
    ct = CardTable()
    row = ct.get("柔らかな光の中で+")
    assert row is not None, "日文偶像卡名应经 ja_aliases 命中"
    assert row["id"] == IDO_ID
    assert int(row["upgrade"]) == 1
    # 读得到打分数值（修复前 score_of=None → 政策估 0 盲打）
    assert ct.score_of("柔らかな光の中で+") is not None


def test_card_table_japanese_base_and_plus_variants() -> None:
    ct = CardTable()
    base = ct.get("柔らかな光の中で")
    assert base is not None and base["id"] == IDO_ID and int(base["upgrade"]) == 0
    two = ct.get("柔らかな光の中で++")
    assert two is not None and two["id"] == IDO_ID and int(two["upgrade"]) == 2
    # OCR 丢「+」退回基础版仍命中
    assert ct.get("柔らかな光の中で＋") is not None


def test_card_table_chinese_lookup_unchanged() -> None:
    """中文卡名查找行为不变（别名是 fallback，不抢占精确命中）。"""
    ct = CardTable()
    row = ct.get("温柔的光之中+")
    assert row is not None and row["id"] == IDO_ID and int(row["upgrade"]) == 1
    assert ct.get("演出计划")["id"] == "p_card-01-men-2_034"
    assert ct.get("平衡感")["id"] == "p_card-01-men-1_024"


def test_ja_aliases_cover_new_idol_card() -> None:
    raw = json.loads(TABLE.read_text(encoding="utf-8"))
    ja = raw.get("ja_aliases") or {}
    assert ja.get("柔らかな光の中で") == "温柔的光之中"
    assert ja.get("柔らかな光の中で+") == "温柔的光之中+"
    # 新技能卡日文名也覆盖（演出計画 / バランス感覚）
    assert ja.get("演出計画") == "演出计划"
    assert ja.get("バランス感覚") == "平衡感"


def test_unknown_name_still_none() -> None:
    """别名 fallback 不产生假阳性：不存在的卡名仍返回 None。"""
    ct = CardTable()
    assert ct.get("存在しないカード_xyz") is None
    assert ct.get("") is None


def test_exam_plan_resolves_japanese_t8_hand() -> None:
    """ep-t31 期末 T8 实机手牌（OCR 日文偶像卡名）应能解析，不再因名落空 mismatch。"""
    setup = ExamSetup(
        seed=0x41EDB911,
        deck=((IDO_ID, 1), ("p_card-01-men-2_034", 0), ("p_card-01-men-1_024", 0)),
        config_turns=12,
        npc_count=5,
    )
    plan = ExamDrawPlan(setup)
    resolved = plan._resolve(["演出计划", "柔らかな光の中で+", "平衡感"])
    assert resolved is not None, "T8 手牌含日文偶像卡名应可解析（修复前 None）"
    assert resolved == [
        ("p_card-01-men-2_034", 0),
        (IDO_ID, 1),
        ("p_card-01-men-1_024", 0),
    ]