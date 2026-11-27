# gkagent-seedlock — seed-lock + GKMS 官方引擎 GNRPA 的 gkbench 投稿适配器。
# Copyright (C) 2026 gkagent contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# 思路（对标 UIHorizon-v2.2b-Gratwanderung，去掉 ONNX 网络，搜索全部走官方引擎原生 GNRPA）：
#   1. begin：用引擎在 6 个任意种子下开局，得到与种子无关的 pre（洗牌前牌序）、k（洗牌前 RNG 调用数）、
#      invariant hand（考试放置/创建的牌）；回合属性池来自引擎的 audition_parameter_values。
#   2. decide（锁定前）：从公开 obs 累积抽牌序（Draws）；seed_scan 内核并行分段扫 [0, hi)，
#      过滤条件 = 回合属性 + 洗牌后抽牌序（skip 放置牌/效果移牌）。候选多时随抽牌增加重扫，
#      候选少时用引擎 FastCut（复用 loading，~3ms/种子）按历史手牌逐一筛。
#   3. 唯一候选且引擎重建与画面一致 → 锁定。锁定后整局确定：NativeSearch.policy_search GNRPA
#      搜整场路线，路线池每步可重搜（取终局分更高者），照着路线首动作打。
#   4. 锁定前/丢失后：引擎卡表贪心兜底。硬规矩 forced_play（缺省 1 开）：legal 里有 play 绝不 end；
#      托管评测 obs 完美，可 forced_play=0 关掉（允许 GNRPA 为蓄体力主动 end）。
#
# 只读 ctx.obs / ctx.loadout / ctx.meta，不用 ctx.worlds，不拿裁判的种子（sees_seed 类属性 False，
# 托管门禁要求；about.sees="seed" 如实声明「锁定后看牌序」，网站按此标看牌序，UIHorizon 同先例）。
#
# 引擎：GKMS_ROOT（默认 <repo>/data/GKMSMainWheel，AGPL）+ 原生核心 gkmscore.dll（vendor/ 随提交带）。
# 模块导入时自配置 gkbench.engine 的路径常量（evaluate() 先 import engine 后 make 算法，env 来不及设）。
from __future__ import annotations

import atexit
import copy
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path

try:
    from gkbench.algos.base import Algorithm, Decision
except ImportError:                                    # 离线探针：同样的两个形状
    from dataclasses import dataclass, field

    @dataclass
    class Decision:
        action: tuple
        meta: dict = field(default_factory=dict)

    class Algorithm:
        name = "base"
        privileged = False
        needs_gkms = False
        sees_seed = False

        def __init__(self, **params):
            self.params = params

        def describe(self):
            return {"name": self.name, "params": self.params, "privileged": False, "sees_seed": False}


SUB = Path(__file__).resolve().parent
VENDOR = SUB / "vendor"
_DATA = SUB.parents[2]                                 # submissions/gkagent-seedlock → submissions → bench_repo → data
_GKMS_DEFAULT = _DATA / "GKMSMainWheel"
_OPEN_LOCK = threading.Lock()                          # FastCut.open 期间共享 loading，跨线程实例串行化


def _configure_engine_paths():
    """GKMS_ROOT / 原生核心路径：env 优先，否则仓库内默认；同步已导入的 gkbench.engine 常量。"""
    root = Path(os.environ.get("GKMS_ROOT", "")).expanduser() if os.environ.get("GKMS_ROOT") else None
    if root is None or not (root / "GakumasCLI").is_dir():
        root = _GKMS_DEFAULT
    if not (root / "GakumasCLI").is_dir():
        return None
    dll = VENDOR / "gkmscore.dll"
    if not dll.is_file():
        dll = root / "GakumasCLI" / "native" / "build" / ("gkmscore.dll" if os.name == "nt" else "libgkmscore.so")
    os.environ["GKMS_ROOT"] = str(root)
    os.environ["GKMSCLIGPU_LIB"] = str(dll)
    os.environ["GKMS_NATIVE_LIB"] = str(dll)
    eng = sys.modules.get("gkbench.engine")
    if eng is not None:
        eng.GKMS_ROOT = root
        eng.NATIVE_LIB = dll
        eng.MASTER_DIR = root / "GakumasCLI" / "ro" / "master" / "tables"
    return root


_ENGINE_ROOT = _configure_engine_paths()


# ---------------------------------------------------------------- 抽牌序跟踪（语义同 UIHorizon vendor/bench/draws.py）
class Draws:
    """从 UIObs 读出的抽牌序：seen（按抽牌序的卡 id）、skip（没经抽牌离开牌堆的卡）、open（牌堆顺序还可读）。"""

    def __init__(self, pre, inv=None):
        self.pre = Counter(pre)
        self.inv = Counter(inv or ())
        self.left = None
        self.seen = []
        self.skip = Counter()
        self.open = True

    def update(self, obs):
        if not self.open:
            return
        left = self.pre - Counter(c["id"] for c in obs["deck"])
        hand = [c["id"] for c in obs["hand"]]
        if self.left is None:                          # 开局：放置/创建的牌在前，其后是抽到的
            skip, order = Counter(self.inv), []
            for x in hand:
                if skip[x] > 0:
                    skip[x] -= 1
                else:
                    order.append(x)
            rest, drawn = Counter(left), []
            for x in order:                            # 手牌里不属于牌堆的：考试创建，不是抽牌
                if rest[x] > 0:
                    rest[x] -= 1
                    drawn.append(x)
            self.skip = rest
            self.seen += drawn
            self.left = left
            return
        if self.left - left:                           # 有牌回到牌堆（洗回/创建）：顺序不再可读
            self.open = False
            return
        need = left - self.left
        if need:
            order = []
            for x in reversed(hand):                   # 新抽的牌在手牌末尾
                if need[x] > 0:
                    need[x] -= 1
                    order.append(x)
            self.skip += need                          # 离开牌堆但没进手牌：效果移除，扫描时跳过
            self.seen += reversed(order)
        self.left = left


# ---------------------------------------------------------------- seed_scan 内核与后台扫描
_KERNEL_DIR = Path(tempfile.gettempdir()) / "gkagent-seedlock-kernel"
_NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


def kernel():
    """vendor/seed_scan.exe 直接用；没有就用 gcc/clang 现编到临时目录。"""
    exe = VENDOR / ("seed_scan.exe" if os.name == "nt" else "seed_scan")
    if exe.is_file():
        if os.name != "nt" and not os.access(exe, os.X_OK):
            os.chmod(exe, 0o755)
        return exe
    _KERNEL_DIR.mkdir(parents=True, exist_ok=True)
    out = _KERNEL_DIR / ("seed_scan.exe" if os.name == "nt" else "seed_scan")
    if out.is_file():
        return out
    src = VENDOR / "seed_scan.c"
    gccs = ["gcc", "clang", "cc"]
    w64 = _DATA / "_f2sl_tools" / "w64devkit" / "bin" / "gcc.exe"
    if w64.is_file():
        gccs.insert(0, str(w64))
    for cc in gccs:
        exe_path = shutil.which(cc) if not os.path.isabs(cc) else cc
        if not exe_path:
            continue
        try:
            subprocess.run([exe_path, "-O3", str(src), "-o", str(out)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_NO_WINDOW)
        except (OSError, subprocess.CalledProcessError):
            continue
        if out.is_file():
            return out
    return None


class Scan:
    """[lo, hi) 分 procs 段并行扫；poll() 非阻塞，全部进程结束后返回排序种子表。"""

    def __init__(self, exe, k, pre, seen, skip, pool=None, turns=None, procs=8, lo=0, hi=1 << 32):
        names = {v: i for i, v in enumerate(sorted(set(pre)))}
        if len(names) > 255 or any(x not in names for x in seen):
            raise ValueError("observed cards not in the deck")
        ints = lambda xs: ",".join(str(names[x]) for x in xs) or "-"   # noqa: E731
        self.started = time.perf_counter()
        self.seconds = None
        self.dir = tempfile.mkdtemp(prefix="gksl_scan_")
        self.jobs = []
        step = -(-(hi - lo) // procs)
        for i in range(procs):
            a, b = lo + i * step, min(hi, lo + (i + 1) * step)
            if a >= b:
                break
            args = [str(exe), str(int(k)), ints(pre), ints(seen), ints([x for x in skip if x in names]), str(a), str(b)]
            if pool and turns:
                args += [",".join(str(int(t)) for t in pool), ",".join(str(int(t)) for t in turns)]
            out = open(os.path.join(self.dir, f"{i}.txt"), "w")
            self.jobs.append((subprocess.Popen(args, stdout=out, stderr=subprocess.DEVNULL, **_NO_WINDOW), out))
        self._result = None
        atexit.register(self.stop)

    def poll(self):
        if self._result is not None:
            return self._result
        if any(p.poll() is None for p, _f in self.jobs):
            return None
        seeds = []
        for i, (p, f) in enumerate(self.jobs):
            f.close()
            if p.returncode != 0:
                raise RuntimeError(f"seed_scan exited with {p.returncode}")
            for line in open(os.path.join(self.dir, f"{i}.txt")):
                if line.strip() and not line.startswith("#"):
                    seeds.append(int(line))
        self.seconds = time.perf_counter() - self.started
        shutil.rmtree(self.dir, ignore_errors=True)
        self._result = sorted(seeds)
        return self._result

    def stop(self):
        if self._result is not None:
            return
        for p, f in self.jobs:
            if p.poll() is None:
                p.terminate()
            f.close()
        shutil.rmtree(self.dir, ignore_errors=True)


# ---------------------------------------------------------------- 引擎快筛（复用 loading）
class FastCut:
    """loading 建一次（与种子无关），每个种子只改 rng.state/config.seed 再 open；~3ms/种子。

    只按手牌筛：可能放过错种子，不会漏掉真种子（锁定时再整屏核对）。"""

    def __init__(self, master, loadout):
        from GakumasCLI.native import native_session as NS
        from GakumasCLI.scenario.exam_session import deferred_open
        from GakumasCLI.scenario.hif import build_hif_loadout_session
        self.NS = NS
        self.lo = dict(loadout)
        with deferred_open():
            self.loading, self.meta = build_hif_loadout_session(master, dict(self.lo, seed=1))
        self.config = self.loading.config

    def open(self, seed):
        seed = int(seed)
        ld = self.loading
        ld.deck.rng.state = seed & 0xFFFFFFFF
        ld.config = copy.copy(self.config)
        ld.config.seed = seed
        with _OPEN_LOCK:
            return self.NS.open_loading(ld, dict(self.lo, seed=seed), seed)

    def follows(self, seed, actions, hands):
        try:
            s = self.open(seed)
            for a, hand in zip(actions, hands):
                if [c["produce_card_id"] for c in s.deck.hand] != hand:
                    return False
                s.step(tuple(a), observe=False)
            return [c["produce_card_id"] for c in s.deck.hand] == hands[len(actions)]
        except Exception:                              # noqa: BLE001 -- 这个种子的对局走不了这些动作
            return False


def _hand_ids(session):
    return [c["produce_card_id"] for c in session.deck.hand]


def _mirror_key(session):
    st = session.state
    return (_hand_ids(session), int(session.turn), int(st.score), int(st.stamina), int(st.block), int(st.playable))


def _obs_key(obs):
    return ([c["id"] for c in obs["hand"]], int(obs["exam"]["turn"]), int(obs["num"]["score"]),
            int(obs["num"]["stamina"]), int(obs["num"]["block"]), int(obs["num"]["playable"]))


def _replay_score(session, route):
    """路线在副本上回放到终局的分数；走不完返回 None。"""
    c = session.clone()
    try:
        for a in route:
            if c.finished:
                break
            c.step(tuple(a), observe=False)
    except Exception:                                  # noqa: BLE001
        return None
    return int(c.state.score) if c.finished else None


# ---------------------------------------------------------------- 路线池（GNRPA，无网络）
class RoutePool:
    """锁定后：整局是一条确定性问题。每步 GNRPA 出一条完整路线，回放核分，终局分更高者替换在手路线。

    在手路线的分数是已经保住的：后续短搜不会让终局分下降。参考 UIHorizon vendor/uihorizon/pool.py。"""

    def __init__(self, ns, prior=None, stabilization=3, seed=182):
        self.ns, self.prior = ns, prior
        self.stabilization, self.seed = int(stabilization), int(seed)
        self.route, self.target, self.n = [], -1, 0
        self.stats = {"searches": 0, "adopted": 0, "bad_routes": 0, "transitions": 0}

    def reset(self):
        self.route, self.target, self.n = [], -1, 0
        self.stats = {"searches": 0, "adopted": 0, "bad_routes": 0, "transitions": 0}

    def search_offer(self, session, transitions, seconds):
        """从 session 当前状态搜一条路线并尝试采纳。返回 stats（失败 None）。"""
        try:
            self.ns._cache = None                      # 强制重导入当前状态（teacher.py 同口径）
            path, st = self.ns.policy_search(session, transitions=int(transitions), deadline=float(seconds),
                                             seed=self.seed + 1009 * self.n, variant="gnrpa",
                                             stabilization=self.stabilization, prior=self.prior)
        except Exception:                              # noqa: BLE001 -- 核心拒绝的状态：没有提案
            return None
        self.stats["searches"] += 1
        self.stats["transitions"] += int(st.get("expansions") or 0)
        if int(st.get("status", 0)) != 0 or not path:
            return st
        route = [tuple(a) for a in path]
        score = _replay_score(session, route)
        if score is None:
            self.stats["bad_routes"] += 1
        elif score > self.target:
            self.route, self.target = route, score
            self.stats["adopted"] += 1
        return st

    def take(self):
        if not self.route:
            return None
        action, self.route = self.route[0], self.route[1:]
        self.n += 1
        return tuple(action)

    def played(self, action):
        """实际打出的不是 decide 给的动作（强制/兜底）：路线首动作一致则续，否则丢弃。"""
        if self.route and tuple(self.route[0]) == tuple(action):
            self.route = self.route[1:]
        else:
            self.route, self.target = [], -1
        self.n += 1


# ---------------------------------------------------------------- 算法
class _Game:
    def __init__(self):
        self.state = "none"                            # none → scanning → candidates → locked | lost | failed
        self.actions = []
        self.hands = []
        self.scan = None
        self.scan_draws = 0
        self.scan_s = None
        self.cands = None
        self.cut_pos = 0
        self.kept = []
        self.lock_turn = None
        self.lost_turn = None
        self.why = None
        self.counts = {}
        self.rescans = 0


class SeedLockAlgo(Algorithm):
    name = "gkagent-seedlock"
    title = "gkagent-seedlock"
    needs_gkms = True
    sees_seed = False                                  # 托管门禁；种子从公开 obs 自反推，about.sees="seed" 如实声明
    about = {
        "summary": "从公开观测（回合属性、抽牌序）反推牌序种子；锁定后用 GKMS 官方引擎原生 GNRPA 搜整场路线，"
                   "路线池每步重搜取终局分更高者照着打。无 ONNX 网络，搜索全走官方引擎。",
        "detail": ["只读 ctx.obs / ctx.loadout，不用 ctx.worlds，不拿裁判的种子",
                   "种子由 seed_scan 内核并行分段扫 [0,2^32) 反推，引擎快筛 + 整屏核对锁定，通常第 1–3 回合",
                   "锁定后整局确定：NativeSearch GNRPA（官方 gkmscore.dll）路线池，回放核分采纳",
                   "锁定前/丢失后引擎卡表贪心兜底；硬规矩 forced_play（缺省开）：有可出牌绝不 end",
                   "成绩应与看牌序的算法对照（UIHorizon 同类）"],
        "sees": "seed",
        "family": "gkagent-seedlock", "family_name": "gkagent-seedlock",
    }

    def __init__(self, procs=8, hi=1 << 31, scan_min=6, step_trans=300000, lock_trans=1000000,
                 stabilization=3, prior=0, rescan_above=256, forced_play=1, report=1, **kw):
        # hi 缺省 2^31：gkbench 的全部种子（固定题 dev 种子与保密模板 HMAC mod (2^31-2)+1，server/tseeds.go）
        # 都落在 [1, 2^31-1]；扫 [0,2^32) 的上半段是纯浪费。hi=4294967296 可扩到全 32 位空间。
        super().__init__(procs=int(procs), hi=int(hi), scan_min=int(scan_min), step_trans=int(step_trans),
                         lock_trans=int(lock_trans), stabilization=int(stabilization), prior=int(prior),
                         rescan_above=int(rescan_above), forced_play=int(forced_play), **kw)
        self.procs, self.hi, self.scan_min = int(procs), int(hi), int(scan_min)
        self.step_trans, self.lock_trans = int(step_trans), int(lock_trans)
        self.stabilization, self.use_prior = int(stabilization), bool(int(prior))
        self.rescan_above = int(rescan_above)
        # forced_play=1（缺省）：硬规矩「有可出牌绝不 end」（真机 bot 防 OCR 盲打的历史约束）。
        # forced_play=0：托管评测 obs 完美，允许 GNRPA 为蓄体力主动 end，不丢在手路线。
        self.forced_play = bool(int(forced_play))
        self.report, self.games, self.g = bool(int(report)), 0, None
        self.master = self.ns = self.prior_obj = self.kernel_exe = None
        self.fastcut = None
        self.pool = None
        self.mirror = None
        self._load_err = None
        if self.report:
            atexit.register(self._report)

    def describe(self):
        d = super().describe()
        d["params"] = {"procs": self.procs, "hi": self.hi, "scan_min": self.scan_min,
                       "step_trans": self.step_trans, "lock_trans": self.lock_trans,
                       "stabilization": self.stabilization, "prior": int(self.use_prior),
                       "forced_play": int(self.forced_play)}
        return d

    # -- 加载（每进程一次；托管 evaluate 每线程一个实例，共享 master/内核，搜索各用各的 core 副本）
    def _load(self):
        if self.master is not None or self._load_err is not None:
            return
        try:
            root = _configure_engine_paths()
            if root is None:
                raise RuntimeError(f"GKMS_ROOT 下没有 GakumasCLI（默认 {_GKMS_DEFAULT}）")
            for p in (str(root), str(root / "GKMSUINet")):
                if p not in sys.path:
                    sys.path.insert(0, p)
            try:
                from gkbench import engine as ge
                ge.setup()
            except Exception:                          # noqa: BLE001 -- 直接加载，不依赖 gkbench.engine
                os.chdir(root / "GakumasCLI")
            from GakumasCLI.scenario.exam_session import Master
            from GakumasCLI.native import native_session as NS
            from GakumasCLI.native.native_search import NativeSearch
            try:                                       # 共享缓存的 master（跨线程实例同一份，refmap 缓存才命中）
                from gkbench import engine as ge
                self.master = ge.master()
            except Exception:                          # noqa: BLE001
                self.master = Master.load(root / "GakumasCLI" / "ro" / "master" / "tables")
            nat = NS._lib()                            # vendor DLL（GKMS_NATIVE_LIB）
            self.ns = NativeSearch(nat)
            if self.use_prior:
                from GakumasCLI.scenario import policy_search as PS
                prior_path = root / "GakumasCLI" / "priors" / "prior_generated_only.json"
                self.prior_obj = PS.load_prior(prior_path) if prior_path.is_file() else None
            self.kernel_exe = kernel()
            if self.kernel_exe is None:
                raise RuntimeError("没有 seed_scan 内核且编不出来（gcc/clang）")
            self.pool = RoutePool(self.ns, prior=self.prior_obj, stabilization=self.stabilization)
        except Exception as e:                         # noqa: BLE001
            self._load_err = f"{type(e).__name__}: {e}"

    def _report(self):
        g, self.g = self.g, None
        if g is None or not self.report or not g.actions:
            return
        c = g.counts
        head = f"not locked ({g.state})" if g.lock_turn is None else \
            f"locked turn {g.lock_turn}" + (f", lost turn {g.lost_turn}" if g.state == "lost" else "")
        scan = "" if g.scan_s is None else f"; scan {g.scan_s}s, rescans {g.rescans}"
        steps = ", ".join(f"{k} {c[k]}" for k in ("pool", "base", "forced", "forced_play") if c.get(k))
        pool = "" if self.pool is None else f"; target {self.pool.target}, adopted {self.pool.stats['adopted']}"
        why = f"; {g.why}" if g.why else ""
        print(f"[seedlock] game {self.games}: {head}{scan}{pool}; steps: {steps}{why}", file=sys.stderr, flush=True)

    # -- 一局
    def begin(self, ctx):
        self._load()
        self._report()
        self.games += 1
        g = self.g = _Game()
        self.mirror = None
        if self.pool is not None:
            self.pool.reset()
        if self._load_err is not None:
            g.state, g.why = "failed", self._load_err
            return
        lo = {k: v for k, v in dict(ctx.loadout).items() if not k.startswith("_") and k != "source"}
        self.lo = lo
        try:
            self.fastcut = FastCut(self.master, lo)
            pre = [c["produce_card_id"] for c in self.fastcut.loading.deck.deck]
            dk = self.fastcut.loading.deck
            if dk.audition_parameter_values is not None:
                k = max(0, int(dk.audition_limit_turn) - 3) + int(dk.audition_npc_rng_advances or 0)
            else:
                k = int(dk.segment_start_rng_advances or 0)
            self.pre, self.k = pre, k
            hands = []
            for s in (11, 0x9E3779B9, 123456789, 987654321, 55555, 4242424242):
                sess = self.fastcut.open(s)
                hands.append(_hand_ids(sess))
            inv = Counter(hands[0])
            for h in hands[1:]:
                inv &= Counter(h)
            self.tracker = Draws(pre, inv)
            self.pool_attr, self.mutable = self._turn_pool(dk)
            # 课程局（无回合属性池）：扫描无属性早拒、慢一个量级，且局短——3 张抽牌就起扫，步内多等
            self.scan_min_eff = 3 if self.pool_attr is None else self.scan_min
        except Exception as e:                         # noqa: BLE001 -- 贪心兜底打完整局
            g.state, g.why = "failed", f"{type(e).__name__}: {e}"

    @staticmethod
    def _turn_pool(dk):
        values = dk.audition_parameter_values
        if values is None:
            return None, 0
        from GakumasCLI.engine.card_data import _f32 as f32
        limit = int(dk.audition_limit_turn)
        (t0, p0), (t1, p1), (t2, p2) = sorted(values.items(), key=lambda item: -item[1])
        mutable = limit - 3
        if mutable <= 0:
            return None, 0
        c0 = math.ceil(f32(f32(f32(mutable) * f32(p0)) / f32(p0 + p1 + p2)))
        remaining = mutable - c0
        c1 = round(f32(f32(f32(remaining) * f32(p1)) / f32(p1 + p2)))
        return [t0] * c0 + [t1] * c1 + [t2] * (remaining - c1), mutable

    # -- 种子搜索
    def _start_scan(self, obs):
        g, tr = self.g, self.tracker
        if g.scan is not None:
            g.scan.stop()
        turns = [int(t) for t in obs["exam"]["types"][:self.mutable]] if self.pool_attr else None
        g.scan = Scan(self.kernel_exe, self.k, self.pre, list(tr.seen), list(tr.skip.elements()),
                      self.pool_attr, turns, procs=self.procs, hi=self.hi)
        g.scan_draws, g.state = len(tr.seen), "scanning"
        g.cands, g.cut_pos, g.kept = None, 0, []

    def _try_lock(self, seed, obs, t0, budget):
        g = self.g
        try:
            s = self.fastcut.open(seed)
            for a in g.actions:
                s.step(tuple(a), observe=False)
            if _mirror_key(s) != _obs_key(obs):
                return False
        except Exception:                              # noqa: BLE001
            return False
        self.mirror = s
        g.state, g.lock_turn = "locked", int(obs["exam"]["turn"])
        g.cands = None
        left = t0 + 0.85 * budget - time.perf_counter()
        if left > 0.15:
            self.pool.search_offer(s, self.lock_trans, left)
        return True

    def _progress(self, obs, t0, budget, meta):
        g, tr = self.g, self.tracker
        if g.state == "none":
            turn = int(obs["exam"]["turn"])
            # 默认攒到 6 张抽牌（第 2 回合）再扫：一次扫描候选就降到几十，避免 3 张起扫的几万候选重扫。
            # 牌堆顺序已不可读或第 3 回合还没攒够：有多少扫多少。课程局 3 张起扫（scan_min_eff）。
            if len(tr.seen) >= self.scan_min_eff or (len(tr.seen) >= 3 and (not tr.open or turn >= 3)):
                self._start_scan(obs)
            elif not tr.open:
                g.state, g.why = "failed", "pile changed before enough draws"
            return
        if g.state == "scanning":
            wait_frac = 0.85 if self.pool_attr is None else 0.7
            wait_until = t0 + wait_frac * budget       # 步内等扫描（兜底出牌前），跨步接着等
            seeds = g.scan.poll()
            while seeds is None and time.perf_counter() < wait_until:
                time.sleep(0.02)
                seeds = g.scan.poll()
            if seeds is None:
                return
            g.scan_s, g.cands, g.state = round(g.scan.seconds, 2), seeds, "candidates"
            g.scan = None
            g.cut_pos, g.kept = 0, []
            if not seeds:
                g.state, g.why = "failed", "no seed reproduces the draws"
            return
        if g.state != "candidates" or g.cands is None:
            return
        # 抽牌增加了且候选还多：用更长的抽牌序重扫（比快筛几万候选便宜）
        if tr.open and len(tr.seen) >= g.scan_draws + 3 and len(g.cands) > self.rescan_above:
            g.rescans += 1
            self._start_scan(obs)
            return
        deadline = t0 + 0.6 * budget
        hands = g.hands + [[c["id"] for c in obs["hand"]]]
        i = g.cut_pos
        while i < len(g.cands) and time.perf_counter() < deadline:
            if self.fastcut.follows(g.cands[i], g.actions, hands):
                g.kept.append(g.cands[i])
            i += 1
        g.cut_pos = i
        if i < len(g.cands):
            return                                     # 这一步没筛完，下一步接着筛
        g.cands, g.kept, g.cut_pos = g.kept, [], 0
        if len(g.cands) == 1:
            if not self._try_lock(g.cands[0], obs, t0, budget):
                g.state, g.why = "failed", "the last candidate does not rebuild to the screen"
        elif not g.cands:
            g.state, g.why = "failed", "no seed reproduces the hands"
        elif len(g.cands) <= 8:
            # 少量候选（课程局重牌多，抽牌序不足以区分）：逐个整屏核对，观测等价者锁定
            for s in g.cands:
                if self._try_lock(s, obs, t0, budget):
                    break
        # 多个候选：等更多抽牌（下一步继续筛/重扫）

    # -- 兜底贪心（引擎卡表即时分，同 exam_session.greedy_policy 口径）
    def _card_row(self, cid, upg):
        row = self.master.cards.get((cid, upg))
        if row is None:
            tiers = [u for (k, u) in self.master.cards if k == cid and u <= upg]
            row = self.master.cards.get((cid, max(tiers))) if tiers else {}
        return row or {}

    def _play_value(self, card):
        row = self._card_row(card["id"], int(card.get("u") or 0))
        value = 0
        for link in row.get("playEffects") or ():
            effect = self.master.effects.get(link.get("produceExamEffectId")) if isinstance(link, dict) else None
            t = (effect or {}).get("effectType")
            t = t.get("number") if isinstance(t, dict) else t
            if t in (1, 56, 23):
                value += int((effect or {}).get("effectValue1") or 0)
            elif t == 49:
                value += 2 * int((effect or {}).get("effectValue1") or 0)
        return value

    def _best_play(self, obs, legal):
        best, best_value = None, -1
        for a in legal:
            if a[0] != "play":
                continue
            card = obs["hand"][a[1]]
            v = self._play_value(card)
            if v > best_value:
                best, best_value = a, v
        return best

    def _fallback(self, obs, legal):
        if self.master is not None:
            a = self._best_play(obs, legal)
            if a is not None:
                return a
        for a in legal:                                # 没有可出牌才 end（硬规矩）
            if a[0] != "end":
                return a
        return legal[0] if legal else ("end",)

    # -- 决策
    def decide(self, ctx):
        t0 = time.perf_counter()
        budget = float(ctx.budget or 5.0)
        obs = ctx.obs
        legal = [tuple(a) for a in obs["legal"]]
        g = self.g
        meta = {}
        if g is None:                                  # begin 没跑过（防御）
            self.begin(ctx)
            g = self.g
        if g.state not in ("failed", "lost"):
            try:
                if g.state != "locked":
                    self.tracker.update(obs)
                    self._progress(obs, t0, budget, meta)
                elif self.mirror.finished or _mirror_key(self.mirror) != _obs_key(obs):
                    g.lost_turn = int(obs["exam"]["turn"])
                    g.state = "lost"
                    g.why = ("the battle is over" if self.mirror.finished
                             else f"screen differs at turn {g.lost_turn}")
            except Exception as e:                     # noqa: BLE001
                g.state, g.why = "failed", f"{type(e).__name__}: {e}"
        action, mode = None, "base"
        if len(legal) == 1:
            action, mode = legal[0], "forced"
        elif g.state == "locked":
            try:
                left = t0 + 0.85 * budget - time.perf_counter()
                if left > 0.12:
                    self.pool.search_offer(self.mirror, self.step_trans, left)
                a = self.pool.take()
                if a is not None and (a[0] == "select" or a in legal):
                    action, mode = a, "pool"
                    meta["target"] = self.pool.target
                elif a is not None:
                    self.pool.played(a)                # 路线首动作不合法：丢弃
                    meta["route_illegal"] = list(a)
            except Exception as e:                     # noqa: BLE001
                meta["error"] = f"pool {type(e).__name__}: {e}"
        if action is None:
            action, mode = self._fallback(obs, legal), "base"
        if self.forced_play and action[0] == "end" and any(a[0] == "play" for a in legal):
            action, mode = self._best_play(obs, legal), "forced_play"   # 硬规矩（forced_play=1 缺省）：有可出牌绝不 end
            meta["hard_rule"] = True
            if g.state == "locked":
                self.pool.played(action)
        elif g.state == "locked" and mode != "pool":
            self.pool.played(action)
        g.actions.append(action)
        g.hands.append([c["id"] for c in obs["hand"]])
        if g.state == "locked":
            try:
                self.mirror.step(tuple(action), observe=False)
            except Exception as e:                     # noqa: BLE001
                g.state, g.why = "lost", f"mirror step {type(e).__name__}: {e}"
        meta.update(mode=mode, seed=g.state)
        g.counts[mode] = g.counts.get(mode, 0) + 1
        if g.lock_turn is not None:
            meta["lock_turn"] = g.lock_turn
        if g.scan_s is not None:
            meta["scan_s"], meta["scan_draws"], meta["rescans"] = g.scan_s, g.scan_draws, g.rescans
        if g.state == "candidates":
            meta["candidates"] = len(g.cands or ())
        if g.state == "locked":
            meta["adopted"] = self.pool.stats["adopted"]
        if g.why:
            meta["why"] = g.why
        return Decision(tuple(action), meta)