"""Dump 指定记录的完整牌表 + 培育进度（produceId/stepNumber/stepType），判定快照 vs 增量。"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from reconstruct_deck import find_cards, body, fmt, varint  # noqa: E402

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
PROGRESS_FIELD = 374217157


def key_bytes(key: int) -> bytes:
    out = bytearray()
    while True:
        b = key & 0x7F
        key >>= 7
        if key:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def find_progress(b: bytes) -> dict:
    kb = key_bytes(PROGRESS_FIELD << 3 | 2)
    idx = b.find(kb)
    if idx < 0:
        return {}
    try:
        length, after = varint(b, idx + len(kb))
    except IndexError:
        return {}
    sub = b[after : after + length]
    # 浅解析 progress 顶层 varint/string 字段
    out: dict = {}
    i = 0
    while i < len(sub):
        try:
            key, i = varint(sub, i)
        except IndexError:
            break
        field, wire = key >> 3, key & 7
        if wire == 0:
            try:
                v, i = varint(sub, i)
            except IndexError:
                break
            out[field] = v
        elif wire == 2:
            try:
                ln, i = varint(sub, i)
            except IndexError:
                break
            s = sub[i : i + ln]
            i += ln
            try:
                txt = s.decode("utf-8")
                if all(32 <= ord(c) < 127 for c in txt):
                    out[field] = txt
            except UnicodeDecodeError:
                pass
        elif wire == 5:
            i += 4
        elif wire == 1:
            i += 8
        else:
            break
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--indices", default="0,7,64,129,136")
    args = ap.parse_args(argv)
    want = {int(x) for x in args.indices.split(",")}

    records = []
    for line in Path(args.file).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    for n, rec in enumerate(records):
        if n not in want:
            continue
        b = body(rec, "resp_plain_hex")
        if b is None:
            continue
        cards = find_cards(b)
        prog = find_progress(b)
        print(f"\n=== [{n}] {rec.get('ts')} {rec.get('path')} ===")
        # progress 关键字段: 3=produceId, 103=stepNumber, 105=stepType, 6=characterId, 7=idolCardId
        print(f"  produceId(3)={prog.get(3)} characterId(6)={prog.get(6)} "
              f"idolCardId(7)={prog.get(7)} stepNumber(103)={prog.get(103)} "
              f"stepType(105)={prog.get(105)} examSeed(600)={prog.get(600)}")
        print(f"  牌表 {len(cards)} 张:")
        for _, c in sorted(cards, key=lambda x: x[1]['number']):
            print("    " + fmt(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
