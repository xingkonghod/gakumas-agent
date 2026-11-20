"""从 traffic.jsonl 提取每场考试的真实结果（ground truth）。

用法：python scripts/extract_exams.py [--file PATH]
输出：每次 StepAuditionEndExamBattle 的 rank / score / vocal / dance / visual
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")


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


def field_map(nodes: list) -> dict[int, object]:
    """把 [(field, type, value)] 转成 {field: value}（重复字段取第一个）。"""
    out: dict[int, object] = {}
    for field, kind, value in nodes:
        if field not in out:
            out[field] = value
    return out


def decode_exam(record: dict) -> dict | None:
    raw = bytes.fromhex(record.get("req_plain_hex") or "")
    if not raw:
        return None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:  # noqa: BLE001
            return None
    top = field_map(parse(raw))
    result = top.get(2)
    if not isinstance(result, list):
        return None
    fields = field_map(result)
    return {
        "ts": record.get("ts"),
        "rank": fields.get(1),
        "score": fields.get(2),
        "stamina": fields.get(3),
        "vocal": fields.get(8),
        "dance": fields.get(9),
        "visual": fields.get(10),
        "actions": sum(1 for f, _, _ in result if f == 100),
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT))
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(f"找不到 {path}")
        return 1
    exams = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "StepAuditionEndExamBattle" in record.get("path", ""):
            exam = decode_exam(record)
            if exam:
                exams.append(exam)
    if not exams:
        print("没有考试记录")
        return 2
    print(f"{'时间':20s} {'名次':>4s} {'分数':>6s} {'歌唱':>5s} {'舞蹈':>5s} {'表现':>5s} {'操作数':>6s}")
    for e in exams:
        print(
            f"{str(e['ts'])[:19]:20s} {str(e['rank']):>4s} {str(e['score']):>6s} "
            f"{str(e['vocal']):>5s} {str(e['dance']):>5s} {str(e['visual']):>5s} {str(e['actions']):>6d}"
        )
    totals = [e["score"] for e in exams if isinstance(e["score"], int)]
    if totals:
        print(f"\n共 {len(exams)} 场，分数合计 {sum(totals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
