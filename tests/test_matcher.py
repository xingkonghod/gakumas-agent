from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from gkagent.vision.matcher import TemplateMatcher

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def test_self_match() -> None:
    matcher = TemplateMatcher(TEMPLATES)
    img = cv2.imread(str(TEMPLATES / "activity_fee.png"))
    m = matcher.find("activity_fee", img)
    assert m is not None
    assert m.score > 0.99
    assert m.box[:2] == (0, 0)


def test_missing_template() -> None:
    matcher = TemplateMatcher(TEMPLATES)
    with pytest.raises(FileNotFoundError):
        matcher.find("no_such_template", cv2.imread(str(TEMPLATES / "activity_fee.png")))


def test_find_any() -> None:
    matcher = TemplateMatcher(TEMPLATES)
    img = cv2.imread(str(TEMPLATES / "activity_fee.png"))
    m = matcher.find_any(["close", "activity_fee"], img)
    assert m is not None
    assert m.name == "activity_fee"
