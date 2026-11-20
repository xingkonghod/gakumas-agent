"""在采集到的响应里找 ExamSeedValue（UserProduceProgress.field 600）。

字段 600 → protobuf key = 600<<3 = 4800 → varint 0xC0 0x25
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
FIELD = 600
KEY = bytes([(FIELD << 3 & 0x7F) | 0x80, (FIELD << 3) >> 7])


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


def bodies(rec: dict):
    for which in ("req_plain_hex", "resp_plain_hex"):
        raw = bytes.fromhex(rec.get(which) or "")
        if not raw:
            continue
        if raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except Exception:  # noqa: BLE001
                continue
        yield which, raw


def main() -> int:
    print("field", FIELD, "key bytes", KEY.hex())
    hits = 0
    for line in TRAFFIC.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        path = rec.get("path", "")
        for which, body in bodies(rec):
            idx = body.find(KEY)
            if idx < 0:
                continue
            # 读取该 key 后面的 varint 值
            try:
                value, _ = varint(body, idx + len(KEY))
            except IndexError:
                continue
            if 0 < value < 2**31:
                hits += 1
                print(f"{path} [{which}] offset={idx} seed={value} (0x{value:08X})")
    print("命中", hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
