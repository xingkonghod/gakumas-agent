"""B9 文档数字收尾：把 expectimax A/B 换成最终重跑数字。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLACEMENTS = {
    "docs/HANDOVER_NEXT.md": [
        (
            "**+110.3（+2.87%，CI [+39.6,+193.3]，20胜/2负/38平）** / expectimax +48.2（CI 含 0）；",
            "**+110.3（+2.87%，CI [+39.6,+193.3]，20胜/2负/38平）** / expectimax +156.2（CI 含 0）；",
        ),
        (
            "CI[+39.6,+193.3]，20胜/2负/38平）** / expectimax 3749.1→**3797.2（+48.2，CI 含 0，墙钟噪声）**。",
            "CI[+39.6,+193.3]，20胜/2负/38平）** / expectimax 3666.5→**3822.8（+156.2，CI 含 0，墙钟噪声）**。",
        ),
        (
            "**3951.0（+110.3，+2.87%，CI[+39.6,+193.3]）** / expectimax +48.2（CI 含 0）。",
            "**3951.0（+110.3，+2.87%，CI[+39.6,+193.3]）** / expectimax +156.2（CI 含 0）。",
        ),
    ],
    "docs/INDEX.md": [
        ("expectimax +48.2（CI 含 0，墙钟噪声）；", "expectimax +156.2（CI 含 0，墙钟噪声）；"),
    ],
    "README.md": [
        ("expectimax +48.2（CI 含 0）；", "expectimax +156.2（CI 含 0）；"),
    ],
}


def main() -> int:
    for relative, pairs in REPLACEMENTS.items():
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        for old, new in pairs:
            if old not in text:
                print(f"SKIP（未命中）：{relative}: {old[:50]}")
                continue
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        print(f"updated {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
