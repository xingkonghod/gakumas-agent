import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
from gemini_web import Page

page = Page()
print("URL:", page.eval("location.href"))
print("有输入框:", page.eval('!!document.querySelector(\'div[contenteditable="true"]\')'))
print("按钮数:", page.eval("document.querySelectorAll('button').length"))
body = page.eval("document.body ? document.body.innerText : ''") or ""
print("页面文本前 120:", body[:120].replace("\n", " | "))
buttons = page.eval("[...document.querySelectorAll('button')].slice(0,12).map(b => (b.getAttribute('aria-label')||b.innerText||'').trim().slice(0,18))")
print("按钮标签:", json.dumps(buttons, ensure_ascii=False))
