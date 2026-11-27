import sys

sys.path.insert(0, r"D:\Games\gakumas-agent\src")
sys.path.insert(0, r"D:\Games\gakumas-agent\scripts")

import cv2

from gkagent.tasks.produce_ui import CARD_DETAIL_NAME_BOX, CARD_DETAIL_PROBES, is_card_detail_text
from gkagent.vision.ocr import OcrEngine

img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else r"D:\Games\gakumas-agent\data\auto\step_190.png")
engine = OcrEngine()
print("image", img.shape)
for box in CARD_DETAIL_PROBES + (CARD_DETAIL_NAME_BOX,):
    line = engine.line(img, box, digits_only=False)
    text = line.text if line is not None else None
    print(box, "->", repr(text), "detail?", is_card_detail_text(text or ""))
