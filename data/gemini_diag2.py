import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from gemini_web import Page

page = Page()
for _ in range(3):
    time.sleep(2)
    body = page.eval("document.body ? document.body.innerText : ''") or ""
    print("---- 页面文本 ----")
    print(body[:400].replace("\n", " | "))
    selectors = [
        "model-response",
        "message-content",
        ".response-container",
        "[data-response-id]",
        "div.markdown",
        ".markdown",
    ]
    counts = {sel: page.eval(f"document.querySelectorAll({json.dumps(sel)}).length") for sel in selectors}
    print("选择器计数:", json.dumps(counts, ensure_ascii=False))
