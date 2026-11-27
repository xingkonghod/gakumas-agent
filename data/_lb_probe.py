"""Read-only probe: gkbench leaderboard + runs summary (not committed)."""
import json
import urllib.request

BASE = "https://hiro.matto.top/gkbench/api"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as f:
        return json.load(f)

def show_lb(kind):
    rows = get(f"/leaderboard?set=hif&kind={kind}")
    rows = [r for r in rows if r.get("label")]
    rows.sort(key=lambda r: -(r.get("mean") or 0))
    print(f"=== leaderboard kind={kind} rows={len(rows)} ===")
    for r in rows[:25]:
        about = r.get("about") or {}
        eng = r.get("engine") or {}
        print(
            f"{r.get('mean', 0):>12,.0f} n={r.get('n'):<4} mode={r.get('mode'):<7}"
            f" rules={eng.get('rules_version')} by={r.get('by')} sees={about.get('sees')}"
            f" over={r.get('over')} algo={r.get('algo')} label={r.get('label')}"
        )

def show_runs():
    rows = get("/runs?set=hif")
    ours = [r for r in rows if str(r.get("by")) == "xingkonghod"]
    ours.sort(key=lambda r: str(r.get("started_at") or r.get("run")), reverse=True)
    print(f"=== our runs ({len(ours)}/{len(rows)}) ===")
    for r in ours[:30]:
        print(
            f"{r.get('run')} mean={r.get('mean')} n={r.get('n')} kind={r.get('kind')}"
            f" mode={r.get('mode')} errors={r.get('errors')} over={r.get('over')}"
            f" label={r.get('label')} algo={r.get('algo')}"
        )

if __name__ == "__main__":
    import sys
    if "runs" in sys.argv:
        show_runs()
    else:
        show_lb("template")
        show_lb("fixed")