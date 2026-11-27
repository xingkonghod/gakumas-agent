"""臂A 被清评测已落盘 episodes vs v2 同题同种子配对（探针，不提交）。"""
import json
import random
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERVER = "https://hiro.matto.top/gkbench"
tok = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()


def client():
    return httpx.Client(base_url=SERVER, headers={"Authorization": f"Bearer {tok}"}, timeout=120)


def episodes(c, run):
    for i in range(6):
        try:
            j = c.get(f"/api/runs/{run}", timeout=120).raise_for_status().json()
            break
        except Exception as e:
            print(i, "retry", type(e).__name__, flush=True)
            time.sleep(5)
    else:
        raise SystemExit(f"fetch fail {run}")
    eps = j["episodes"] if isinstance(j, dict) else j
    out = {}
    for e in eps:
        if not e.get("finished"):
            continue
        out[(e["id"], int(e["seed_index"]))] = {
            "score": int(e["score"]), "over": int(e.get("over_steps") or 0),
        }
    return out


def boot_ci(d, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(d)
    means = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def main():
    v3run = sys.argv[1] if len(sys.argv) > 1 else "template-hif-gkagent-ex-seed-v3-xingkonghod-9ba9c00fb468"
    v2run = "template-hif-gkagent-ex-seed-v2-xingkonghod-db12324b5d57"
    with client() as c:
        a = episodes(c, v3run)
        b = episodes(c, v2run)
    keys = sorted(set(a) & set(b))
    d = [a[k]["score"] - b[k]["score"] for k in keys]
    lo, hi = boot_ci(d)
    wins = sum(1 for x in d if x > 0)
    loss = sum(1 for x in d if x < 0)
    tie = sum(1 for x in d if x == 0)
    print(json.dumps({
        "n_pairs": len(keys), "v3_partial_mean": sum(a[k]["score"] for k in keys) / len(keys),
        "v2_same_mean": sum(b[k]["score"] for k in keys) / len(keys),
        "mean_delta": sum(d) / len(d), "ci95": [lo, hi], "wins": wins, "loss": loss, "ties": tie,
        "v3_over": sum(a[k]["over"] for k in keys), "v2_over": sum(b[k]["over"] for k in keys),
        "top_pos": sorted(((d[i], keys[i]) for i in range(len(d))), reverse=True)[:5],
        "top_neg": sorted(((d[i], keys[i]) for i in range(len(d))))[:5],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()