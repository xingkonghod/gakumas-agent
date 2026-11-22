"""批量下载 gkbench 公开数据（Phase F0：题模板 / 各算法 run / 局记录）。

来源：gkbench 公开只读接口（`https://hiro.matto.top/gkbench/api/...`，见本地克隆
`data/bench_repo/server/routes.go`）：

- ``/api/sets``                            题集列表
- ``/api/runs?set=<set>``                  某题集全部运行（算法/模式/均分/规则版本）
- ``/api/runs/<run>``                      一次运行的逐局摘要（**含 route 出牌路线**）
- ``/api/runs/<run>/episodes/<id>/<seed>`` 逐局完整记录（steps/观测；保密种子需登录，无令牌会 403）
- ``/api/sets/<set>/saves?answers=1``      题模板存档 NDJSON（每行一题：编成 + 公开算法的答/路线）
- ``/api/leaderboard?set=<set>``           排行/参考分（含 vs_oracle）

用法（默认只下 hif + 四个目标算法；逐局 steps 默认就下，token 可选、只影响保密种子逐局记录）::

    .venv\\Scripts\\python.exe scripts\\bench_download.py --sets hif --algos external:uinet,external:uihorizon,external:official-ai,external:best-known
    .venv\\Scripts\\python.exe scripts\\bench_download.py --sets all --no-episodes --no-saves
    # 有登录令牌时（网页 /me → 命令行令牌）：
    $env:GKBENCH_TOKEN="..."; .venv\\Scripts\\python.exe scripts\\bench_download.py --sets hif

数据写 ``data/bench_local/gkbench_dl/<set>/``（gitignore，不入库）。可重复执行：已有文件跳过。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://hiro.matto.top/gkbench"
UA = "gkagent-research/0.1"
DEFAULT_ALGOS = (
    "external:uinet",
    "external:uihorizon",
    "external:official-ai",
    "external:best-known",
)
DEFAULT_OUT = ROOT / "data" / "bench_local" / "gkbench_dl"
# 与 gkbench 官方 CLI 一致：令牌优先 GKBENCH_TOKEN，其次 ~/.config/gkbench/token
TOKEN_FILE = Path(
    os.environ.get("GKBENCH_TOKEN_FILE", Path.home() / ".config/gkbench/token")
).expanduser()


def default_token() -> str:
    env = os.environ.get("GKBENCH_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_FILE.is_file():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""


class Client:
    """带限速/重试的只读客户端；token 可选（保密种子逐局记录要登录）。"""

    def __init__(self, base: str = BASE, token: str = "", sleep_s: float = 0.25) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.sleep_s = max(0.0, float(sleep_s))
        self.calls = 0

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": UA}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def open(self, path: str):
        url = f"{self.base}{path}"
        last: Exception | None = None
        for attempt in range(4):
            if self.calls:
                time.sleep(self.sleep_s)
            self.calls += 1
            try:
                req = urllib.request.Request(url, headers=self._headers())
                return urllib.request.urlopen(req, timeout=180)
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 401, 403, 404):
                    raise
                last = exc
            except (urllib.error.URLError, TimeoutError) as exc:  # 网络抖动重试
                last = exc
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"GET {url} 失败：{last}")

    def get_json(self, path: str):
        with self.open(path) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def download(self, path: str, dest: Path) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with self.open(path) as resp, tmp.open("wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        tmp.replace(dest)
        return dest.stat().st_size


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(text))


def write_json(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path.stat().st_size


def _episode_is_secret_error(exc: urllib.error.HTTPError) -> bool:
    return exc.code in (401, 403)


def scan_output(out: Path, algos: list[str]) -> dict:
    """按磁盘实际文件重建 manifest（多次/断点续传后仍然准确）。"""
    summary = {"bytes": 0, "files": 0, "sets": {}}
    for set_dir in sorted(p for p in out.iterdir() if p.is_dir()):
        runs_file = set_dir / "runs.json"
        if not runs_file.is_file():
            continue
        runs = json.loads(runs_file.read_text(encoding="utf-8"))
        by_algo: dict[str, int] = {}
        for run in runs:
            algo = str(run.get("algo"))
            if algo in algos:
                by_algo[algo] = by_algo.get(algo, 0) + 1
        episodes = set_dir / "episodes"
        ep_count = sum(1 for _ in episodes.rglob("*.json")) if episodes.is_dir() else 0
        run_index_count = (
            sum(1 for _ in (set_dir / "runs").glob("*.json"))
            if (set_dir / "runs").is_dir()
            else 0
        )
        set_summary: dict = {
            "runs_total": len(runs),
            "target_runs": sum(by_algo.values()),
            "by_algo": by_algo,
            "run_index_files": run_index_count,
            "episodes_downloaded": ep_count,
        }
        seeds_file = set_dir / "seeds.json"
        if seeds_file.is_file():
            seeds = json.loads(seeds_file.read_text(encoding="utf-8")).get("problems") or {}
            set_summary["seeds_problems"] = len(seeds)
            set_summary["seeds_total"] = sum(len(rows) for rows in seeds.values())
        saves_file = set_dir / "saves.jsonl"
        if saves_file.is_file():
            set_summary["saves_bytes"] = saves_file.stat().st_size
            set_summary["saves_lines"] = sum(
                1 for line in saves_file.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        size = sum(p.stat().st_size for p in set_dir.rglob("*") if p.is_file())
        set_summary["bytes"] = size
        summary["bytes"] += size
        summary["files"] += sum(1 for _ in set_dir.rglob("*") if _.is_file())
        summary["sets"][set_dir.name] = set_summary
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--token", default=default_token())
    parser.add_argument("--sets", default="hif", help="题集 id，逗号分隔；all = 全部题集")
    parser.add_argument("--algos", default=",".join(DEFAULT_ALGOS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--sleep", type=float, default=0.25, help="请求间隔秒")
    parser.add_argument("--no-episodes", action="store_true", help="不下逐局 steps（只下 run 索引）")
    parser.add_argument(
        "--with-episodes",
        action="store_true",
        help="显式下逐局 steps（默认就下固定种子 run 的；与 --no-episodes 相斥，后者优先）",
    )
    parser.add_argument(
        "--runs",
        default="",
        help="只给这些 run id 下逐局 steps（逗号分隔；含保密种子 run，需令牌），默认只下 fixed run",
    )
    parser.add_argument("--no-saves", action="store_true", help="不下题模板存档 NDJSON")
    parser.add_argument("--no-leaderboard", action="store_true")
    parser.add_argument(
        "--no-seeds",
        action="store_true",
        help="不下开发集固定种子（/api/sets/<set>/seeds；需要令牌或题集 public_seeds）",
    )
    parser.add_argument(
        "--variants",
        action="store_true",
        help="除精确算法名外，也下同名变体（algo 含 uinet/uihorizon/official-ai/best-known）",
    )
    args = parser.parse_args(argv)

    algos = [a.strip() for a in args.algos.split(",") if a.strip()]
    force_runs = {x.strip() for x in args.runs.split(",") if x.strip()}
    tokens = [
        a.split(":", 1)[-1].lower().replace("_", "-") for a in algos
    ]

    def is_target(algo: str) -> bool:
        if algo in algos:
            return True
        if not args.variants:
            return False
        norm = algo.split(":", 1)[-1].lower().replace("_", "-")
        return any(token in norm for token in tokens)
    out = Path(args.out)
    client = Client(args.base, args.token, args.sleep)

    sets_doc = client.get_json("/api/sets")
    need_login: list[dict] = []
    bytes_total = write_json(out / "sets.json", sets_doc)
    print(f"题集 {len(sets_doc)} 个 → {out / 'sets.json'}")

    wanted_sets = [s["set"] for s in sets_doc] if args.sets.strip() == "all" else [
        s.strip() for s in args.sets.split(",") if s.strip()
    ]
    by_id = {s["set"]: s for s in sets_doc}

    for set_name in wanted_sets:
        if set_name not in by_id:
            print(f"⚠️ 题集 {set_name} 不存在，跳过")
            continue
        set_dir = out / set_name
        runs = client.get_json(f"/api/runs?set={set_name}")
        bytes_total += write_json(set_dir / "runs.json", runs)
        if not args.no_leaderboard:
            for kind in ("fixed", "template"):
                try:
                    lb = client.get_json(f"/api/leaderboard?set={set_name}&kind={kind}")
                    bytes_total += write_json(set_dir / f"leaderboard_{kind}.json", lb)
                except urllib.error.HTTPError as exc:
                    print(f"⚠️ {set_name} leaderboard[{kind}] 失败：{exc}")

        targets = [r for r in runs if is_target(str(r.get("algo")))]
        summary = {
            "set": set_name,
            "runs_total": len(runs),
            "target_runs": len(targets),
            "by_algo": {},
            "episodes_downloaded": 0,
            "episodes_login_required": 0,
        }
        # 开发集固定种子（seed + fixed_id + check{turn,score,stamina,hand,rules}）：
        # hif 的 public_seeds=false，要令牌；没有令牌时 401 跳过（不报错）。
        if not args.no_seeds:
            try:
                seeds_doc = client.get_json(f"/api/sets/{set_name}/seeds")
                bytes_total += write_json(set_dir / "seeds.json", seeds_doc)
                probs = seeds_doc.get("problems") or {}
                summary["seeds_problems"] = len(probs)
                summary["seeds_total"] = sum(len(rows) for rows in probs.values())
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    summary["seeds_need_token"] = True
                else:
                    print(f"⚠️ {set_name} seeds 失败：{exc}")
        for run in targets:
            algo = str(run.get("algo"))
            summary["by_algo"][algo] = summary["by_algo"].get(algo, 0) + 1
            run_id = str(run.get("run"))
            dest = set_dir / "runs" / f"{_safe_name(run_id)}.json"
            if dest.is_file():
                doc = json.loads(dest.read_text(encoding="utf-8"))
            else:
                doc = client.get_json(f"/api/runs/{run_id}")
                bytes_total += write_json(dest, doc)
            episodes = doc.get("episodes") or []
            fixed = str(run.get("kind")) == "fixed"
            do_episodes = bool(run_id in force_runs) if force_runs else fixed
            if args.no_episodes or not do_episodes or not episodes:
                summary["run_episodes"] = summary.get("run_episodes", 0) + len(episodes)
                continue
            ep_dir = set_dir / "episodes" / _safe_name(run_id)
            for ep in episodes:
                pid = str(ep.get("id") or "")
                si = ep.get("seed_index")
                if not pid or si is None:
                    continue
                ep_dest = ep_dir / f"{_safe_name(pid)}_{si}.json"
                if ep_dest.is_file():
                    summary["episodes_downloaded"] += 1
                    continue
                try:
                    ep_doc = client.get_json(f"/api/runs/{run_id}/episodes/{pid}/{si}")
                except urllib.error.HTTPError as exc:
                    if _episode_is_secret_error(exc):
                        summary["episodes_login_required"] += 1
                        need_login.append(
                            {"set": set_name, "run": run_id, "id": pid, "seed_index": si}
                        )
                        continue
                    raise
                bytes_total += write_json(ep_dest, ep_doc)
                summary["episodes_downloaded"] += 1
            summary["run_episodes"] = summary.get("run_episodes", 0) + len(episodes)

        if not args.no_saves:
            saves_dest = set_dir / "saves.jsonl"
            if saves_dest.is_file():
                bytes_total += saves_dest.stat().st_size
            else:
                try:
                    bytes_total += client.download(
                        f"/api/sets/{set_name}/saves?answers=1", saves_dest
                    )
                    summary["saves_bytes"] = saves_dest.stat().st_size
                except urllib.error.HTTPError as exc:
                    print(f"⚠️ {set_name} saves 失败：{exc}")

        print(
            f"[{set_name}] runs={len(runs)} 目标运行={len(targets)} "
            f"逐局={summary['episodes_downloaded']} 需登录={summary['episodes_login_required']} "
            f"by_algo={summary['by_algo']}"
        )

    scan = scan_output(out, algos)
    manifest = {
        "base": args.base,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "algos": algos,
        "variants": bool(args.variants),
        "with_token": bool(args.token),
        "last_run_requests": client.calls,
        "need_login_episodes": need_login,
    }
    manifest.update(scan)
    write_json(out / "manifest.json", manifest)
    print(
        f"\n完成：本次 {client.calls} 次请求；磁盘共 {scan['files']} 文件 / "
        f"{scan['bytes'] / 1e6:.1f} MB → {out}"
    )
    if need_login:
        print(f"需登录的逐局记录 {len(need_login)} 条（带 token 重跑同一命令补齐）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
