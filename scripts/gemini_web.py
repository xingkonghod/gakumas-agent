"""网页端 Gemini 驱动（CDP，无需 API key）。

用法：
  python scripts/gemini_web.py --launch          # 启动带调试端口的 Chrome 并打开 Gemini
  python scripts/gemini_web.py --ask "你好"       # 发一句并打印回复
  python scripts/gemini_web.py --batch in.json --out out.json   # 批量（[{id, prompt}]）

首次使用要**在打开的浏览器里手动登录一次**（登录态存在独立 profile 里，之后免登录）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
PROFILE = ROOT / "data" / "chrome-gemini"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PORT = 9222


def launch(url: str = "https://gemini.google.com/app") -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(CHROME),
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            url,
        ]
    )
    print(f"已启动 Chrome（调试端口 {PORT}，profile={PROFILE}）")
    print("→ 请在那个窗口里登录 Gemini，登录一次即可（之后免登录）")


def _ws():
    import requests
    import websocket

    for _ in range(40):
        try:
            targets = requests.get(f"http://127.0.0.1:{PORT}/json", timeout=1).json()
        except Exception:
            time.sleep(0.5)
            continue
        pages = [t for t in targets if t.get("type") == "page" and "gemini.google.com" in t.get("url", "")]
        if pages:
            return websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=60)
        time.sleep(0.5)
    raise RuntimeError("找不到 Gemini 页面；先跑 --launch 并在浏览器里打开 gemini.google.com")


class Page:
    def __init__(self) -> None:
        self.ws = _ws()
        self.seq = 0

    def eval(self, expression: str, timeout: float = 60.0):
        import websocket

        self.seq += 1
        self.ws.send(
            json.dumps(
                {
                    "id": self.seq,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expression, "awaitPromise": True, "returnByValue": True},
                }
            )
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                message = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if message.get("id") == self.seq:
                result = message.get("result", {})
                if "exceptionDetails" in result:
                    raise RuntimeError(result["exceptionDetails"].get("text", "JS 异常"))
                return result.get("result", {}).get("value")
        raise TimeoutError("CDP 调用超时")

    def send(self, method: str, params: dict | None = None):
        import websocket

        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                message = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if message.get("id") == self.seq:
                return message.get("result")
        return None

    def type_text(self, text: str) -> None:
        """聚焦输入框并用 CDP 原生插入文本（比 execCommand 可靠）。"""
        self.eval("""
            (() => {
              const box = document.querySelector('rich-textarea div[contenteditable="true"]')
                       || document.querySelector('div[contenteditable="true"]');
              if (box) { box.focus(); }
              return !!box;
            })()
        """)
        self.send("Input.insertText", {"text": text})

    def press_enter(self) -> None:
        for kind in ("keyDown", "keyUp"):
            self.send(
                "Input.dispatchKeyEvent",
                {"type": kind, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13},
            )
        time.sleep(0.3)
        self.send(
            "Input.dispatchKeyEvent",
            {"type": "rawKeyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13},
        )
        self.send(
            "Input.dispatchKeyEvent",
            {"type": "char", "key": "Enter", "text": "\r", "unmodifiedText": "\r", "windowsVirtualKeyCode": 13},
        )
        self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13})

    def ask(self, prompt: str, wait_s: float = 180.0) -> str:
        """发送并返回回复：用整页文本做差分（对 Gemini 的 DOM 改版最鲁棒）。"""
        body = "document.body ? document.body.innerText : ''"
        before = self.eval(body) or ""
        self.type_text(prompt)
        time.sleep(0.6)
        self.press_enter()
        time.sleep(1.0)
        last = ""
        stable = 0
        deadline = time.time() + wait_s
        while time.time() < deadline:
            time.sleep(1.5)
            now = self.eval(body) or ""
            if any(k in now for k in ("正在深入", "思考中", "正在生成", "正在思考")):
                last, stable = "", 0
                continue
            if now == before:
                continue
            if now == last:
                stable += 1
                if stable >= 3:
                    break
            else:
                last, stable = now, 0
        # 取"提示词之后"的部分作为回复
        answer = ""
        idx = last.rfind(prompt.strip()[:20]) if prompt.strip() else -1
        if idx != -1:
            answer = last[idx + len(prompt.strip()[:20]):]
        else:
            common = 0
            while common < min(len(before), len(last)) and before[common] == last[common]:
                common += 1
            answer = last[common:]
        return answer.strip() or last.strip()


def ask_once(prompt: str) -> str:
    page = Page()
    return page.ask(prompt)


def batch(items: list[dict], out_path: Path) -> None:
    page = Page()
    results = []
    for item in items:
        try:
            answer = page.ask(item["prompt"])
            results.append({**item, "answer": answer, "ok": True})
            print(f"  [{item.get('id')}] 完成 ({len(answer)} 字)")
        except Exception as exc:  # noqa: BLE001
            results.append({**item, "answer": "", "ok": False, "error": str(exc)})
            print(f"  [{item.get('id')}] 失败: {exc}")
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {out_path}")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--ask")
    parser.add_argument("--batch")
    parser.add_argument("--out", default=str(ROOT / "data" / "gemini_out.json"))
    args = parser.parse_args(argv)

    if args.launch:
        launch()
        return 0
    if args.ask:
        print(ask_once(args.ask))
        return 0
    if args.batch:
        items = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        batch(items, Path(args.out))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
