"""Read-only probe: our gkbench runs detail (not committed)."""
import json
import urllib.request

BASE = "https://hiro.matto.top/gkbench/api"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as f:
        return json.load(f)

def main():
    rows = get("/runs?set=hif")
    ours = [r for r in rows if str(r.get("by")) == "xingkonghod"]
    for r in ours:
        print(json.dumps({k: r.get(k) for k in (
            "run", "label", "algo", "kind", "mode", "n", "mean", "errors", "over",
            "ep_think_s", "step_seconds", "started_at", "finished_at", "rules", "engine")},
            ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()