"""从手牌 OCR 直接读卡名选牌（不点开每张卡）。

课程手牌上本来就有卡名（如「魅力的基础」「想象的基础」），OCR 底部区域就能读到；
拿卡名查本地卡库拿价值，挑最值且体力付得起的一张。
比「逐张点开读详情」快 3-4 倍。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HandPick:
    point: tuple[int, int]
    index: int
    name: str
    value: float


def _name_near(lines, box, library) -> str | None:
    """在手牌框下半部分/下方找 OCR 行，文本能查卡库的就是卡名。"""
    bx, by, bw, bh = box
    for line in lines:
        lx, ly, lw, _lh = line.box
        if ly < by + bh * 0.5 or ly > by + bh + 50:
            continue
        cx = lx + lw // 2
        if cx < bx - 10 or cx > bx + bw + 10:
            continue
        text = line.text.strip()
        if not (2 <= len(text) <= 12):
            continue
        if any(ch.isdigit() for ch in text):
            continue
        if library.find(text) is not None:
            return text
    return None


def pick_hand_card(
    lines,
    boxes,
    library,
    stamina: int | None = None,
    costs=None,
    attribute: str | None = None,
    exclude: set[str] | None = None,
) -> HandPick | None:
    """按卡名价值挑一张；costs 给每张卡的体力费用（可选）；attribute 匹配的卡加权；
    exclude 里的卡名（点不动/不满足条件）跳过。"""
    attribute_keyword = {"Vo": "歌唱", "Da": "舞蹈", "Vi": "视觉"}.get(attribute or "", None)
    excluded = exclude or set()
    best: HandPick | None = None
    for index, box in enumerate(boxes):
        cost = costs[index] if costs is not None and index < len(costs) else None
        if cost is not None and not (0 < cost <= 60):
            cost = None  # OCR 读歪的费用（71/0 之类）不参与判断
        if stamina is not None and cost is not None and cost > stamina:
            continue
        name = _name_near(lines, box, library)
        if name is None or name in excluded:
            continue
        info = library.find(name)
        if info is None:
            continue
        value = info.value
        if attribute_keyword:
            text = getattr(info, "text", "")
            if attribute_keyword in text:
                value += 4.0  # 课程属性匹配的卡大幅加权（CLEAR 要的是对应属性分）
            elif any(word in text for word in ("歌唱", "舞蹈", "视觉")):
                value -= 1.5  # 其它属性的卡降权
        pick = HandPick(
            point=(box[0] + box[2] // 2, box[1] + box[3] // 2),
            index=index,
            name=name,
            value=value,
        )
        if best is None or pick.value > best.value:
            best = pick
    return best
