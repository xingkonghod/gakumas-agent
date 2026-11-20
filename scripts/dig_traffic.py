"""从采集到的 traffic.jsonl 里挖：编成(loadout)、牌组、seed/random 线索。

解 gzip + protobuf，打印 Produce/Start、StepAuditionStart/Refresh 的字段结构。
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
KEYS = ("Produce/Start", "StepAuditionStart", "StepAuditionRefresh", "StepAuditionEnd")


def varint(buf: bytes, i: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return value, i


def parse(buf: bytes, depth: int = 0, max_depth: int = 6) -> list:
    out: list = []
    i = 0
    while i < len(buf):
        try:
            key, i = varint(buf, i)
        except IndexError:
            break
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = varint(buf, i)
            out.append((field, "varint", value))
        elif wire == 2:
            length, i = varint(buf, i)
            sub = buf[i : i + length]
            i += length
            inner = None
            if depth < max_depth and length > 1:
                try:
                    inner = parse(sub, depth + 1, max_depth)
                    if not inner:
                        inner = None
                except Exception:  # noqa: BLE001
                    inner = None
            out.append((field, "msg", inner) if inner else (field, "bytes", sub))
        elif wire == 5:
            out.append((field, "f32", buf[i : i + 4]))
            i += 4
        elif wire == 1:
            out.append((field, "f64", buf[i : i + 8]))
            i += 8
        else:
            break
    return out


def show(nodes: list, indent: int = 0, max_lines: int = 60) -> None:
    shown = 0
    for field, kind, value in nodes:
        if shown >= max_lines:
            print("  " * indent + "...")
            return
        shown += 1
        pad = "  " * indent
        if kind == "msg":
            print(f"{pad}{field}: {{")
            show(value, indent + 1, max_lines)
            print(f"{pad}}}")
        elif kind == "varint":
            print(f"{pad}{field}: {value}")
        else:
            try:
                text = value.decode("utf-8")
                printable = all(32 <= ord(c) < 127 or c in "，。、！？" for c in text)
            except Exception:  # noqa: BLE001
                printable = False
            preview = text if printable else value[:16].hex()
            print(f"{pad}{field}: <{kind} {len(value)}B> {preview}")


def decode(rec: dict, which: str) -> bytes | None:
    raw = bytes.fromhex(rec.get(which) or "")
    if not raw:
        return None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:  # noqa: BLE001
            return None
    return raw


def main() -> int:
    seen: dict[str, dict] = {}
    for line in TRAFFIC.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        path = rec.get("path", "")
        for key in KEYS:
            if path.endswith(key) and key not in seen:
                seen[key] = rec

    for key, rec in seen.items():
        print(f"\n{'=' * 70}\n{key}   ({rec.get('note', '')})")
        for which, label in (("req_plain_hex", "请求"), ("resp_plain_hex", "响应")):
            body = decode(rec, which)
            if body is None:
                print(f"  {label}: 无")
                continue
            print(f"  --- {label} {len(body)} 字节 ---")
            show(parse(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
