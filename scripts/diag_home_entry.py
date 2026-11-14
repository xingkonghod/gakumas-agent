"""离线诊断：当前主页截图上模板/OCR 能否定位「プロデュース」入口。"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.vision.matcher import TemplateMatcher  # noqa: E402
from gkagent.vision.ocr import OcrEngine  # noqa: E402


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "new_account.png"
    image = cv2.imread(str(path))
    print(f"image {path.name}: {image.shape[1]}x{image.shape[0]}")

    matcher = TemplateMatcher(ROOT / "templates")
    for name in ("home", "produce_entry", "home_tab"):
        for th in (0.85, 0.7, 0.5):
            match = matcher.find(name, image, threshold=th)
            if match is not None:
                print(f"template {name} >= {th}: score={match.score:.3f} center={match.center} box={match.box}")
                break
        else:
            print(f"template {name}: no match >= 0.5")

    ocr = OcrEngine()
    print("--- OCR bottom half (y>=800) ---")
    for line in ocr.read(image, roi=(0, 800, 720, 480)):
        print(f"{line.score:.2f}\t{line.text}\tbox={line.box}")


if __name__ == "__main__":
    main()
