"""One-shot doc patch helper: replace a line range in a UTF-8 file."""
import sys
from pathlib import Path

path = Path(sys.argv[1])
start = int(sys.argv[2])  # 1-based inclusive
end = int(sys.argv[3])    # 1-based inclusive
new = Path(sys.argv[4]).read_text(encoding="utf-8")

lines = path.read_text(encoding="utf-8").splitlines()
assert 1 <= start <= end <= len(lines), (start, end, len(lines))
out = lines[: start - 1] + new.splitlines() + lines[end:]
path.write_text("\n".join(out) + ("\n" if path.read_text(encoding="utf-8").endswith("\n") else ""), encoding="utf-8")
print(f"patched {path}: lines {start}-{end} -> {len(new.splitlines())} lines; total {len(out)}")
