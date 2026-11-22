"""解析 ProduceItem 主数据，产出 data/knowledge/p_items.json（P 道具 / 被动道具）。

数据来源：
  * 中文：``masterTrans/ProduceItem.json``（游戏本地解包 master，2026-09-16 版）
    —— 只有 id / name / produceDescriptions 三个字段，描述是"分段"结构：
    普通文本段 + ``ProduceExamEffectType`` 标签段（打分/元气/体力回复…）+
    ``Exam`` 数值段（``CustomizeEffectValue1`` 等标记里带数值）。
  * 结构化字段：``data/cache/ProduceItem.yaml``（vertesan/gakumasu-diff 上游 diff 出的
    原始 master，21MB / **1115 件**）。本地 master 里**没有** rarity 和 trigger/effect
    关联，这两个只能从 yaml 的 ``rarity`` / ``originProduceExamTriggerId`` 拿。
  * **本地 master 没有、yaml 才有的 47 个新 id（2026-11 上游新增）**：结构化字段 +
    日文描述来自 yaml；卡名优先用仓库里的自译表 ``data/i18n/translation_new.json``
    （只有名字），没有就保留日文名并在记录上标 ``i18n_name_source="ja"``；
    **中文描述缺失**时 ``text_zh`` 留空、``text_ja`` 保留 yaml 原文，并标
    ``i18n_text_source="ja"``——不猜效果、不臆造译文。
  * 触发时机中文：``masterTrans/ProduceExamTrigger.json``（``e_trigger-*`` 的中文描述）。
    本地 masterTrans 是 2026-09-16 快照，新 id 用的新触发 id 没有中文触发句 →
    ``condition_known=False``（条件未知时**保守不触发**，见 ``sim/p_items.py``）。
  * 效果类型中文：``masterTrans/ProduceDescriptionExamEffect.json``

效果 / 数值的抽取口径（实测验证过）：
  * yaml 里每个 ``produceDescriptions`` 条目要么属于"触发/条件"（带
    ``originProduceExamTriggerId``），要么属于"效果"（trigger id 为空）；
    带 trigger id 的 ``ExamLessonBuff``（如"集中≥5"）只是条件里提到的状态，**不算效果**。
  * 数值段在 master 里是独立条目（``effectValue1`` 字段存数值、``text`` 是本地化后的
    显示数字），按顺序挂到前一个效果上。取 ``text`` 而不是字段值：percent 类字段
    在上游是 ×10 存的（30% 存成 300），取 text 才和中文/日文显示一致
    （实测 1396/1396 个数值段对齐，其中 281 个 percent 段是上游 ×10 编码）。
  * 次数上限：有 ``effectCount`` 且中文描述里对应出现 "（N次）" 的，才记成
    ``max_uses``（避免把"技能卡使用数追加+1"的 1 当成上限）。

用法：
  .venv\\Scripts\\python.exe scripts/build_p_items.py            # 生成 json + 打印统计
  .venv\\Scripts\\python.exe scripts/build_p_items.py --check    # 只打印统计，不写文件
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(r"D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans")
YAML = ROOT / "data" / "cache" / "ProduceItem.yaml"
OUT = ROOT / "data" / "knowledge" / "p_items.json"
# 仓库里已提交的自译表（P0 59 条：3 张卡的 12 变体 + 47 个 P 道具的名字）。
# 只用来给「本地 masterTrans 没有的新 id」补中文**卡名**；描述仍是日文，不猜。
I18N_NAMES = ROOT / "data" / "i18n" / "translation_new.json"

# B9（2026-11-22）：持久倍率 / modifier 类效果的分类与数值口径复用 sim/p_items.py
# 的纯函数（effect_type + 效果文本 → target / duration），避免两处各写一套。
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from gkagent.data.card_meta import card_meta_index
from gkagent.sim.p_items import (
    classify_effect_target,
    effect_duration,
)

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")

RARITY = {
    "ProduceItemRarity_N": "N",
    "ProduceItemRarity_R": "R",
    "ProduceItemRarity_Sr": "SR",
    "ProduceItemRarity_Ssr": "SSR",
}

# 效果类型中文名（也用来判断"堆叠类"效果）
STACK_KEYS = {
    "元气": "vitality",
    "好印象": "impression",
    "集中": "focus",
    "好调": "parameter_buff",
    "干劲": "aggressive",
    "全力值": "full_power_point",
    "强气": "stance_concentration",
    "温存": "stance_preservation",
    "全力": "stance_full_power",
}

# e_trigger-* 前缀 -> (canonical trigger, 是否落在"出牌/回合"事件里)
EXAM_TRIGGERS: list[tuple[str, str]] = [
    ("exam_play_turn_count_interval", "card_play_interval"),  # 回合内每使用 N 次技能卡
    ("exam_play_count_interval_after", "card_play_interval_after"),  # 每使用 N 次技能卡后
    ("exam_play_count_interval", "card_play_interval"),  # 每使用 N 次技能卡
    ("exam_review_up_interval", "status_gain_interval"),  # B8：好印象累计增加 N 次时
    ("exam_aggressive_up_interval", "status_gain_interval"),  # 干劲增加 N 次时
    ("exam_status_change", "status_gain"),  # 直接效果使 X 增加后
    ("exam_stance_change", "stance_change"),  # 指针 / 强气 / 全力 / 温存
    ("exam_stamina_reduce", "stamina_reduce"),  # 体力减少时
    ("exam_card_play_after", "card_played"),  # 技能卡使用后
    ("exam_card_play", "card_play"),  # 技能卡使用时
    ("exam_card_move_lost", "card_moved_out"),  # 技能卡被移动到除外时
    ("exam_start_turn", "turn_start"),  # 回合开始时
    ("exam_end_turn_interval", "turn_end_interval"),  # 每 N 回合的回合结束时
    ("exam_end_turn", "turn_end"),  # 回合结束时
    ("exam_turn_timer", "turn_start"),  # 第 N 回合开始时
    ("exam_turn_interval", "turn_interval"),  # 每 N 回合
    ("exam_turn_skip", "turn_skip"),  # 跳过回合时
    ("exam_buff_consume", "buff_consume"),  # 使用以强化状态为花费的技能卡时
    ("exam_start_exam", "exam_start"),  # 训练 / 考试 / 试镜开始时
    ("start_exam_play", "exam_start_after"),  # 训练开始后
    ("start_play", "turn_start_after"),  # 回合开始后（剩余 N 回合内的…）
]

# 每种触发时机里"时机词"的正则；从触发句里剥掉它，剩下的就是条件。
BASE_PHRASES: dict[str, list[str]] = {
    "turn_start": [
        r"(?:剩余\d+回合内|最终回合|第\d+)的?回合开始时",
        r"回合开始时",
    ],
    "turn_start_after": [
        r"(?:剩余\d+回合内|最终回合)的?回合开始后",
        r"回合开始后",
    ],
    "turn_end": [
        r"(?:剩余\d+回合内|最终回合)的?回合结束时",
        r"回合结束时",
    ],
    "turn_interval": [r"每\d+回合"],
    "turn_end_interval": [r"每\d+回合的回合结束时", r"每\d+回合"],
    "card_play": [
        r"(?:主动|辅助|偶像固有)技能卡使用时",
        r"(?:集中|好印象|好调|全力|强气|温存|干劲|绝好调|消耗体力减少)效果的技能卡使用时",
        r"技能卡（(?:R|SR|SSR)）使用时",
        r"使用原本的消耗体力值在\d+以上的技能卡时",
        r"技能卡使用时",
        r"^[^，,]{1,20}使用时",  # B8：指定卡名触发（p_card_search-playing-…）
    ],
    "card_played": [
        r"(?:主动|辅助|偶像固有)技能卡使用后",
        r"(?:集中的|感性|理性|元气|体力回复|绝好调|干劲|强气|全力|温存)效果的?技能卡使用后",
        r"技能卡使用后",
        r"^[^，,]{1,20}使用后",  # B8：指定卡名触发
    ],
    "card_play_interval": [
        r"回合内(?:主动|辅助)?每使用\d+次技能卡",
        r"回合内(?:主动|辅助)?技能卡每使用\d+次",
        r"回合内使用过\d+次技能卡时",
        r"技能卡（(?:R|SR|SSR)）每使用\d+次",
        r"(?:集中|好印象|好调|全力|强气|温存|干劲|绝好调)效果的技能卡每使用\d+次",
        r"(?:主动|辅助)?技能卡每使用\d+次",
        r"每使用\d+次技能卡",
    ],
    "card_play_interval_after": [r"(?:主动|辅助)?技能卡每使用\d+次后"],
    "status_gain": [r"直接效果使(?:干劲|好印象|好调|集中|全力值|元气)增加(?:\d+以上)?后"],
    "status_gain_interval": [r"直接效果使(?:干劲|好印象|好调|集中|全力值)增加\d+次时"],
    "stance_change": [
        r"直接效果使(?:强气|温存)存在的时候",
        r"直接效果使指针(?:\d+次)?变更的时候",
        r"(?:全力|强气|温存)存在的时候",
        r"全力被解除后",
    ],
    "stamina_reduce": [r"(?:直接效果使体力减少|(?:技能卡)?花费值使体力减少)时"],
    "buff_consume": [r"使用以强化状态作为花费值的技能卡时"],
    "card_moved_out": [r"技能卡被移动到除外时"],
    "turn_skip": [r"跳过回合时"],
    "exam_start": [
        r"仅限以后的(?:考试|试镜|训练)开始时",
        r"下一个训练开始时",
        r"下次试镜开始时",
        r"考试・试镜开始时",
        r"SP训练开始时",
        r"(?:训练|考试|试镜)开始时",
    ],
    "exam_start_after": [r"训练开始后"],
}

CARD_FILTERS = {
    "主动技能卡": "ActiveSkill",
    "辅助技能卡": "MentalSkill",
    "偶像固有技能卡": "IdolUnique",
}

LESSON_FILTERS = {
    "歌唱": "vocal",
    "舞蹈": "dance",
    "视觉": "visual",
}

# 数值分段里的 examDescriptionType -> 数值字段名
VALUE_KEY = {
    "ExamDescriptionType_CustomizeEffectValue1": "value1",
    "ExamDescriptionType_CustomizeEffectValue2": "value2",
    "ExamDescriptionType_CustomizeEffectValuePercent1": "percent1",
    "ExamDescriptionType_CustomizeEffectValuePercent2": "percent2",
    "ExamDescriptionType_CustomizeEffectCount": "count",
    "ExamDescriptionType_CustomizeTurn": "turn",
    "ExamDescriptionType_CustomizeLessonCountAdd": "lesson_count_add",
}

# 扁平摘要里 value 的取值优先级（第一个非 0 的）
VALUE_PRIORITY = ("value1", "percent1", "count", "value2", "turn")


def clean(text: str) -> str:
    """去富文本标签 / 折叠空白 / 去 YAML 引号残留。"""
    out = WS.sub(" ", TAG.sub("", text or "")).strip()
    if out in ("|", '""', '"'):
        return ""
    if len(out) >= 2 and out.startswith('"') and out.endswith('"'):
        out = out[1:-1].strip()
    return out


def parse_yaml_items(path: Path) -> dict[str, dict]:
    """行解析 gakumasu-diff 的 ProduceItem.yaml（21MB，PyYAML 会吃几个 G）。"""
    items: dict[str, dict] = {}
    cur: dict | None = None
    section = ""
    elem: dict | None = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("- id: "):
            cur = {"id": line[6:].strip(), "descriptions": [], "produceItemEffectIds": []}
            items[cur["id"]] = cur
            section = ""
            elem = None
            continue
        if cur is None:
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 2 and not stripped.startswith("- "):
            key = stripped.split(":", 1)[0]
            section = key
            elem = None
            value = stripped.split(": ", 1)[1] if ": " in stripped else ""
            if key in ("rarity", "produceTriggerId", "planType", "name"):
                cur[key] = value.strip('"')
            continue
        if indent == 2 and stripped.startswith("- "):
            value = stripped[2:]
            if section == "produceDescriptions":
                elem = {}
                cur["descriptions"].append(elem)
                key, _, val = value.partition(": ")
                elem[key.rstrip(":")] = val
            elif section == "produceItemEffectIds":
                cur["produceItemEffectIds"].append(value.strip('"'))
            else:
                elem = {}
            continue
        if indent >= 4 and elem is not None:
            key, _, val = stripped.partition(": ")
            elem[key.rstrip(":")] = val
    return items


def load_master(name: str) -> list[dict]:
    with (SRC / name).open(encoding="utf-8") as f:
        return json.load(f).get("data", [])


def label_tables() -> tuple[dict[str, str], dict[str, str]]:
    """(trigger id -> 中文触发句, examEffectType -> 中文效果名)。"""
    trigger = {}
    for row in load_master("ProduceExamTrigger.json"):
        trigger[row["id"]] = clean("".join(d.get("text", "") for d in row.get("produceDescriptions", [])))
    labels = {row["type"]: row.get("name", "") for row in load_master("ProduceDescriptionExamEffect.json")}
    return trigger, labels


def classify_trigger(trigger_id: str, trigger_text: str = "") -> tuple[str, str, str]:
    """(canonical, family, domain)。"""
    if not trigger_id:
        return "none", "", "none"
    if trigger_id.startswith("p_trigger-"):
        family = trigger_id[len("p_trigger-") :].split("-")[0]
        return f"produce_{family}", family, "produce"
    token = trigger_id.removeprefix("e_trigger-")
    for prefix, canonical in EXAM_TRIGGERS:
        if token.startswith(prefix):
            # exam_turn_timer 里混着两种语义：第 N 回合开始时（考试内）/ 下次试镜开始时（育成期）。
            # 后者不是回合事件，按"下一次考试开始"归类。
            if prefix == "exam_turn_timer" and "回合开始时" not in trigger_text:
                return "exam_start", prefix, "exam"
            return canonical, prefix, "exam"
    return "other", token.split("-")[0], "exam"


def interval_of(trigger_id: str, prefix: str) -> int:
    """从 trigger id 里取"每 N 次"的 N（e_trigger-exam_play_count_interval-4）。"""
    rest = trigger_id.split(prefix, 1)[-1]
    match = re.match(r"-(\d+)", rest)
    return int(match.group(1)) if match else 0


# ---- B8（2026-11-22）：新语法 trigger id 解析 ------------------------------
# 上游 2026-11 新增的触发 id 把**条件直接编码进 id**（例如
# ``e_trigger-exam_play_turn_count_interval-2-remaining_turn-5-…`` =
# 回合内每 2 次技能卡 + 剩余 5 回合内）。本地 2026-09-16 的 masterTrans 触发表里
# 没有这些 id 的中文触发句，旧实现只能记 ``condition_known=False`` 保守不触发；
# 这里从 id 后缀解析出结构化条件（比翻译文本确定，不猜）。
_REMAINING_TURN = re.compile(r"(?:^|-)remaining_turn-(\d+)")
_PARAM_BUFF_UP = re.compile(r"(?:^|-)parameter_buff_up-(\d+)")
_STAMINA_UP_MULT = re.compile(r"(?:^|-)stamina_up_multiple-(\d+)")
_STAMINA_LESS_MULT = re.compile(r"(?:^|-)stamina_less_multiple-(\d+)")
_FULL_POWER_SUM = re.compile(r"(?:^|-)full_power_point_get_sum_up-(\d+)")
_AGGRESSIVE_MIN = re.compile(r"(?:^|-)card_play_aggressive_up-(\d+)")
_LESSON_ID = re.compile(r"(?:^|-)lesson_(vocal|dance|visual)")
# 没有中文触发句、且 id 里带这些条件时，本轮还解析不了 → 保持 condition_known=False：
# 指定卡名触发（需要卡名→卡 id 映射）和手牌指定卡张数（需要手牌卡 id）。
_UNPARSED_TRIGGER_TOKENS = ("p_card_search-playing-", "card_search_count_up-")
_SPECIFIC_CARD_IN_SEARCH = re.compile(r"p_card_search[^-]*(?:-[a-z_0-9]+)*?-p_card-\d")


# ---- B10（2026-11-23）：p_card_search 触发限定结构化解析 --------------------
# 上游把「哪张卡 / 哪个区域几张卡」编码进 trigger id 的 p_card_search 段。语义来源：
#   * masterTrans/ProduceCardSearch.json（描述表：playing=使用时 / target=使用后 /
#     deck_grave=牌堆或弃牌 / deck_all=全部 / lost=除外 / hold=保留 / hand=手牌 /
#     trouble=干扰卡 / r-sr-ssr-legend=R以上 / min_max-4_99=原本消耗体力4以上 /
#     effect_group-visible-exam_*-000=可见效果组 / idol-unique=偶像固有）；
#   * 主数据 ProduceCard.effectGroupIds（卡→效果组，与限定同一套 id）；
#   * BSD-3 参考引擎 gakumas-tools：指定卡名触发用 usedCardBaseId（base id，
#     不限强化）；countCards 区域语义；hold 区我们未建模 → 保守不解析。
_CARD_ID_RE = re.compile(r"p_card-\d{2}-[a-z]+-\d+_\d+")
_SEARCH_MARKER = re.compile(
    r"(?:(?P<neg>not-)?card_search_count_up-(?P<n>\d+)-)?p_card_search-"
)
_ZONE_TOKENS = {
    "playing", "target", "hand", "deck", "grave",
    "deck_grave", "deck_all", "lost", "not_lost", "hold",
}
_PLAY_ZONES = {"playing", "target"}
#: 区域 → 模拟器 tracked 区（hold 未建模 → 不映射，保守不触发）。
#: deck_all = 全部 tracked 区（hold/除外以外都在；参考 countCards 无区域限定 = 全场）。
_ZONE_MAP = {
    "hand": ("hand",),
    "deck": ("deck",),
    "grave": ("discard",),
    "deck_grave": ("deck", "discard"),
    "deck_all": ("deck", "hand", "discard", "excluded"),
    "lost": ("excluded",),
    "not_lost": ("deck", "hand", "discard"),
}
_RARITY_TOKENS = {
    "r-sr-ssr-legend": ("R", "SR", "SSR", "LEGEND"),
    "n-r-sr-ssr": ("N", "R", "SR", "SSR"),
    "ssr": ("SSR",),
    "sr": ("SR",),
    "r": ("R",),
    "n": ("N",),
    "legend": ("LEGEND",),
}
_CATEGORY_TOKENS = {"active_skill": "ActiveSkill", "mental_skill": "MentalSkill"}


def _parse_search_filter(text: str) -> tuple[dict | None, bool]:
    """p_card_search 段去掉区域词后的限定 → (filter dict, unresolved)。"""
    rest = text.strip("-")
    filt: dict = {}
    while rest:
        match = _CARD_ID_RE.match(rest)
        if match:
            filt["kind"] = "card"
            filt["card_id"] = match.group(0)
            rest = rest[match.end():]
            suffix = re.match(r"-(\d+)_(\d+)", rest)
            if suffix:
                # -U_C = upgrade/count 编码；参考引擎按 baseId 匹配（不限强化），
                # upgrade 只作记录，结算按 base id。
                filt["upgrade"] = int(suffix.group(1))
                filt["count"] = int(suffix.group(2))
                rest = rest[suffix.end():]
            rest = rest.lstrip("-")
            continue
        match = re.match(r"effect_group-visible-([a-z_]+)-(\d+)", rest)
        if match:
            filt["kind"] = "effect_group"
            filt["group"] = f"effect_group-visible-{match.group(1)}-{match.group(2)}"
            rest = rest[match.end():].lstrip("-")
            continue
        match = re.match(r"min_max-(\d+)_(\d+)", rest)
        if match:
            filt["kind"] = "cost"
            filt["cost_min"] = int(match.group(1))
            filt["cost_max"] = int(match.group(2))
            rest = rest[match.end():].lstrip("-")
            continue
        if rest.startswith("idol-unique"):
            filt["kind"] = "idol_unique"
            rest = rest[len("idol-unique"):].lstrip("-")
            continue
        matched_category = False
        for token, category in _CATEGORY_TOKENS.items():
            if rest.startswith(token):
                filt["kind"] = "category"
                filt["category"] = category
                rest = rest[len(token):].lstrip("-")
                matched_category = True
                break
        if matched_category:
            continue
        match = re.match(r"plan(\d+)", rest)
        if match:
            filt["kind"] = "plan"
            filt["plan"] = f"Plan{int(match.group(1))}"
            rest = rest[match.end():].lstrip("-")
            continue
        if rest.startswith("trouble"):
            filt["trouble"] = True
            rest = rest[len("trouble"):].lstrip("-")
            continue
        matched_rarity = False
        for token, rarities in _RARITY_TOKENS.items():
            if rest.startswith(token):
                filt["rarities"] = list(rarities)
                rest = rest[len(token):].lstrip("-")
                matched_rarity = True
                break
        if matched_rarity:
            continue
        match = re.match(r"lesson_(vocal|dance|visual)", rest)
        if match:
            # 训练/回合属性限定由 B8 的 lesson_filter 处理，这里跳过。
            rest = rest[match.end():].lstrip("-")
            continue
        match = re.match(r"\d+(?:_\d+)?", rest)
        if match:
            # 张数 / upgrade_count（无卡 id = 任意卡），结算不需要。
            rest = rest[match.end():].lstrip("-")
            continue
        return (filt or None), True
    return (filt or None), False


def parse_card_search(trigger_id: str) -> tuple[dict | None, dict | None, bool]:
    """解析 trigger id 里的 p_card_search 限定（B10）。

    返回 ``(play_filter, zone_count, unresolved)``：

    * ``play_filter``：出牌触发（playing/target）的卡限定 →
      ``{kind: any/card/idol_unique/effect_group/cost, ...}``；
    * ``zone_count``：区域张数条件 → ``{zones, min, negate, filter}``
      （``not-card_search_count_up-N`` = 张数 < N）；
    * ``unresolved``：还有解析不了的限定（hold 区未建模 / 未知词）→
      调用方保持 ``trigger_known=False`` 保守不触发。
    """
    if not trigger_id or "p_card_search" not in trigger_id:
        return None, None, False
    markers = list(_SEARCH_MARKER.finditer(trigger_id))
    if not markers:
        return None, None, False
    play_filter: dict | None = None
    zone_count: dict | None = None
    unresolved = False
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(trigger_id)
        piece = trigger_id[marker.end():end].strip("-")
        tokens = piece.split("-") if piece else []
        zone = ""
        rest_tokens: list[str] = []
        for token in tokens:
            if token in _ZONE_TOKENS and not zone:
                zone = token
            else:
                rest_tokens.append(token)
        filt, bad = _parse_search_filter("-".join(rest_tokens))
        unresolved = unresolved or bad
        if not zone:
            unresolved = True
            continue
        if zone in _PLAY_ZONES:
            if play_filter is not None:
                unresolved = True
            # 空限定（playing-0_1 = 任意技能卡）= 无额外限定，落回 None
            # （card_play 触发本身就隐含"打出了一张卡"）。
            play_filter = filt if filt else None
            continue
        if zone == "hold" or zone not in _ZONE_MAP:
            # 保留区未建模（RULES_REFERENCE §6）：不能当 0 张算，保守不解析。
            unresolved = True
            continue
        if marker.group("n") is None:
            # 没有 card_search_count_up 前缀的区域段（育成期「获得技能卡」的搜索目标，
            # 如 p_trigger-get_produce_card-…-p_card_search-deck_all）：不是张数条件，
            # 考试事件里也不会触发，跳过（不算 unresolved）。
            continue
        if zone_count is not None:
            unresolved = True
        zone_count = {
            "zones": list(_ZONE_MAP[zone]),
            "min": int(marker.group("n")),
            "negate": bool(marker.group("neg")),
            "filter": filt,
        }
    return play_filter, zone_count, unresolved


def trigger_id_has_unparsed_condition(trigger_id: str) -> bool:
    """触发 id 里是否还有建模不了的卡限定（B10 起按结构化解析判定）。

    指定卡名 / 效果组 / 偶像固有 / 费用 / 区域张数（tracked 区）都能解析；
    只剩 **hold（保留）区** 与未知词 → True（保守不触发）。
    """
    return parse_card_search(trigger_id)[2]


#: 区域张数条件的中文子句（解析成 zone_count 后从 condition 里剥掉，避免
#: evaluate_condition 认不出整句而拒绝触发）。
_ZONE_COND_RES = (
    re.compile(r"(?:牌堆或弃牌|除外|手牌|保留)中的?[^，,]{0,14}?在\d+张(?:以上|以下)的时候"),
    re.compile(r"技能卡（R以上）在\d+张(?:以上|以下)的时候"),
)


def strip_zone_condition(condition: str) -> str:
    body = condition or ""
    for pattern in _ZONE_COND_RES:
        body = pattern.sub("", body)
    body = re.sub(r"[，,、\s]+$", "", body)
    body = re.sub(r"^[，,、\s]+", "", body)
    return body


def _permil_to_percent(value: int) -> str:
    """800 → "80"（上游 percent 字段 ×10 编码）。"""
    percent = value / 10
    return str(int(percent)) if percent == int(percent) else f"{percent:g}"


def parse_exam_trigger_id(trigger_id: str, family: str) -> tuple[dict, list[str], bool]:
    """从 ``e_trigger-`` 新语法 id 解析参数/条件（B8）。

    返回 ``(params, conditions, complete)``。``complete=False`` = id 里还有解析不了的
    条件（指定卡名 / 手牌张数）→ 调用方保持 ``condition_known=False``，保守不触发。
    """
    if not trigger_id.startswith("e_trigger-") or not family:
        return {}, [], False
    token = trigger_id.removeprefix("e_trigger-")
    rest = token.removeprefix(family) if family else token
    params: dict = {}
    conditions: list[str] = []
    if family in (
        "exam_play_turn_count_interval",
        "exam_play_count_interval",
        "exam_play_count_interval_after",
        "exam_review_up_interval",
        "exam_aggressive_up_interval",
    ):
        match = re.match(r"-(\d+)", rest)
        if match:
            params["interval"] = int(match.group(1))
        if family == "exam_review_up_interval":
            params["status"] = "impression"
        elif family == "exam_aggressive_up_interval":
            params["status"] = "aggressive"
    match = _REMAINING_TURN.search(rest)
    if match:
        params["remaining_turns"] = int(match.group(1))
    match = _PARAM_BUFF_UP.search(rest)
    if match:
        conditions.append(f"好调在{int(match.group(1))}回合以上")
    for regex, template in (
        (_STAMINA_UP_MULT, "体力在{}%以上"),
        (_STAMINA_LESS_MULT, "体力在{}%以下"),
    ):
        match = regex.search(rest)
        if match:
            conditions.append(template.format(_permil_to_percent(int(match.group(1)))))
    match = _FULL_POWER_SUM.search(rest)
    if match:
        conditions.append(f"累计全力值在{int(match.group(1))}以上")
    match = _AGGRESSIVE_MIN.search(rest)
    if match:
        conditions.append(f"干劲在{int(match.group(1))}以上")
    match = _LESSON_ID.search(rest)
    if match:
        params["lesson_filter"] = match.group(1)
    complete = not parse_card_search(trigger_id)[2]
    return params, conditions, complete


def strip_base(text: str, family: str) -> str:
    """从触发句里剥掉时机词，返回条件部分。"""
    body = text.strip().rstrip("，,")
    for pattern in BASE_PHRASES.get(family, []):
        new = re.sub(pattern, "", body, count=1)
        if new != body:
            body = new
            break
    # 【仅限XX训练・XX回合】/【仅限SP训练】已经进 trigger_params.lesson_filter，不再重复算条件
    body = re.sub(r"【仅限(?:歌唱|舞蹈|视觉)(?:训练|回合)[^】]*】", "", body)
    body = re.sub(r"【仅限SP训练】", "", body)
    body = re.sub(r"^[，,、\s的]+", "", body)
    body = re.sub(r"[，,、\s的]+$", "", body)
    return body


def trigger_params(trigger_id: str, canonical: str, family: str, trigger_text: str) -> dict:
    """从触发 id / 触发句里抽结构化参数（interval / turn / status / card_filter …）。"""
    params: dict = {}
    if canonical == "card_play_interval":
        params["interval"] = interval_of(trigger_id, family)
        params["interval_scope"] = "turn" if family == "exam_play_turn_count_interval" else "exam"
    elif canonical == "card_play_interval_after":
        params["interval"] = interval_of(trigger_id, family)
        params["interval_scope"] = "exam"
    elif canonical in ("turn_start", "turn_end", "turn_start_after"):
        m = re.search(r"第(\d+)回合", trigger_text)
        if m:
            params["turn"] = int(m.group(1))
        m = re.search(r"剩余(\d+)回合内", trigger_text)
        if m:
            params["remaining_turns"] = int(m.group(1))
        if "最终回合" in trigger_text:
            params["final_turn"] = 1
    elif canonical == "turn_interval":
        m = re.search(r"每(\d+)回合", trigger_text)
        if m:
            params["every"] = int(m.group(1))
    elif canonical == "status_gain":
        m = re.search(r"直接效果使(干劲|好印象|好调|集中|全力值|元气)增加", trigger_text)
        if m and m.group(1) in STACK_KEYS:
            params["status"] = STACK_KEYS[m.group(1)]
        m = re.search(r"直接效果使.+?增加(\d+)以上后", trigger_text)
        if m:
            params["status_min"] = int(m.group(1))
    elif canonical == "status_gain_interval":
        m = re.search(r"直接效果使(干劲|好印象|好调|集中|全力值)增加(\d+)次时", trigger_text)
        if m and m.group(1) in STACK_KEYS:
            params["status"] = STACK_KEYS[m.group(1)]
            params["status_count"] = int(m.group(2))

    # 卡牌类别过滤（"主动技能卡使用时" 之类）
    for text, category in CARD_FILTERS.items():
        if text in trigger_text:
            params["card_filter"] = category
            break
    # 训练 / 回合属性过滤（"【仅限歌唱训练・歌唱回合】" 之类）
    m = re.search(r"【仅限(歌唱|舞蹈|视觉)(?:训练|回合)", trigger_text)
    if m:
        params["lesson_filter"] = LESSON_FILTERS[m.group(1)]
    elif "【仅限SP训练】" in trigger_text:
        params["lesson_filter"] = "sp"
    return params


def extract_effects(
    local_descs: list[dict],
    yaml_descs: list[dict],
    zh_text: str,
) -> list[dict]:
    """抽效果：每个 ``ProduceExamEffectType`` 分段开一个效果，数值段按顺序挂上去。

    以**本地** master 的分段为准（数值取本地化后的显示文本，和游戏里看到的一致）；
    yaml 只用来判断"这一段是不是触发/条件部分"（带 ``originProduceExamTriggerId``）。
    两边分段数可能差 1 条（实测 1067/1068 对齐），对不齐的条目退回纯 yaml 口径。
    """
    if len(local_descs) != len(yaml_descs):
        return _extract_effects_yaml(yaml_descs, zh_text)

    effects: list[dict] = []
    current: dict | None = None
    for desc, yaml_desc in zip(local_descs, yaml_descs, strict=True):
        # 带 originProduceExamTriggerId 的分段属于"触发/条件"部分（例如条件里的
        # "集中≥5" 只是一个 ExamLessonBuff 标签，不是效果），effect 段没有 trigger id。
        if (yaml_desc.get("originProduceExamTriggerId") or "").strip('"'):
            current = None
            continue
        if (desc.get("produceDescriptionType") or "").endswith("_ProduceExamEffectType"):
            etype = (desc.get("examEffectType") or "").strip('"')
            if etype.endswith("_Unknown"):
                continue
            current = {"type": etype, "values": {}, "text": ""}
            effects.append(current)
            current["text"] += clean(desc.get("text", ""))
            continue
        if current is None:
            continue
        marker = (desc.get("examDescriptionType") or "").strip('"')
        raw = clean(desc.get("text", ""))
        key = VALUE_KEY.get(marker)
        if key is None:
            current["text"] += raw
            continue
        if not raw:
            current["values"].setdefault(key, None)
            continue
        try:
            current["values"].setdefault(key, int(float(raw)))
        except ValueError:
            current["text"] += raw
    return _finish_effects(effects, zh_text)


def _extract_effects_yaml(yaml_descs: list[dict], zh_text: str) -> list[dict]:
    """纯 yaml 口径的兜底（本地分段和 yaml 段数对不上时用）。"""
    effects: list[dict] = []
    current: dict | None = None
    for desc in yaml_descs:
        if (desc.get("originProduceExamTriggerId") or "").strip('"'):
            current = None
            continue
        etype = (desc.get("examEffectType") or "").strip('"')
        if etype and not etype.endswith("_Unknown"):
            current = {"type": etype, "values": {}, "text": ""}
            effects.append(current)
            current["text"] += clean(desc.get("text", ""))
            continue
        if current is None:
            continue
        marker = (desc.get("examDescriptionType") or "").strip('"')
        raw = clean(desc.get("text", ""))
        key = VALUE_KEY.get(marker)
        if key is None:
            current["text"] += raw
            continue
        if not raw:
            current["values"].setdefault(key, None)
            continue
        try:
            current["values"].setdefault(key, int(float(raw)))
        except ValueError:
            current["text"] += raw
    return _finish_effects(effects, zh_text)


# ---- B8（2026-11-22）：依赖换算式效果 --------------------------------------
# 卡面常见「X 的 N% 数值变为 Y」：源效果段只带 percent1、文本以「X的%数值变为」结尾，
# 紧随其后是空 values 的目标效果（打分上升 / 元气增加 / …）。把源层的 percent1
# 挂到目标上（``depends_on`` + ``values.percent1``），源段标 ``role=conversion_source``。
CONVERSION_SOURCES = {
    "好印象": "impression",
    "元气": "vitality",
    "干劲": "aggressive",
    "集中": "focus",
    "累计全力值": "full_power_point_total",
    "全力值": "full_power_point",
    "消耗过的体力": "consumed_stamina_total",
    # 好调在模拟器里是「剩余回合数」而非可换算的量 → 本轮不建模（保持 no-op，不猜）
}
CONVERSION_TARGET_TYPES = frozenset(
    {"ExamLesson", "ExamReview", "ExamBlock", "ExamLessonBuff", "ExamCardPlayAggressive", "ExamParameterBuff"}
)
_CONVERSION_SOURCE_TEXT = re.compile(
    r"^(?P<src>" + "|".join(CONVERSION_SOURCES) + r")的%数值变为"
)
_ZERO_TEXT = re.compile(r"^(?P<src>" + "|".join(CONVERSION_SOURCES) + r")变为0$")


def annotate_effects(effects: list[dict], zh_text: str) -> list[dict]:
    """B8：把依赖换算 / 最大体力百分比 / 归零段的语义标进 effects（不改 effect 顺序）。

    * 源段（``percent1`` + 文本「X的%数值变为」）→ 找紧随其后、空 values 的目标效果，
      写 ``depends_on`` + ``values.percent1``；源段 ``values.percent1`` 移除并标
      ``role="conversion_source"``（它只是系数，不是直接加层数）。
    * 「最大体力的 N% 数值变为体力消耗/回复」：percent 段可能挂在前一个效果上
      （实测 pitem_02-3-076-0）→ 挪到体力效果上记 ``percent_max``；本地化描述兜底。
    * 「X变为0」的空效果 → ``zero_stack``（结算时把对应层数清零，不猜成加 0 层）。
    """
    for index, effect in enumerate(effects):
        text = (effect.get("text") or "").strip()
        values = effect.setdefault("values", {})
        percent = values.get("percent1")
        if percent:
            match = _CONVERSION_SOURCE_TEXT.match(text)
            if match:
                source = CONVERSION_SOURCES.get(match.group("src"), "")
                if source:
                    for target in effects[index + 1 : index + 3]:
                        if target.get("type") not in CONVERSION_TARGET_TYPES:
                            continue
                        if target.get("values"):
                            continue
                        target["depends_on"] = source
                        target["values"] = {"percent1": int(percent)}
                        effect["role"] = "conversion_source"
                        values.pop("percent1", None)
                        break
            # 最大体力的 N% 被挂到前一个效果上（文本里「…数值变为」是标志）
            if "数值变为" in text:
                for target in effects[index + 1 : index + 3]:
                    if target.get("type") not in ("ExamStaminaReduceFix", "ExamStaminaRecoverFix"):
                        continue
                    if target.get("values"):
                        continue
                    target["percent_max"] = int(percent)
                    effect["role"] = "stamina_percent_source"
                    values.pop("percent1", None)
                    break
        zero = _ZERO_TEXT.match(text)
        if zero and not values:
            source = CONVERSION_SOURCES.get(zero.group("src"), "")
            if source:
                effect["zero_stack"] = source
    # 本地化兜底：数值段落在效果段之前时 percent 会丢（如 pitem_00-3-119-0）。
    for kind, effect_type in (
        ("体力消耗", "ExamStaminaReduceFix"),
        ("体力回复", "ExamStaminaRecoverFix"),
    ):
        match = re.search(rf"最大体力的(\d+)%数值变为{kind}", zh_text)
        if not match:
            continue
        for effect in effects:
            if effect.get("type") != effect_type:
                continue
            if effect.get("values") or effect.get("percent_max"):
                continue
            effect["percent_max"] = int(match.group(1))
            break
    return effects


# B9（2026-11-22）：P 道具的「（训练内N次）」次数上限在描述文本里（yaml 的
# ``limit`` 没有单独的本地化列）。没有这个上限，持续倍率类效果会在每回合重复
# 触发、把分数算爆，所以从中文/日文描述解析出来当记录级 ``max_uses``。
_LIMIT_PATTERNS = [
    re.compile(r"（训练内(\d+)次）"),
    re.compile(r"（培育中(\d+)次）"),
    re.compile(r"（レッスン内(\d+)回）"),
    re.compile(r"（プロデュース中(\d+)回）"),
    re.compile(r"（(\d+)次）"),
    re.compile(r"（(\d+)回）"),
]


def parse_text_max_uses(*texts: str) -> int:
    """从道具描述里解析可用次数上限；没有就返回 0（不限）。"""
    for pattern in _LIMIT_PATTERNS:
        for text in texts:
            match = pattern.search(text or "")
            if match:
                return int(match.group(1))
    return 0


def annotate_modifier_effects(effects: list[dict]) -> None:
    """B9：给持久倍率 / modifier 类效果段标 ``target`` / ``duration``。

    只标有语义的分类（``classify_effect_target`` 认不出的保持不标 = no-op）；
    数值仍留在 ``values`` 里，由 ``sim/p_items.py::effect_value`` 按 target 取列。
    """
    for effect in effects:
        target = classify_effect_target(effect.get("type", ""), effect.get("text", ""))
        if not target:
            continue
        effect["target"] = target
        duration = effect_duration(effect, target)
        if duration:
            effect["duration"] = duration


def _finish_effects(effects: list[dict], zh_text: str) -> list[dict]:
    for eff in effects:
        eff["type"] = eff["type"].replace("ProduceExamEffectType_", "")
        eff["values"] = {k: v for k, v in eff["values"].items() if v is not None}
        count = eff["values"].get("count")
        eff["max_uses"] = 0
        if count and re.search(rf"（{count}次）", zh_text):
            # 只有中文描述里真的写了 "（N次）" 才算次数上限；
            # "技能卡使用数追加+1" 这类 count 是数值本身。
            eff["max_uses"] = count
    annotate_modifier_effects(effects)
    return annotate_effects(effects, zh_text)

def primary_value(effects: list[dict]) -> tuple[int | None, str]:
    for eff in effects:
        for key in VALUE_PRIORITY:
            value = eff["values"].get(key)
            if value:
                return int(value), key
    return None, ""


def primary_effect(effects: list[dict]) -> dict | None:
    """主效果 = 第一个带数值的效果；都没数值就取第一个。"""
    for eff in effects:
        if any(eff["values"].get(k) for k in VALUE_PRIORITY):
            return eff
    return effects[0] if effects else None


def render(descriptions: list[dict]) -> str:
    return "".join(clean(d.get("text", "")) for d in descriptions)


def produce_trigger_text(zh_text: str) -> str:
    """育成期（p_trigger-*）道具没有触发表，时机词就在描述开头。

    取第一个逗号前的那一小截；只有它看起来像"什么时候"才用（含 时/后/每/开始/结束），
    否则留空（例如"初始P点数+50授课消耗的体力会…"根本没有触发句）。
    """
    head, sep, _ = zh_text.partition("，")
    if not sep or len(head) > 24:
        return ""
    if any(key in head for key in ("时", "后", "每", "开始", "结束")):
        return head + "，"
    return ""


def load_i18n_names(path: Path = I18N_NAMES) -> dict[str, str]:
    """读仓库里的自译表（``data/i18n/translation_new.json``）：日文名 → 中文名。

    只用于「本地 masterTrans 没有、yaml 才有的新 id」的**卡名**（描述不译、不猜）。
    文件缺失/格式不对 → 空表（重建时退化成 yaml 日文名并在记录里标记，不报错）。
    """
    if not path.is_file():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    names: dict[str, str] = {}
    if isinstance(entries, Mapping):
        for jp, cn in entries.items():
            if jp and isinstance(cn, str) and cn:
                names[str(jp)] = cn
    elif isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            jp = entry.get("jp")
            cn = entry.get("cn")
            if isinstance(jp, str) and jp and isinstance(cn, str) and cn:
                names[jp] = cn
    return names


def chinese_name(japanese: str, names: Mapping[str, str]) -> tuple[str, str]:
    """(显示名, 来源)。强化变体名以 ``+`` 结尾：用基础名的译名 + ``+``。

    译表里没有的保留日文名，来源记 ``"ja"``（明确标记，不臆造）。
    """
    if not japanese:
        return "", "missing"
    if japanese in names:
        return names[japanese], "translation_new.json"
    if japanese.endswith("+") and japanese[:-1] in names:
        return names[japanese[:-1]] + "+", "translation_new.json"
    return japanese, "ja"


# ---- B10（2026-11-23）：ExamCardCreateId 生成卡标注 -------------------------
# 生成卡的卡名/目标区只在描述文本里（effect.values 为空）。语义来源：
#   * 中文「X向手牌中生成 / 向牌堆的最顶部中生成 / 向弃牌中生成」；
#     日文「Xを手札に生成 / を山札の一番上に生成 / を捨札に生成」；
#   * BSD-3 参考引擎 p_items.csv DSL 交叉验证：勝利をその手に=addCardToHand(111)、
#     迷子のお呼び出し=addCardToHand(131)、麻央にぴったし=addCardToHand(421)、
#     雨上がりの女神=addCardToTopOfDeck(23)（眠気）、H.I.F応援棒=
#     addRandomBasicCardToDeckAtRandom(22-countCards[deck])（随机 → RNG 未知，不实现）。
# 卡名→(id, upgrade) 用 card_meta 索引（中文精确 + 日文别名，最长后缀匹配）。
_CREATE_ZONES_ZH = (
    ("向手牌中生成", "hand"),
    ("向牌堆的最顶部中生成", "deck_top"),
    ("向弃牌中生成", "discard"),
)
_CREATE_ZONES_JA = (
    ("を手札に生成", "hand"),
    ("を山札の一番上に生成", "deck_top"),
    ("を捨札に生成", "discard"),
)
_RANDOM_DECK_TARGET_ZH = re.compile(r"达到(\d+)张")
_RANDOM_DECK_TARGET_JA = re.compile(r"(\d+)枚になるように")


def annotate_create_effects(effects: list[dict], zh_text: str, ja_text: str) -> None:
    """给 ExamCardCreateId 段标注 ``create``（确定卡）/ ``create_random``（随机，不实现）。"""
    index = card_meta_index()
    names = index.names()
    for eff in effects:
        if eff.get("type") != "ExamCardCreateId":
            continue
        annotated = False
        for text, zones in ((zh_text, _CREATE_ZONES_ZH), (ja_text, _CREATE_ZONES_JA)):
            if not text:
                continue
            for phrase, zone in zones:
                pos = text.find(phrase)
                if pos < 0:
                    continue
                prefix = text[:pos]
                best = ""
                for candidate in names:
                    if prefix.endswith(candidate) and len(candidate) > len(best):
                        best = candidate
                if not best:
                    continue
                meta = index.meta(best)
                if meta is None or not meta.card_id:
                    continue
                eff["create"] = {
                    "card_id": meta.card_id,
                    "upgrade": meta.upgrade,
                    "zone": zone,
                    "count": 1,
                }
                annotated = True
                break
            if annotated:
                break
        if annotated:
            continue
        # 随机基础卡（H.I.F应援棒）：卡选择/位置是考试 RNG 入口之一，真机流未知 →
        # 只记录语义（牌堆补到 N 张），保持 no-op（与 exam_risk 的事前检测同口径）。
        text = zh_text or ja_text
        if "随机" in text and ("基础" in text or "基本" in text):
            match = _RANDOM_DECK_TARGET_ZH.search(zh_text or "") or _RANDOM_DECK_TARGET_JA.search(ja_text or "")
            if match:
                eff["create_random"] = {
                    "kind": "basic_to_deck_count",
                    "deck_target": int(match.group(1)),
                }


def build_record(
    *,
    item_id: str,
    local_descs: list[dict] | None,
    yaml_item: dict,
    name: str,
    trigger_cn: Mapping[str, str],
    effect_labels: Mapping[str, str],
) -> dict:
    """组装一条 catalog 记录（本地 1068 条与 yaml 新增 47 条共用一套口径）。

    ``local_descs=None`` 表示本地 masterTrans 没有这一行：效果退回纯 yaml 口径
    （``_extract_effects_yaml``），中文描述缺失（``text_zh=""``，日文留在 ``text_ja``）。
    """
    yaml_descs = yaml_item.get("descriptions", [])
    zh_text = render(local_descs) if local_descs is not None else ""
    ja_text = render(yaml_descs)

    desc_triggers = [d.get("originProduceExamTriggerId", "").strip('"') for d in yaml_descs]
    desc_triggers = [t for t in desc_triggers if t]
    if desc_triggers:
        trigger_id = desc_triggers[0]
        trigger_text = trigger_cn.get(trigger_id, "")
    else:
        trigger_id = yaml_item.get("produceTriggerId", "").strip('"')
        trigger_text = produce_trigger_text(zh_text)

    canonical, family, domain = classify_trigger(trigger_id, trigger_text)
    condition = strip_base(trigger_text, canonical) if domain == "exam" else ""
    params = trigger_params(trigger_id, canonical, family, trigger_text)
    id_params, id_conditions, id_complete = parse_exam_trigger_id(trigger_id, family)
    for key, value in id_params.items():
        if value not in (None, "", 0):
            params[key] = value
    # B10：p_card_search 限定结构化解析（指定卡名/偶像固有/效果组/费用/区域张数）。
    # 解析不了的（hold 保留区未建模/未知词）保持 trigger_known=False 保守不触发。
    play_filter, zone_count, search_unresolved = parse_card_search(trigger_id)
    if domain == "exam" and trigger_id:
        if trigger_text:
            condition_known = True
            if not condition and id_conditions:
                condition = "，".join(id_conditions)
        else:
            condition_known = bool(id_complete and canonical not in ("none", "other"))
            condition = "，".join(id_conditions)
    else:
        condition_known = True
    # 中文触发句缺失的考试类触发 id（本地 masterTrans 快照早于该 id）→ 条件未知。
    # 不能当成"无条件"结算（会把带条件的道具凭空触发），由 sim/p_items.py 保守跳过。
    if not condition_known:
        condition = ""
    elif zone_count is not None:
        # 区域张数已结构化（zone_count），从条件文本里剥掉，避免整句认不出拒触发。
        condition = strip_zone_condition(condition)
    # 育成期（produce domain）触发的 p_card_search 是「获得哪张卡」的搜索目标，
    # 不是考试事件限定；保守检查只对考试域生效。
    trigger_known = not (search_unresolved and domain == "exam")
    if play_filter is not None:
        params["play_filter"] = play_filter
        if play_filter.get("kind") == "idol_unique":
            # 结构化限定取代类别标签：卡表 category 词表没有 IdolUnique，
            # 留着旧标签会在 _trigger_matches 里把固有卡触发永远挡掉。
            params.pop("card_filter", None)
    if zone_count is not None:
        params["zone_count"] = zone_count
    if local_descs is None:
        effects = _extract_effects_yaml(yaml_descs, zh_text)
    else:
        effects = extract_effects(local_descs, yaml_descs, zh_text)
    for eff in effects:
        eff["label"] = effect_labels.get(f"ProduceExamEffectType_{eff['type']}", "")
    # B10：生成卡（ExamCardCreateId）的卡名/目标区标注（确定卡 create / 随机 create_random）。
    annotate_create_effects(effects, zh_text, ja_text)
    primary = primary_effect(effects)
    value, unit = primary_value(effects)

    record = {
        "id": item_id,
        "name": name,
        "rarity": RARITY.get(yaml_item.get("rarity", ""), "unknown"),
        "trigger": canonical,
        "trigger_family": family,
        "trigger_id": trigger_id,
        "trigger_text": trigger_text,
        "trigger_domain": domain,
        "trigger_params": params,
        "condition": condition,
        "effect_type": primary["type"] if primary else "unknown",
        "effect_label": primary["label"] if primary else "",
        "effect_text": primary["text"] if primary else "",
        "value": value,
        "value_unit": unit,
        # B9：描述里的「（训练内N次）/（レッスン内N回）」是整条道具的触发上限；
        # 效果段的 count 上限（B6 口径）取较大值兜底。
        "max_uses": max(
            parse_text_max_uses(zh_text, ja_text),
            max((e["max_uses"] for e in effects), default=0),
        ),
        "effects": effects,
        "text_zh": zh_text,
        "text_ja": ja_text,
    }
    if not condition_known:
        record["condition_known"] = False
    if not trigger_known:
        record["trigger_known"] = False
    return record


def build() -> dict:
    local = load_master("ProduceItem.json")
    yaml_items = parse_yaml_items(YAML)
    trigger_cn, effect_labels = label_tables()
    names = load_i18n_names()

    local_ids = {row["id"] for row in local}
    missing = [row["id"] for row in local if row["id"] not in yaml_items]
    new_ids = [item_id for item_id in yaml_items if item_id not in local_ids]

    records = [
        build_record(
            item_id=row["id"],
            local_descs=row.get("produceDescriptions", []),
            yaml_item=yaml_items.get(row["id"], {}),
            name=row.get("name", ""),
            trigger_cn=trigger_cn,
            effect_labels=effect_labels,
        )
        for row in local
    ]
    i18n_ja_names = 0
    for item_id in new_ids:
        yaml_item = yaml_items[item_id]
        name, name_source = chinese_name(yaml_item.get("name", ""), names)
        if name_source == "ja":
            i18n_ja_names += 1
        record = build_record(
            item_id=item_id,
            local_descs=None,
            yaml_item=yaml_item,
            name=name,
            trigger_cn=trigger_cn,
            effect_labels=effect_labels,
        )
        record["i18n_name_source"] = name_source
        record["i18n_text_source"] = "ja"
        records.append(record)

    triggers = Counter(r["trigger"] for r in records)
    effects_all = Counter(e["type"] for r in records for e in r["effects"])
    stats = {
        "count": len(records),
        "rarity": dict(Counter(r["rarity"] for r in records)),
        "trigger_domain": dict(Counter(r["trigger_domain"] for r in records)),
        "trigger": dict(triggers),
        "trigger_family": dict(Counter(r["trigger_family"] for r in records)),
        "trigger_kinds": len(triggers),
        "effect_types": dict(effects_all),
        "effect_type_kinds": len(effects_all),
        "primary_effect_type": dict(Counter(r["effect_type"] for r in records)),
        "items_with_effects": sum(1 for r in records if r["effects"]),
        "items_with_value": sum(1 for r in records if r["value"]),
        "items_with_condition": sum(1 for r in records if r["condition"]),
        "items_with_max_uses": sum(1 for r in records if r["max_uses"]),
        "items_missing_yaml": len(missing),
        "items_missing_trigger_text": sum(1 for r in records if r["trigger_id"] and not r["trigger_text"]),
        # B7：本地 masterTrans（2026-09-16）之外的新 id 与中文缺口，全部显式计数。
        "items_local_master": len(local),
        "items_from_yaml": len(new_ids),
        "items_i18n_name_ja": i18n_ja_names,
        "items_i18n_text_ja": len(new_ids),
        "items_condition_unknown": sum(1 for r in records if r.get("condition_known") is False),
        # B8：指定卡名触发/手牌张数（没有卡名→id 映射，不能建模 → 保守跳过）。
        "items_trigger_unknown": sum(1 for r in records if r.get("trigger_known") is False),
        # B10：p_card_search 限定结构化（出牌卡限定 / 区域张数）与生成卡标注。
        "items_play_filter": sum(1 for r in records if r["trigger_params"].get("play_filter")),
        "items_zone_count": sum(1 for r in records if r["trigger_params"].get("zone_count")),
        "effects_create_card": sum(1 for r in records for e in r["effects"] if e.get("create")),
        "effects_create_random": sum(1 for r in records for e in r["effects"] if e.get("create_random")),
        # B8：新语法 id 解析 + 依赖换算/最大体力百分比/归零段的结构化计数。
        "items_trigger_id_parsed": sum(
            1
            for r in records
            if r["trigger_domain"] == "exam"
            and r["trigger_id"]
            and not r["trigger_text"]
            and r.get("condition_known", True)
        ),
        "effects_depends_on": sum(
            1 for r in records for e in r["effects"] if e.get("depends_on")
        ),
        "effects_percent_max": sum(
            1 for r in records for e in r["effects"] if e.get("percent_max")
        ),
        "effects_zero_stack": sum(
            1 for r in records for e in r["effects"] if e.get("zero_stack")
        ),
        # B9：持久倍率 / modifier 类效果（target + duration）与文本次数上限。
        "effects_modifier": sum(1 for r in records for e in r["effects"] if e.get("target")),
        "effects_modifier_targets": dict(
            Counter(e["target"] for r in records for e in r["effects"] if e.get("target"))
        ),
        "items_with_modifier": sum(
            1 for r in records if any(e.get("target") for e in r["effects"])
        ),
        "items_text_limit": sum(
            1
            for r in records
            if parse_text_max_uses(r["text_zh"], r["text_ja"]) > 0
        ),
    }
    return {
        "source": {
            "master": "masterTrans/ProduceItem.json",
            "master_version": "2026-09-16（1068 件）",
            "master_size": "8.69MB",
            "structured": "data/cache/ProduceItem.yaml (vertesan/gakumasu-diff，1115 件)",
            "name_i18n": "data/i18n/translation_new.json（新增 47 条只补卡名；描述仍是日文）",
            "trigger_labels": "masterTrans/ProduceExamTrigger.json",
            "effect_labels": "masterTrans/ProduceDescriptionExamEffect.json",
        },
        "stats": stats,
        "items": records,
    }


def report(payload: dict) -> None:
    stats = payload["stats"]
    print(f"P 道具总数: {stats['count']}  稀有度: {stats['rarity']}")
    print(f"触发域: {stats['trigger_domain']}")
    print(f"\ntrigger 种类: {stats['trigger_kinds']}")
    for name, count in sorted(stats["trigger"].items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {name}")
    print(f"\ntrigger_family 种类: {len(stats['trigger_family'])}")
    print(f"效果类型种类（分段级）: {stats['effect_type_kinds']}")
    for name, count in sorted(stats["effect_types"].items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {count:5d}  {name}")
    print("\n主效果类型 top12:")
    for name, count in sorted(stats["primary_effect_type"].items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {count:5d}  {name}")
    print(
        f"\n有分段效果 {stats['items_with_effects']} / 有数值 {stats['items_with_value']} / "
        f"有条件 {stats['items_with_condition']} / 有次数上限 {stats['items_with_max_uses']}"
    )
    print(f"trigger 中文缺失 {stats['items_missing_trigger_text']} / yaml 缺 id {stats['items_missing_yaml']}")
    print(
        f"本地 masterTrans {stats['items_local_master']} 件 + yaml 新增 {stats['items_from_yaml']} 件 = "
        f"{stats['count']} 件；其中名字用自译表 {stats['items_from_yaml'] - stats['items_i18n_name_ja']} / "
        f"日文 {stats['items_i18n_name_ja']}，描述日文（中文缺失）{stats['items_i18n_text_ja']}；"
        f"条件未知（保守不触发）{stats['items_condition_unknown']} 件；"
        f"触发未知（指定卡/手牌，保守不触发）{stats['items_trigger_unknown']} 件"
    )
    print(
        f"B8：从新语法 id 解析出条件 {stats['items_trigger_id_parsed']} 件；"
        f"依赖换算目标 {stats['effects_depends_on']} 段 / 最大体力百分比 {stats['effects_percent_max']} 段 / "
        f"归零段 {stats['effects_zero_stack']} 段"
    )
    print(
        f"B9：持久倍率/modifier 效果 {stats['effects_modifier']} 段"
        f"（{stats['items_with_modifier']} 件道具）；描述里带次数上限 {stats['items_text_limit']} 件"
    )
    for name, count in sorted(
        stats["effects_modifier_targets"].items(), key=lambda kv: -kv[1]
    ):
        print(f"  {count:5d}  {name}")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not YAML.exists():
        print(f"缺少 {YAML}（需要 gakumasu-diff 的 ProduceItem.yaml）")
        return 1
    payload = build()
    report(payload)
    if "--check" not in argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n写入 {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
