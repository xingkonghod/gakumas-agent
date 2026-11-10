from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from gkagent.contract.models import Card, Observation, Phase
from gkagent.vision.cards import (
    DEFAULT_TEMPLATE_DIR,
    HandCard,
    HandScan,
    is_produce_battle,
    recognize_hand,
    scan_hand,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = DEFAULT_TEMPLATE_DIR
DATA = ROOT / "data"

WIDTH, HEIGHT = 720, 1279
CARD_W, CARD_H = 130, 232
GAP = 8
LEFT = 24
TOP = 852
COSTS = (1, 0, 2, 3, 1)
PLAYABLE = (True, True, True, False, True)


def _draw_card(
    image: np.ndarray,
    x: int,
    y: int,
    cost: int,
    *,
    dim: bool = False,
    suggested: bool = False,
) -> tuple[int, int, int, int]:
    frame = (210, 120, 45)
    if suggested:
        cv2.rectangle(image, (x - 4, y - 4), (x + CARD_W + 3, y + CARD_H + 3), (240, 220, 40), -1)
        frame = (230, 200, 60)
    cv2.rectangle(image, (x, y), (x + CARD_W - 1, y + CARD_H - 1), frame, -1)
    cv2.rectangle(
        image,
        (x + 5, y + 5),
        (x + CARD_W - 6, y + CARD_H - 6),
        (235, 240, 246),
        -1,
    )
    cv2.circle(image, (x + CARD_W // 2, y + CARD_H // 2 + 8), 24, (120, 150, 230), -1)
    cv2.rectangle(image, (x + 12, y + 10), (x + 60, y + 36), (40, 30, 90), -1)
    cv2.putText(
        image,
        str(cost),
        (x + 20, y + 33),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (250, 250, 250),
        2,
        cv2.LINE_AA,
    )
    cv2.rectangle(
        image,
        (x + 8, y + CARD_H - 34),
        (x + CARD_W - 8, y + CARD_H - 10),
        (248, 248, 244),
        -1,
    )
    cv2.putText(
        image,
        "COST",
        (x + 20, y + CARD_H - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (90, 90, 100),
        1,
        cv2.LINE_AA,
    )
    if dim:
        region = image[y : y + CARD_H, x : x + CARD_W]
        image[y : y + CARD_H, x : x + CARD_W] = (region * 0.52).astype(np.uint8)
    return x, y, CARD_W, CARD_H


def _synthetic_hand(
    costs: tuple[int, ...] = COSTS,
    playable: tuple[bool, ...] = PLAYABLE,
    suggested: int | None = None,
) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    rng = np.random.default_rng(7)
    image = np.full((HEIGHT, WIDTH, 3), (58, 64, 74), np.uint8)
    # 场景噪声 + 一个不相关亮块，避免识别器依赖纯色背景。
    noise = rng.integers(-8, 8, size=(HEIGHT, WIDTH, 3), dtype=np.int16)
    image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    cv2.rectangle(image, (20, 560), (180, 700), (210, 215, 220), -1)
    boxes: list[tuple[int, int, int, int]] = []
    for i, (cost, usable) in enumerate(zip(costs, playable, strict=True)):
        x = LEFT + i * (CARD_W + GAP)
        boxes.append(
            _draw_card(image, x, TOP, cost, dim=not usable, suggested=i == suggested)
        )
    return image, boxes


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = float(ix * iy)
    union = float(aw * ah + bw * bh) - inter
    return inter / union if union > 0 else 0.0


def test_recognize_hand_finds_boxes() -> None:
    image, truth = _synthetic_hand()
    scan = scan_hand(image)
    assert isinstance(scan, HandScan)
    assert len(scan) == len(truth)

    xs = [card.box[0] for card in scan.cards]
    assert xs == sorted(xs)
    for true_box in truth:
        assert max(_iou(card.box, true_box) for card in scan.cards) > 0.45
    for card in scan.cards:
        assert isinstance(card, HandCard)
        assert isinstance(card, Card)
        assert card.box[2] > 80
        assert card.box[3] > 120
        assert 0.0 <= card.confidence <= 1.0


def test_costs_and_playability() -> None:
    image, _ = _synthetic_hand()
    cards = recognize_hand(image)
    assert len(cards) == len(COSTS)
    assert [card.cost for card in cards] == list(COSTS)
    assert [card.playable for card in cards] == list(PLAYABLE)
    assert [card.kind for card in cards] == [
        "cards",
        "cards",
        "cards",
        "useless",
        "cards",
    ]
    assert all(card.card_id.startswith("card_") for card in cards)


def test_two_digit_cost() -> None:
    image = np.full((HEIGHT, WIDTH, 3), (58, 64, 74), np.uint8)
    box = _draw_card(image, 200, TOP, 10)
    cards = recognize_hand(image)
    assert len(cards) == 1
    assert cards[0].cost == 10
    assert cards[0].box[0] <= box[0] <= cards[0].box[0] + cards[0].box[2]


def test_ap_makes_cards_unplayable() -> None:
    image, _ = _synthetic_hand()
    cards = recognize_hand(image, ap=1)
    assert [card.playable for card in cards] == [True, True, False, False, True]
    assert cards[2].kind == "useless"


def test_observation_contract_roundtrip() -> None:
    image, _ = _synthetic_hand()
    scan = scan_hand(image, ap=2)
    obs = scan.to_observation(frame_id=3, ts_ms=1234, screen="produce_card", turn=2)
    assert isinstance(obs, Observation)
    assert obs.frame_id == 3
    assert obs.ts_ms == 1234
    assert obs.phase == Phase.PRODUCE
    assert len(obs.hand) == len(scan.cards)
    assert all(isinstance(card, Card) for card in obs.hand)
    assert len(obs.raw["boxes"]) == len(scan.cards)
    assert len(obs.raw["costs"]) == len(scan.cards)
    assert obs.raw["ap"] == 2
    assert 0.0 <= obs.confidence <= 1.0
    # box 是 HandCard 的扩展字段；dump 后仍能按 Contract 重新校验。
    Observation.model_validate(obs.model_dump())


def test_maa_hits_drive_label_box_and_playability() -> None:
    image, boxes = _synthetic_hand()
    hits = [
        SimpleNamespace(label="suggestions", box=boxes[0], score=0.95),
        SimpleNamespace(label="useless", box=boxes[3], score=0.90),
        SimpleNamespace(label="cards", box=boxes[4], score=0.80),
    ]
    cards = recognize_hand(image, hits=hits, ap=5)
    assert len(cards) == 3
    assert cards[0].kind == "suggestions"
    assert cards[0].playable is True
    assert cards[0].suggested is True
    assert cards[0].box == boxes[0]
    assert cards[1].kind == "useless"
    assert cards[1].playable is False
    assert cards[2].kind == "cards"
    assert cards[2].box == boxes[4]


def test_downscaled_screenshot() -> None:
    image, _ = _synthetic_hand()
    small = cv2.resize(image, (WIDTH // 2, HEIGHT // 2), interpolation=cv2.INTER_AREA)
    scan = scan_hand(small)
    assert len(scan) == len(COSTS)
    for card in scan.cards:
        assert 0 <= card.box[0] < WIDTH // 2
        assert 0 <= card.box[1] < HEIGHT // 2


def test_empty_and_invalid_image() -> None:
    blank = np.full((HEIGHT, WIDTH, 3), 20, np.uint8)
    assert scan_hand(blank).cards == []

    with pytest.raises(ValueError):
        scan_hand(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        scan_hand(np.zeros((0, 0, 3), np.uint8))


def test_non_hand_screenshot_has_no_cards() -> None:
    screenshot = DATA / "row_before.png"
    if not screenshot.exists():
        pytest.skip("real screenshot not available")
    image = cv2.imread(str(screenshot))
    assert scan_hand(image).cards == []
    assert is_produce_battle(image) is False


def test_is_produce_battle_templates() -> None:
    # 复制到 templates/ 的 MAA 模板应能自匹配。
    health = cv2.imread(str(TEMPLATES / "cards_health.png"))
    assert health is not None
    canvas = np.full((HEIGHT, WIDTH, 3), 30, np.uint8)
    h, w = health.shape[:2]
    canvas[125 : 125 + h, 512 : 512 + w] = health
    assert is_produce_battle(canvas) is True

    screenshot = DATA / "sel_after.png"
    if not screenshot.exists():
        pytest.skip("real screenshot not available")
    real = cv2.imread(str(screenshot))
    assert is_produce_battle(real) is False
