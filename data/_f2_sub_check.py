"""一次性：Windows 上复刻 gkbench submissions check 的格式校验（fcntl 仅 Unix）。"""
import json
import re
from pathlib import Path

root = Path(r"D:\Games\gakumas-agent\data\bench_repo\submissions")
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
OFFICIAL = ("hif", "nia", "hajime", "idolroad")
labels = {}
for f in sorted(root.glob("*/submission.json")):
    if f.parent.name.startswith((".", "_")):
        continue
    cfg = json.loads(f.read_text(encoding="utf-8"))
    errs = []
    label = cfg.get("label") or ""
    if not LABEL_RE.match(label):
        errs.append(f"label invalid: {label!r}")
    if label in labels:
        errs.append("duplicate label")
    labels[label] = f.parent.name
    entry = cfg.get("entry") or ""
    file, _, cls = entry.partition(":")
    if not file.endswith(".py") or not cls or not (f.parent / file).is_file():
        errs.append(f"entry invalid: {entry!r}")
    sets = cfg.get("sets") or ["hif"]
    if [s for s in sets if s not in OFFICIAL]:
        errs.append("bad sets")
    step = float(cfg.get("step_seconds", 5))
    if not 0 < step <= 10:
        errs.append("bad step_seconds")
    if not isinstance(cfg.get("params", {}), dict):
        errs.append("params not object")
    status = ("ERR " + "; ".join(errs)) if errs else "OK  "
    print(status, f.parent.name, "->", label)