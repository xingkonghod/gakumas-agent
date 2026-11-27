import sys

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.tasks.produce_ui import ProduceDriver


class FakeDevice:
    def __init__(self):
        self.clicks = []

    def click_force(self, x, y):
        self.clicks.append((x, y))


class FakeAgent:
    def __init__(self):
        self.device = FakeDevice()


img = cv2.imread(sys.argv[1])
driver = ProduceDriver(sleep=lambda _s: None)
lines = driver.read_fast(img)
text = driver.text_of(lines)
print("TEXT:", text.replace("\n", " | ")[:500])
print("LINES:", [(ln.text, ln.box) for ln in lines])
agent = FakeAgent()
res = driver.decide(agent, lines, img)
print("RESULT:", res.screen, res.action, res.detail)
print("CLICKS:", agent.device.clicks)
