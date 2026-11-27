import sys

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.tasks.produce_ui import ProduceDriver

img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else r"D:\Games\gakumas-agent\data\auto\step_045.png")
driver = ProduceDriver(sleep=lambda _s: None)
lines = driver.read_fast(img)
text = driver.text_of(lines)
print("TEXT:", text[:400].replace("\n", " | "))
print("LINES:", [(ln.text, ln.box) for ln in lines])
print("best_reward:", driver._best_reward_card(lines, img))
print("claim line:", driver.find(lines, "领取"))
print("claim center:", driver.center(driver.find(lines, "领取")) if driver.find(lines, "领取") else None)
print("recommend:", driver.find(lines, "推荐"))
print("gold:", driver._gold_reward_point(img))
