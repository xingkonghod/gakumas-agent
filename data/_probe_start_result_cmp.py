"""一次性探针②：对比全部 Produce/Start 与 Produce/Result（5 Start / 3 Result），
确认 ep-t31 与手动 B/7404 局的 produce id/难度是否相同 + 最终评价点字段定位。不提交。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dig_traffic import decode, parse  # noqa: E402
from extract_exams import field_map  # noqa: E402

TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")


def fmap(nodes):
    return field_map(nodes)


def get(nodes, *path):
    cur = nodes
    for p in path:
        if not isinstance(cur, list):
            return None
        m = fmap(cur)
        cur = m.get(p)
    return cur


def allf(nodes, f):
    if not isinstance(nodes, list):
        return []
    return [v for ff, _, v in nodes if ff == f]


def main() -> int:
    recs = []
    for line in TRAFFIC.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    print("== 全部 Produce/Start（请求关键字段）==")
    for i, r in enumerate(recs):
        if not r.get("path", "").endswith("Produce/Start"):
            continue
        body = decode(r, "req_plain_hex")
        if body is None:
            continue
        top = parse(body)
        m = fmap(top)
        print(f"\n#{i} {r.get('ts')}")
        print(f"  f1={m.get(1)} f2={m.get(2)} f7={m.get(7)} f99={m.get(99)}")
        # 响应里的 produce 概要 374217157
        resp = decode(r, "resp_plain_hex")
        if resp is None:
            continue
        rtop = parse(resp)
        # 9999.1.374217157
        n9999 = get(rtop, 9999)
        n1 = get(n9999, 1) if isinstance(n9999, list) else None
        summ = None
        if isinstance(n1, list):
            for ff, _, v in n1:
                if ff == 374217157:
                    summ = v
        if isinstance(summ, list):
            sm = fmap(summ)
            keys = [5, 9, 10, 20, 100, 101, 103, 105, 121, 200, 201, 202, 203, 204, 205, 220, 221, 230, 311, 315, 504, 608, 609, 610]
            print("  resp概要374217157:", {k: sm.get(k) for k in keys if k in sm})
            print("  resp概要510(考试):", allf(summ, 510))

    print("\n== 全部 Produce/Result（响应关键字段）==")
    for i, r in enumerate(recs):
        if not r.get("path", "").endswith("Produce/Result"):
            continue
        resp = decode(r, "resp_plain_hex")
        if resp is None:
            continue
        rtop = parse(resp)
        n9999 = get(rtop, 9999)
        n1 = get(n9999, 1) if isinstance(n9999, list) else None
        print(f"\n#{i} {r.get('ts')}")
        if not isinstance(n1, list):
            continue
        for ff, _, v in n1:
            if ff == 110043881 and isinstance(v, list):
                print(f"  110043881(评价?): {fmap(v)}")
            if ff == 163783316 and isinstance(v, list):
                vm = fmap(v)
                print(f"  163783316(偶像记录): 8={vm.get(8)} 9={vm.get(9)} 14={vm.get(14)} 15={vm.get(15)} 16={vm.get(16)} 30/31/32={vm.get(30)}/{vm.get(31)}/{vm.get(32)} 33={vm.get(33)} 99={vm.get(99)} 100={vm.get(100)}")
            if ff == 374217157 and isinstance(v, list):
                sm = fmap(v)
                keys = [100, 101, 103, 105, 121, 200, 201, 202, 203, 204, 205, 220, 221, 230, 311, 315, 504, 650]
                print("  374217157(概要):", {k: sm.get(k) for k in keys if k in sm})
                print("  510(考试):", allf(v, 510))
                print("  620:", sm.get(620))
            if ff == 49977942 and isinstance(v, list):
                vm = fmap(v)
                print(f"  49977942: 4={vm.get(4)} 5={vm.get(5)} 10={vm.get(10)} 11={vm.get(11)} 12={vm.get(12)} 13={vm.get(13)} 14={vm.get(14)}")
            if ff == 494627662 and isinstance(v, list):
                print(f"  494627662: {fmap(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())