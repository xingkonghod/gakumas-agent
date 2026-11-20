"""验证：用 MITM 抓到的 examSeedValue + xorshift32 能否重放考试牌序。

步骤：
1. StepAuditionStart 响应里取 seed（UserProduceProgress.field 600）
2. Produce/Start 响应里取牌组（produceCardIds）
3. 用客户端同款 xorshift32 + Fisher-Yates 洗牌
4. 打印洗牌后的前几张，供人工对照
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")


class NativeRandom:
    """客户端 System.Random 替身（xorshift32），来自 gakumas_exam.rng。"""

    def __init__(self, state: int) -> None:
        self.state = state & 0xFFFFFFFF
        self.calls = 0

    def _advance(self) -> int:
        old = self.state
        x = (old ^ (old << 13)) & 0xFFFFFFFF
        x = (x ^ (x >> 17)) & 0xFFFFFFFF
        self.state = (x ^ (x << 5)) & 0xFFFFFFFF
        self.calls += 1
        return old

    def integer(self, low: int, high: int) -> int:
        return low + ((self._advance() * (high - low)) >> 32)

    def shuffle(self, values: list) -> None:
        for n in range(len(values), 1, -1):
            j = self.integer(0, n)
            values[j], values[n - 1] = values[n - 1], values[j]


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


def parse(buf: bytes, depth: int = 0, max_depth: int = 45) -> list:
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


def walk(nodes: list, path: tuple = ()):
    """深度遍历，产出 (path, field, kind, value)。"""
    for field, kind, value in nodes:
        yield path + (field,), field, kind, value
        if kind == "msg":
            yield from walk(value, path + (field,))


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


def main() -> int:
    records = []
    for line in TRAFFIC.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    audition = next((r for r in records if "Produce/StepAuditionStart" in r.get("path", "")), None)
    start = next((r for r in records if r.get("path", "").endswith("Produce/Start")), None)
    if audition is None or start is None:
        print("缺 Produce/Start 或 StepAuditionStart 记录")
        return 1

    audition_raw = body(audition, "resp_plain_hex") or b""
    start_raw = body(start, "resp_plain_hex") or b""

    # 1) seed：field 600 的 varint
    seeds = [
        value
        for path, field, kind, value in walk(parse(audition_raw))
        if field == 600 and kind == "varint" and 0 < value < 2**31
    ]
    print("StepAuditionStart 里的 field600 候选:", [f"{s} (0x{s:08X})" for s in seeds])

    # 2) 牌组：Start 响应里形如 s_card-* 的字符串
    ids = []
    for path, field, kind, value in walk(parse(start_raw)):
        if kind == "bytes":
            try:
                text = value.decode("utf-8")
            except Exception:  # noqa: BLE001
                continue
            if text.startswith("s_card-") or text.startswith("p_card-"):
                ids.append(text)
    print("Produce/Start 里的卡牌 id 数量:", len(ids), ids[:8])

    if not seeds or not ids:
        print("数据不足，无法验证")
        return 2

    seed = seeds[0]
    deck = list(dict.fromkeys(ids))  # 去重保序（同一张卡可能强化前后）
    print(f"\n用 seed=0x{seed:08X} 洗 {len(deck)} 张牌：")
    rng = NativeRandom(seed)
    shuffled = list(deck)
    rng.shuffle(shuffled)
    print("洗牌后前 8 张:", shuffled[:8])
    print("RNG 调用次数:", rng.calls, " 结束状态:", f"0x{rng.state:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
