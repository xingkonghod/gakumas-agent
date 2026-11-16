"""解析 ProduceItem 主数据，产出 data/knowledge/p_items.json（P 道具 / 被动道具）。

数据来源：
  * 中文：``masterTrans/ProduceItem.json``（游戏本地解包 master，2026-09-16 版）
    —— 只有 id / name / produceDescriptions 三个字段，描述是"分段"结构：
    普通文本段 + ``ProduceExamEffectType`` 标签段（打分/元气/体力回复…）+
    ``Exam`` 数值段（``CustomizeEffectValue1`` 等标记里带数值）。
  * 结构化字段：``data/cache/ProduceItem.yaml``（vertesan/gakumasu-diff 上游 diff 出的
    原始 master，21MB）。本地 master 里**没有** rarity 和 trigger/effect 关联，
    这两个只能从 yaml 的 ``rarity`` / ``originProduceExamTriggerId`` 拿；
    yaml 与本地同 id 空间，脚本会断言 1068/1068 全覆盖。
  * 触发时机中文：``masterTrans/ProduceExamTrigger.json``（``e_trigger-*`` 的中文描述）
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(r"D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans")
YAML = ROOT / "data" / "cache" / "ProduceItem.yaml"
OUT = ROOT / "data" / "knowledge" / "p_items.json"

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
    ],
    "card_played": [
        r"(?:主动|辅助|偶像固有)技能卡使用后",
        r"(?:集中的|感性|理性|元气|体力回复|绝好调|干劲|强气|全力|温存)效果的?技能卡使用后",
        r"技能卡使用后",
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
    return effects


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


def build() -> dict:
    local = load_master("ProduceItem.json")
    yaml_items = parse_yaml_items(YAML)
    trigger_cn, effect_labels = label_tables()

    missing = [row["id"] for row in local if row["id"] not in yaml_items]
    records = []
    for row in local:
        yaml_item = yaml_items.get(row["id"], {})
        zh_text = render(row.get("produceDescriptions", []))
        ja_text = render(yaml_item.get("descriptions", []))

        desc_triggers = [d.get("originProduceExamTriggerId", "").strip('"') for d in yaml_item.get("descriptions", [])]
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
        effects = extract_effects(row.get("produceDescriptions", []), yaml_item.get("descriptions", []), zh_text)
        for eff in effects:
            eff["label"] = effect_labels.get(f"ProduceExamEffectType_{eff['type']}", "")
        primary = primary_effect(effects)
        value, unit = primary_value(effects)

        records.append(
            {
                "id": row["id"],
                "name": row.get("name", ""),
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
                "max_uses": max((e["max_uses"] for e in effects), default=0),
                "effects": effects,
                "text_zh": zh_text,
                "text_ja": ja_text,
            }
        )

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
    }
    return {
        "source": {
            "master": "masterTrans/ProduceItem.json",
            "master_version": "2026-09-16",
            "master_size": "8.69MB",
            "structured": "data/cache/ProduceItem.yaml (vertesan/gakumasu-diff)",
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
