"""定位「考试时刻的牌堆」：逐层解析 StepAuditionStart 响应并标注已知字段号。

字段号来源：data/reverse/out/dump.cs（Il2CppDumper 元数据）
  ProduceStepAuditionStartResponse: effectResults=100(repeated), commonResponse=9999
  UserData: userProduceProgress=374217157, userProduceCardList=230550472,
            userProduceCardConversionList=238079855
  UserProduceProgress: examSeedValue=600, auditions=510, excludeProduceCardIds=313,
            convertProduceCardIds=318, produceItems=353, produceDrinkIds=400,
            stepType=105, stepNumber=103, vocal=200, dance=201, visual=202,
            stamina=220, maxStamina=221
  UserProduceCard: produceCardId=2, produceCardUpgradeCount=3
  AuditionResult: auditionStepType=1, selectNumber=2, rank=3, score=4, point=5

用法：python scripts/dig_deck.py [--file PATH] [--index N] [--tree]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")

# 已知字段号 → 名字（按消息类型分层标注；通用标注只放无歧义的）
KNOWN = {
    374217157: "UserData.userProduceProgress",
    230550472: "UserData.userProduceCardList",
    238079855: "UserData.userProduceCardConversionList",
    342861366: "UserData.user",
    600: "examSeedValue?",
    9999: "commonResponse",
}


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


def parse(buf: bytes, depth: int = 0, max_depth: int = 30) -> list:
    """返回 [(field, wire, value, offset)]；wire2 的 value 是 (raw, inner|None)。"""
    out: list = []
    i = 0
    while i < len(buf):
        start = i
        try:
            key, i = varint(buf, i)
        except IndexError:
            break
        field, wire = key >> 3, key & 7
        if field == 0:
            break
        if wire == 0:
            try:
                value, i = varint(buf, i)
            except IndexError:
                break
            out.append((field, wire, value, start))
        elif wire == 2:
            try:
                length, i = varint(buf, i)
            except IndexError:
                break
            if length < 0 or i + length > len(buf):
                break
            sub = buf[i : i + length]
            i += length
            inner = None
            if depth < max_depth and length > 1 and not looks_text(sub):
                try:
                    inner = parse(sub, depth + 1, max_depth)
                    if not inner:
                        inner = None
                except Exception:  # noqa: BLE001
                    inner = None
            out.append((field, wire, (sub, inner), start))
        elif wire == 5:
            if i + 4 > len(buf):
                break
            out.append((field, wire, buf[i : i + 4], start))
            i += 4
        elif wire == 1:
            if i + 8 > len(buf):
                break
            out.append((field, wire, buf[i : i + 8], start))
            i += 8
        else:
            break
    return out


def looks_text(buf: bytes) -> bool:
    if not buf:
        return False
    try:
        text = buf.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return all(32 <= ord(c) < 127 for c in text)


def show(nodes: list, indent: int = 0, max_lines: int = 400) -> int:
    shown = 0
    for field, wire, value, offset in nodes:
        if shown >= max_lines:
            print("  " * indent + "...(截断)")
            return shown
        pad = "  " * indent
        tag = KNOWN.get(field, "")
        tag = f"  [{tag}]" if tag else ""
        if wire == 0:
            print(f"{pad}@{offset} {field}: {value}{tag}")
            shown += 1
        elif wire == 2:
            raw, inner = value
            if inner is not None:
                print(f"{pad}@{offset} {field}: {{{tag}")
                shown += 1 + show(inner, indent + 1, max_lines - shown)
                print(f"{pad}}}")
            elif looks_text(raw):
                print(f"{pad}@{offset} {field}: \"{raw.decode('utf-8')}\"{tag}")
                shown += 1
            else:
                print(f"{pad}@{offset} {field}: <{len(raw)}B> {raw[:24].hex()}{tag}")
                shown += 1
        else:
            print(f"{pad}@{offset} {field}: <wire{wire}> {value.hex()}{tag}")
            shown += 1
        if shown >= max_lines:
            return shown
    return shown


def walk(nodes: list, path: tuple = ()):
    for field, wire, value, offset in nodes:
        yield path + (field,), field, wire, value, offset
        if wire == 2 and value[1] is not None:
            yield from walk(value[1], path + (field,))


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
    parser.add_argument("--index", type=int, default=None, help="只看第 N 个 StepAuditionStart")
    parser.add_argument("--tree", action="store_true", help="打印完整字段树")
    parser.add_argument("--path", default="StepAuditionStart", help="按 path 子串过滤")
    args = parser.parse_args(argv)

    records = []
    for line in Path(args.file).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if args.path in rec.get("path", ""):
            records.append(rec)
    print(f"匹配 {args.path!r} 的记录: {len(records)}")
    for n, rec in enumerate(records):
        resp = body(rec, "resp_plain_hex")
        req = body(rec, "req_plain_hex")
        print(f"\n[{n}] ts={rec.get('ts')} path={rec.get('path')} "
              f"req={len(req) if req else 0}B resp={len(resp) if resp else 0}B")
        if args.index is not None and n != args.index:
            continue
        if resp is None:
            continue
        nodes = parse(resp)
        if args.tree:
            show(nodes)
        else:
            # 摘要：顶层字段 + 所有卡牌字符串 + seed + 大牌表
            print("  顶层字段:", [(f, w) for f, w, _, _ in nodes])
            cards: list[tuple[str, str]] = []
            seeds: list[tuple[str, int]] = []
            big_lists: list[tuple[str, int, int]] = []
            for path, field, wire, value, offset in walk(nodes):
                pstr = ".".join(map(str, path))
                if wire == 2:
                    raw, inner = value
                    if looks_text(raw):
                        text = raw.decode("utf-8")
                        if "card" in text:
                            cards.append((pstr, text))
                    if field == 230550472 and inner is not None:
                        big_lists.append((pstr, offset, len(inner)))
                elif wire == 0 and field == 600 and 0 < value < 2**31:
                    seeds.append((pstr, value))
            print("  seed 候选:", [(p, f"0x{v:08X}") for p, v in seeds])
            print("  userProduceCardList 出现:", big_lists)
            print(f"  卡牌字符串 {len(cards)} 个:")
            for pstr, text in cards:
                print(f"    {pstr}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
