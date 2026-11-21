"""扫描全部流量，找 userProduceCardList（UserData.field 230550472）的每次出现。

protobuf repeated message：每个元素一次 key+length+value。
UserProduceCard: produceCardId=2(string), produceCardUpgradeCount=3(varint)。
直接按 key 字节定位，避免启发式解析漏树。

用法：python scripts/scan_deck_updates.py [--file PATH] [--dump-last]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
FIELD = 230550472
KEY = FIELD << 3 | 2  # wire 2


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


KEY_BYTES = key_bytes(KEY)


def parse_card(buf: bytes) -> tuple[str, int] | None:
    """解析单个 UserProduceCard 元素。"""
    i = 0
    cid = None
    up = 0
    while i < len(buf):
        try:
            key, i = varint(buf, i)
        except IndexError:
            return None
        field, wire = key >> 3, key & 7
        if wire == 0:
            try:
                value, i = varint(buf, i)
            except IndexError:
                return None
            if field == 3:
                up = value
        elif wire == 2:
            try:
                length, i = varint(buf, i)
            except IndexError:
                return None
            sub = buf[i : i + length]
            i += length
            if field == 2:
                try:
                    cid = sub.decode("utf-8")
                except UnicodeDecodeError:
                    return None
        else:
            return None
    if cid is None:
        return None
    return cid, up


def find_cards(body: bytes) -> list[tuple[int, str, int]]:
    """返回 [(offset, cardId, upgradeCount)]，只保留解析成功的。"""
    out = []
    idx = 0
    while True:
        idx = body.find(KEY_BYTES, idx)
        if idx < 0:
            break
        try:
            length, after = varint(body, idx + len(KEY_BYTES))
        except IndexError:
            idx += 1
            continue
        if 0 < length <= 256 and after + length <= len(body):
            card = parse_card(body[after : after + length])
            if card and card[0].startswith("p_card-"):
                out.append((idx, card[0], card[1]))
                idx = after + length
                continue
        idx += 1
    return out


def body(rec: dict, which: str) -> bytes | None:
    raw = bytes.fromhex(rec.get(which) or "")
    if not raw:
        return None
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except Exception:  # noqa: BLE001
            return None
    return raw


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT))
    parser.add_argument("--dump-last", action="store_true", help="打印最后一次完整牌表")
    args = parser.parse_args(argv)

    records = []
    for line in Path(args.file).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    print(f"key bytes = {KEY_BYTES.hex()}  共 {len(records)} 条记录")
    last: list[tuple[int, str, int]] = []
    hits = 0
    for n, rec in enumerate(records):
        path = rec.get("path", "")
        for which in ("req_plain_hex", "resp_plain_hex"):
            b = body(rec, which)
            if b is None:
                continue
            cards = find_cards(b)
            if not cards:
                continue
            hits += 1
            last = cards
            print(f"[{n}] {rec.get('ts')} {path} [{which[:4]}] {len(cards)} 张")
            if len(cards) <= 40:
                print("     " + ", ".join(f"{c[1]}+{c[2]}" for c in cards))
    print(f"\n共 {hits} 次出现")
    if args.dump_last and last:
        print(f"最后一次牌表（{len(last)} 张）:")
        for off, cid, up in last:
            print(f"  @{off} {cid} +{up}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
