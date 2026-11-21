"""重建「考试时刻的牌堆」。

真正的当前培育牌组 = UserData.userProduceProgressProduceCardList (field 309641228)。
元素 UserProduceProgressProduceCard:
  number=2(int 唯一实例号), produceCardId=3(str), upgradeCount=4(int),
  deleted=6(bool), originType=7(enum), produceCardSkinId=20(str)
（注意：field 230550472 的 UserProduceCardList 是图鉴/收集库，不是牌堆。）

考试牌堆 = 该列表里 deleted=false 的卡。客户端用 NativeRandom(examSeedValue) 洗牌。

本脚本：
  1. 扫描全部流量，按出现顺序列出每次 userProduceProgressProduceCardList 更新。
  2. 用 Number 做 upsert 维护牌组状态（deleted=true 移除）。
  3. 在每个 StepAuditionStart 时刻打印当前牌堆（供洗牌重放对照）。

用法：python scripts/reconstruct_deck.py [--file PATH] [--verbose]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
FIELD = 309641228
KEY = FIELD << 3 | 2


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


def parse_card(buf: bytes) -> dict | None:
    i = 0
    card: dict = {}
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
            if field == 2:
                card["number"] = value
            elif field == 4:
                card["upgrade"] = value
            elif field == 6:
                card["deleted"] = bool(value)
            elif field == 7:
                card["origin"] = value
            elif field == 11:
                card["customizing"] = bool(value)
        elif wire == 2:
            try:
                length, i = varint(buf, i)
            except IndexError:
                return None
            sub = buf[i : i + length]
            i += length
            if field == 3:
                try:
                    card["id"] = sub.decode("utf-8")
                except UnicodeDecodeError:
                    return None
            elif field == 20:
                try:
                    card["skin"] = sub.decode("utf-8")
                except UnicodeDecodeError:
                    pass
            # field 10 customizes: 跳过（暂不解析）
        else:
            return None
    if "id" not in card or "number" not in card:
        return None
    card.setdefault("upgrade", 0)
    card.setdefault("deleted", False)
    return card


def find_cards(body: bytes) -> list[tuple[int, dict]]:
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
        if 0 < length <= 512 and after + length <= len(body):
            card = parse_card(body[after : after + length])
            if card and card["id"].startswith("p_card-"):
                out.append((idx, card))
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


def fmt(card: dict) -> str:
    s = f"#{card['number']} {card['id']}+{card['upgrade']}"
    if card.get("deleted"):
        s += " [删]"
    return s


def load_records(path: Path) -> list[dict]:
    """读 traffic.jsonl（坏行跳过）。"""
    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def build_snapshots(
    path: Path, *, verbose: bool = False, quiet: bool = False
) -> list[dict]:
    """重放 traffic 里的牌组更新，返回每个 ``StepAuditionStart`` 时刻的牌组快照。

    返回元素 ``{"record": traffic 行号, "ts": ..., "deck": [未删除卡片, 按 number 升序]}``。
    生产接线（``build_exam_setup.py --current``）用它拿「最近一场考试」的牌组；
    不写文件、不打印（``quiet=True``），可安全在跑局中调用。
    """
    records = load_records(path)
    if not quiet:
        print(f"key bytes = {KEY_BYTES.hex()}  共 {len(records)} 条记录\n")
    deck: dict[int, dict] = {}  # number -> card
    hits = 0
    snapshots: list[dict] = []
    for n, rec in enumerate(records):
        rec_path = rec.get("path", "")
        is_audition_start = rec_path.endswith("StepAuditionStart")
        # Produce/Start 与 User/Get 下发全量快照 → 整体替换；其余响应按 Number 增量 upsert
        is_snapshot = rec_path.endswith(("Produce/Start", "User/Get"))
        for which in ("req_plain_hex", "resp_plain_hex"):
            b = body(rec, which)
            if b is None:
                continue
            cards = find_cards(b)
            if cards:
                hits += 1
                if is_snapshot:
                    deck = {c["number"]: c for _, c in cards}
                else:
                    for _, card in cards:
                        deck[card["number"]] = card
                if not quiet:
                    mode = "快照" if is_snapshot else "增量"
                    print(
                        f"[{n}] {rec.get('ts')} {rec_path} [{which[:4]}] "
                        f"{mode} {len(cards)} 张"
                    )
                    if verbose or len(cards) <= 6:
                        for _, card in cards:
                            print("     " + fmt(card))
            if is_audition_start and which == "resp_plain_hex":
                alive = [c for c in deck.values() if not c.get("deleted")]
                alive.sort(key=lambda c: c["number"])
                snapshots.append({"record": n, "ts": rec.get("ts"), "deck": alive})
                if not quiet:
                    print(f"\n  >>> 考试时刻牌堆（{len(alive)} 张未删除，按 Number 排序）:")
                    for card in alive:
                        print("      " + fmt(card))
                    print()
    if not quiet:
        print(
            f"共 {hits} 次牌组更新；最终状态 {len(deck)} 个实例，"
            f"{sum(1 for c in deck.values() if not c.get('deleted'))} 张未删除"
        )
    return snapshots


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    snapshots = build_snapshots(Path(args.file), verbose=args.verbose)
    out = Path(args.file).parent / "deck_snapshots.json"
    out.write_text(json.dumps(snapshots, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"考试时刻牌堆已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

