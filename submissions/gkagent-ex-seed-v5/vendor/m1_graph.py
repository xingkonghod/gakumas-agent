"""M1 消费图 graph-clean 门（clean-room 自写，vendored 进 v3g 以便托管自包含）。

口径与 src/gkagent/sim/{rng_graph,exam_risk}.py 的 ``use_graph=True`` opt-in 完全一致：
消费次数已被探针①/实机完全刻画的效果（ExamCardCreateId / ExamCardMove / ExamPanic /
0-RNG 搜索变体 type59/38/156/22）不再算风险；只有**未刻画**消费点（type21 ExamCardCreateSearch
随机池 / ExamReviewPerSearchCount）仍算风险。``m1_rng_index.json`` 是从主数据 card_table 预计算的
``card_id -> 未刻画效果类型`` 索引（仅 2 张卡），随投稿自带，托管无需 src/gkagent。

本文件独立自写（BSD-3 clean-room 口径），不拷任何 AGPL/参考源码；引擎只作 oracle。
"""
from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_INDEX = None

# 未刻画消费点（与 rng_graph.UNMODELED_EFFECT_TYPES 同口径）。
UNMODELED_EFFECT_TYPES = frozenset({"ExamCardCreateSearch", "ExamReviewPerSearchCount"})


def unmodeled_index() -> dict:
    global _INDEX
    if _INDEX is None:
        p = _HERE / "m1_rng_index.json"
        _INDEX = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _INDEX


def _card_id_of(item) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("produce_card_id") or item.get("id")
    if isinstance(item, (list, tuple)) and item:
        return str(item[0])
    return None


def graph_rng_risks(deck) -> list:
    """消费图口径风险扫描：只保留含未刻画消费点的卡（去重、字典序）。"""
    idx = unmodeled_index()
    risks, seen = [], set()
    for item in deck:
        cid = _card_id_of(item)
        if not cid or cid in seen:
            continue
        hits = idx.get(cid)
        if not hits:
            continue
        seen.add(cid)
        risks.append({"card_id": cid, "effects": sorted(hits)})
    risks.sort(key=lambda r: str(r["card_id"]))
    return risks


def known_info_ok_graph(deck) -> bool:
    """牌组是否消费图全知合格（无未刻画消费点）= exam_risk.known_info_ok(use_graph=True)。"""
    return not graph_rng_risks(deck)