import sys

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver

img = cv2.imread(r"D:\Games\gakumas-agent\data\auto\step_003.png")
driver = ProduceDriver(sleep=lambda _s: None)
lines = driver.read_fast(img)
text = driver.text_of(lines)
print("TEXT repr:", ascii(text))
option_rows = [
    line
    for line in lines
    if 600 <= driver.center(line)[1] <= 950
    and 2 <= len(line.text.strip()) <= 20
    and not any(ch.isdigit() for ch in line.text)
    and "P" not in line.text
    and "快进" not in line.text
]
print("option_rows:", [(ln.text, ln.box) for ln in option_rows])
print("action_page_hint:", [(w, w in text) for w in ("授课", "咨询", "训练", "休息")])
import re

print("p_cost:", re.search(r"[-－−]\s*\d{2,3}", text) is not None)
print("dialogue:", [(m, m in text) for m in ("……", "…", "？", "?")])
print("请选择行动:", "请选择行动" in text)
print("tooltip:", "根据选项会发生各种效果" in text)
