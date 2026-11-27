# gkagent-ex-seed-v5 — v4 + **预算饱和的多波次并行 RoutePool**（把空转墙钟换成更多独立起点/搜索配置）。
# Copyright (C) 2026 gkagent contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# v5（在 v4 基础上改**搜索调度/搜索质量**，其余机制全保留；v2/v3/v3g/v4 原版零改动）：
#   问题（v4 托管 240 局逐步记录实测，data/_v5_lockscan.py）：每步 10s 预算只用了 2.3–4.3s ——
#   GNRPA 的 transitions 帽（500k/起点）~0.5s 先到，剩余墙钟空转；「深度」杠杆在 v4 已证伪
#   （500k→1M→2M 同分），有效的是**独立起点/不同搜索配置**。v5 改动：
#     ① **多波次填满预算（waves=0）**：一波 starts 个起点跑完后，只要 t_end 前还有时间就再发一波
#        （新 sd：+104729×wave）。RoutePool 只采纳更高终局分 → 机制上单调安全。
#        **wave 0 与原 v4 逐位同口径**（6 起点 × base 配置 2/8/3），额外波次才是新增搜索。
#     ② **并行起点（pool_threads）**：一波内每个起点在**独立 core 副本**上并行搜（native session
#        search_tables() 本就给每个会话一份自己的 core；ctypes 调用释放 GIL），同等墙钟起点数 ×W。
#        决赛（limit_turn>=12）W=4、其余 W=2。
#     ③ **搜索配置组合（portfolio）**：额外波次逐起点轮换 GNRPA 的 (levels,iterations,stabilization)
#        —— 同一状态下不同配置找到的局部最优**不同**（out/_v5_engine_grid.json：同一状态 s5 在
#        5KZSXANK +31%、i16 在 AXME8QK2 +26%，但没有一组全胜）→ 组合取 max 单调安全。
#     ④ 精确尾不动：剩 ≤tail_turns 回合时整段剩余时间跑 core_tail（node_cap 20M，complete 即证最优）。
#   v4 逐位复现：waves=1 + pool_threads=1 + 空 portfolio + root_scan=0（配置池 v4ref 门里验证）。
#   **负结果如实记录**（都已探针验证、默认关，仅作为门里的对照臂）：
#     · root_scan（根动作枚举，每合法首动作先走一步再完整续搜）：离线 2 局 −9%/−1%、托管 5 槽中性；
#     · mirror_vote（锁定前用候选镜像后验投票代替 ctx.worlds 随机世界）：机制在实测里几乎不触发
#       （候选管线很快就锁定），托管 5 槽 2 胜 3 负、CI 跨 0 → 关；
#     · 固定搜索配置 i16/s5：同状态 +10–25%，但整局 A/B 中性（−0.8%/+0.07%）→ 只进组合臂不进缺省；
#     · 并行+填满但无 portfolio：离线 2 局中性。
#   门与探针（都不提交）：data/_v5_restart_curve.py / _v5_engine_probe.py / _v5_engine_grid.py /
#   _v5_pair.py / _v5_lockscan.py / _v5_compare.py；托管驱动 data/_v4_hosted.py。
#
# v4（在 v3g 基础上加杠杆⑤，其余机制全保留）：
#   背景：v3 托管 240 局均分 1,322,681（seed 行第一 / best-known 1,486,205 的 89.0%）。逐槽缺口
#   28.8M，**AUDITION_FINAL 占 77.7%**（108 槽 207.8M 分 vs MID1 98.9M）——分数尺度决定杠杆价值。
#   离线证伪「深度」：AS-5KZSXANK step_trans 500k→1M→2M 分数**逐位相同**（8,631,520），墙钟 1.72×/2.82×
#   → transitions 帽不是瓶颈，10s 预算有 5-8× 余量（data/_v4_pair_b1.json）。
#   杠杆⑤ **规模自适应起点 starts_hi**（data/_v4_pair_s8a.json / _s6a.json，同题同 seed 配对、bootstrap）：
#     · starts 4→8/6 在 **12 回合决赛**（limit_turn=12）多摸盆地：AS-5KZSXANK **+1,496,003**（8.63M→10.13M，
#       starts6 已达同分）、AS-QV6QCSN9 **+280,434**、AS-P8ZJTXNA 0；
#     · 在 **9 回合中期** 反而**深度稀释**：AS-3G6FFZZT −210,772（s8）/ −224,133（s6）、VH8WYE6J 0
#       → 所以按考试规模**分档**：12 回合题 starts_hi=6，其余 starts=4（`starts_hi=0` 关闭=逐位同 v3g）。
#   其余承 v3g：**失锁重扫**（rescan_open=1，M1 消费图 graph-clean 门 + 首 obs 开局可靠抽牌重扫）/
#   starts4（非决赛）/ lock2M / done / forced_play0 / prior0 / RoutePool / core_tail 全保留。
#   v4 缺省 **vote_sec_cap=0.8**（与托管 1,322,681 那次逐位同口径；vote2.0 的晚锁上行留 v5 单变量验证）。
#
# v3g（在 v3 基础上接 M1 阶段2 消费图 / predictive 牌区，攻真失锁怪物题）：
#   根因（data/_m1b_monster_diag.json 实证）：B38CARVV/VWAF2GDN/HTNFZWKG/5KZSXANK 等牌堆被效果改动
#   （create/move/reshuffle）后 Draws.open=False，冻结的 seen/skip 被 deck-modify 污染 → seed_scan 内核
#   排除真种子（frozen_match=False）→ "no seed reproduces the screen" 整局 worlds 兜底。
#   杠杆④（v3 未实现，v3g 实现）：**失锁重扫**——首 obs（turn1 开局抽牌，任何 deck-modify 之前）的
#   opening_seen/opening_skip 是可靠的（diag：4 怪物 opening_match 全 True）；主扫描失锁时改用开局可靠
#   抽牌重扫种子候选，FastCut 手牌回放（真引擎=完美 predictive 牌区）+ 整屏核对仍防假锁。
#   **消费图 opt-in 门**（vendor/m1_graph.py，clean-room 自写，口径=src exam_risk.known_info_ok(use_graph=True)）：
#   只对 graph-clean 牌组（无未刻画消费点 type21/ExamReviewPerSearchCount）启用重扫；机制题（create/move/panic
#   已刻画）走消费图恢复 known_draw。type21 随机池消费未刻画（data/_m1b_type21_p1：cons≈132-136/create-to-hand）
#   → 保守不重扫。重扫参数化 rescan_open（缺省 1）；=0 复现 v3 行为。
#
# v3（在 v2 榜首 1,267,591 / best-known 87.3% 基础上推前沿，目标 1.3M+ / 90%+）：
#   缺口分析（data/_v3_loss_analysis.md）：v2 输 seedlock 的 4 局全是怪物题（合计 −9.5M）=
#   高方差题搜索盆地方差（离线 dev 种子 v2 赢，托管保密种子反输）。v3 杠杆（按收益）：
#   ① 更多起点 / 更深锁定步：starts 2→4、lock_trans 1M→2M —— 多探索盆地，普适压 ex-seed 50 负局。
#   ② 扫描等待窗去墙钟化（sl3b「锁定等待悬崖」）：scan_wait_mode="done" 等扫描进程真正完成
#      （poll 非 None），上限 scan_wait_cap×budget，cut/mirror 管线 deadline=lock_pipe×budget；
#      不再用 0.7×budget 墙钟截断 → CPU 竞争下扫描时长抖动不再翻锁定回合。="wall" 恢复 v2 行为。
#   ③ 锁定前 worlds 搜索加深：vote_sec_cap 0.8→2.0 —— 晚锁题（lock turn 5-6）锁定前多回合走 worlds
#      投票，v2 每世界 0.8s 只用一小半预算→早期丢回合；2.0s 深搜修复（diag1 QV6QCSN9 +324k）。
#   ④ deck-modify 失锁重扫：**v3g 实现**（rescan_open=1）——首 obs 开局可靠抽牌重扫种子候选 +
#      消费图 graph-clean opt-in 门（vendor/m1_graph）；FastCut 手牌回放 + 整屏核对防假锁（见上）。
#   全部新杠杆参数化，缺省=v3 离线门赢的配置（starts4/lock2M/done/vote2.0）；
#   starts=2/lock_trans=1M/scan_wait_mode=wall/vote_sec_cap=0.8 可复现 v2。
#
# 融合（用户指定架构，承自 v2）：
#   基础 = gkagent-ex-seed（954,652）：公开 obs 自反推牌序种子（seed_scan 内核 + Draws 抽牌追踪 +
#   FastCut 引擎快筛 ~0.4ms/种子 + 整屏核对锁定），锁定前候选世界投票 / ctx.worlds 兜底，
#   末段（剩 ≤2 回合）core_tail 精确尾搜索 —— 全部保留。
#   融入 gkagent-seedlock（944,850）的 RoutePool：锁定后**每步**重搜（transitions 预算），
#   路线在副本上正规回放核分（session.step(action, observe=False)），终局分更高者替换在手路线，
#   跨步保留最优 —— 在手路线分数已保住，后续短搜不会让终局分下降（ex-seed 原版是每回合单路线
#   单调改进，这是融合核心）。多起点：同一搜索机会用不同 sd seed 跑 starts 条 GNRPA 取最优。
#   预算：step_seconds 5→10，step_trans 500k/步 × starts（v2=2 / v3 缺省 4），锁定步 lock_trans（v2=1M / v3 缺省 2M）。prior=0。
#
# 种子不是裁判给的：类属性 sees_seed=False（托管门禁），不读 ctx.seed / ctx.true_session，
# 只用 ctx.obs + ctx.loadout；about.sees="seed" 如实声明看牌序（UIHorizon / ex-seed 托管先例）。
#
# forced_play 硬规矩参数化（缺省 0：托管 obs 完美，允许 GNRPA 为蓄体力主动 end、不丢在手路线。
# 顺序律「先关硬规矩再加预算」：f2-sl3b 池化 n=32 fp0 +28,493 CI>0；本投稿 core8 门 fp0 对 fp1
# 零负例，AS-ADDTACFE +2.66M / AS-8MY3XH4R +147k（fp1 触发硬规矩丢路线 = 崩局源）。
# forced_play=1 恢复 ex-seed 行为：有可出牌绝不 end，搜索选 end 时逐 play 补搜（真机防 OCR 历史约束）。
#
# 引擎：GKMS_ROOT（缺省 <repo>/data/GKMSMainWheel，AGPL）按路径外部引用；原生核心优先 vendor/
# gkmscore.dll（与本机编通的是同一份，不重编）。模块导入时自配置路径常量（evaluate() 先 import
# engine 后 make 算法，env 来不及设）。引擎代码不拷进本文件 / src/gkagent。
from __future__ import annotations

import atexit
import os
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
_DATA = HERE.parents[2]                                  # submissions/gkagent-ex-seed-v3 → submissions → bench_repo → data
_GKMS_DEFAULT = _DATA / "GKMSMainWheel"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


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
    os.environ["UINET_NATIVE_LIB"] = str(dll)
    eng = sys.modules.get("gkbench.engine")
    if eng is not None:
        eng.GKMS_ROOT = root
        eng.NATIVE_LIB = dll
        eng.MASTER_DIR = root / "GakumasCLI" / "ro" / "master" / "tables"
    return root


_ENGINE_ROOT = _configure_engine_paths()

from gkbench.algos.base import Algorithm, Decision  # noqa: E402

OPENING_SEEDS = (11, 0x9E3779B9, 123456789, 987654321, 55555, 4242424242)
# fastcut 会临时替换引擎模块级函数（_Round / _pack_unopened / master_refmap）：
# 托管评测多局并行（线程）时串行化，避免跨局串状态。搜索本身各用各的 core 副本
# （native session 的 search_tables()），不需要这把锁。
_ENGINE_LOCK = threading.RLock()
_TAIL_CALIBRATED = [False]


def _ids(cards):
    return [c["produce_card_id"] for c in cards]


def _v1(mine, obs):
    from uinet.uiobs import v1_view
    if mine.get("v") != "uiobs.v1":
        mine = v1_view(mine)
    cut = lambda o: dict(o, status=[r[:2] if isinstance(r, (list, tuple)) else r for r in o.get("status") or ()])  # noqa: E731
    return cut(mine), cut(obs)


def _same(mine, obs):
    if obs.get("v") == "uiobs.v1":
        mine, obs = _v1(mine, obs)
    return mine == obs


def _differs(mine, obs, limit=6):
    if obs.get("v") == "uiobs.v1":
        mine, obs = _v1(mine, obs)
    out = []
    for k in sorted(set(mine) | set(obs)):
        a, b = mine.get(k, "<absent>"), obs.get(k, "<absent>")
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            out += [f"{k}.{j}" for j in sorted(set(a) | set(b)) if a.get(j, "<absent>") != b.get(j, "<absent>")]
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            idx = next((j for j in range(len(a)) if a[j] != b[j]), "?")
            out.append(f"{k}[{idx}]")
        else:
            out.append(k if not isinstance(a, list) or not isinstance(b, list) else f"{k} (length {len(a)} / {len(b)})")
    return ", ".join(out[:limit]) + (" ..." if len(out) > limit else "")


def _first_legal(path, legal):
    for a in path or ():
        if tuple(a) in legal:
            return tuple(a)
    return None


def _replay_score(session, route):
    """路线在副本上正规回放到终局的分数（session.step(action, observe=False)，solver.replay_session 同口径）；
    走不完返回 None。gk_play 直调不刷新手牌可出性缓存，不能用。"""
    c = session.clone()
    try:
        for a in route:
            if c.finished:
                break
            c.step(tuple(a), observe=False)
    except Exception:                                  # noqa: BLE001 -- 不是这场对局的路线
        return None
    return int(c.state.score) if c.finished else None


class RoutePool:
    """锁定后整局是确定性问题：每步多条 GNRPA 起点各出一条完整路线，回放核分，
    终局分更高者替换在手路线，跨步累积取最优（参考 seedlock RoutePool / UIHorizon pool.py）。
    在手路线的分数已保住：后续短搜不会让终局分下降。tail 证完最优后 proven=True 不再搜。"""

    def __init__(self, ns, prior=None, stabilization=3, seed=182, levels=2, iterations=8):
        self.ns, self.prior = ns, prior
        self.stabilization, self.seed = int(stabilization), int(seed)
        self.levels, self.iterations = int(levels), int(iterations)
        self.route, self.target, self.n = [], -1, 0
        self.proven = False
        self.stats = {"searches": 0, "adopted": 0, "bad_routes": 0, "transitions": 0, "tails": 0}

    def reset(self):
        self.route, self.target, self.n = [], -1, 0
        self.proven = False
        self.stats = {"searches": 0, "adopted": 0, "bad_routes": 0, "transitions": 0, "tails": 0}

    def offer(self, session, route, source="search", proven=False):
        """回放核分后尝试采纳；返回回放分（走不完 None）。"""
        if not route:
            return None
        score = _replay_score(session, route)
        if score is None:
            self.stats["bad_routes"] += 1
            return None
        if score > self.target:
            self.route, self.target = [tuple(a) for a in route], score
            self.stats["adopted"] += 1
            self.proven = bool(proven) and source == "tail"
        elif source == "tail" and proven and score == self.target:
            self.proven = True                     # 在手路线已达精确最优
        return score

    def search_offer(self, session, transitions, seconds, sd, cfg=None):
        """一个起点：GNRPA 搜一条路线并尝试采纳。返回 stats（核心拒绝 None）。
        cfg=(levels, iterations, stabilization) 覆盖池缺省（v5 搜索配置组合用）。"""
        lv, it, stb = cfg if cfg else (self.levels, self.iterations, self.stabilization)
        try:
            self.ns._cache = None                  # 强制重导入当前状态（teacher.py 同口径）
            path, st = self.ns.policy_search(session, transitions=int(transitions), deadline=float(seconds),
                                             seed=int(sd), variant="gnrpa",
                                             levels=int(lv), iterations=int(it),
                                             stabilization=int(stb), prior=self.prior)
        except Exception:                          # noqa: BLE001 -- 核心拒绝的状态：没有提案
            return None
        self.stats["searches"] += 1
        self.stats["transitions"] += int(st.get("expansions") or 0)
        if int(st.get("status", 0)) != 0 or not path:
            return st
        self.offer(session, path)
        return st

    def offer_stats(self, session, path, st):
        """采纳一条**已并行搜完**的路线（v5 并行起点用）：统计进池 + 回放核分，只采纳更高终局分。"""
        if st is not None:
            self.stats["searches"] += 1
            self.stats["transitions"] += int(st.get("expansions") or 0)
        if path and int((st or {}).get("status", 0)) == 0:
            self.offer(session, path)

    def take(self):
        if not self.route:
            return None
        action, self.route = self.route[0], self.route[1:]
        self.n += 1
        return tuple(action)

    def played(self, action):
        """实际打出的不是池给的动作（强制/兜底）：路线首动作一致则续，否则丢弃（分数不再保住）。"""
        if self.route and tuple(self.route[0]) == tuple(action):
            self.route = self.route[1:]
        else:
            self.route, self.target, self.proven = [], -1, False
        self.n += 1


class ExSeedV5Algo(Algorithm):
    name = "gkagent-ex-seed-v5"
    title = "gkagent-ex-seed-v5（v4 + 预算饱和并行多起点 RoutePool）"
    needs_gkms = True
    sees_seed = False                              # 托管门禁；种子从公开 obs 自反推，about.sees="seed" 如实声明
    about = {
        "summary": "从画面信息（回合属性、抽到的牌）和公开编成反推牌序种子；锁定后整局确定，"
                   "GKMS 官方引擎多起点 GNRPA 路线池每步重搜、回放核分跨步累积取最优，"
                   "末段 core_tail 精确尾搜索证最优，照着最优路线打。v5 把每步没用完的墙钟换成"
                   "**同深度的更多独立起点**（多波次 + 并行 core 副本），按规模分档（12 回合决赛 4 线程）。",
        "detail": [
            "只读 ctx.obs 和 ctx.loadout，不拿裁判的种子（sees_seed=False）；种子由 seed_scan 从 [0,2^32) 反推",
            "FastCut 引擎快筛候选（复用 loading + refmap 缓存）；通常第 1–3 回合锁定；锁定前候选世界投票兜底",
            "锁定后 RoutePool：每步每起点一条完整路线、回放核分只采纳更高终局分（机制单调），跨步累积",
            "v5 搜索调度：不再「跑完 starts 个起点就停」——t_end 前持续发新波次（同 500k transitions 深度、"
            "新 sd）；决赛（limit_turn>=12）一波内 4 个独立 core 副本并行，同等墙钟起点数 ×4（中期保持串行，深度主导）",
            "扫描等待去墙钟化（scan_wait_mode=done）：等扫描进程真正完成而非 0.7×budget 墙钟截断，减锁定回合抖动",
            "剩 ≤2 回合换 core_tail 精确尾搜索（多线程 + 置换表），证完最优后不再搜",
            "forced_play 硬规矩参数化（缺省关：托管 obs 完美，允许蓄体力主动 end；=1 恢复 ex-seed 有可出牌绝不 end）；异常 meta.error/why 如实记录",
            "成绩应与看牌序的算法（UIHorizon/官方AI）对照，和不知道牌序的算法不是同一类",
        ],
        "sees": "seed",
        "family": "gkagent-ex-seed", "family_name": "gkagent-ex-seed",
    }

    def __init__(self, scan_min=6, procs=16, hi=1 << 31, tail_turns=2, max_mirrors=48,
                 vote_worlds=4, search_use=0.70, use_prior=0,
                 step_trans=500000, lock_trans=2000000, starts=4, stabilization=3,
                 levels=2, iterations=8,
                 starts_hi=6, starts_hi_turn=12,
                 waves=2, waves_hi=0, waves_hi_turn=12,
                 pool_threads=4, pool_threads_hi=4, pool_threads_hi_turn=12,
                 root_scan=0, root_scan_max=8,
                 portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8",
                 portfolio_first=1,
                 deep_trans=0, deep_waves=0,
                 search_deadline_cap=4.0, min_search_sec=0.12, tail_threads=4,
                 forced_play=0, scan_wait_mode="done", scan_wait_cap=0.95, lock_pipe=1.05,
                 vote_sec_cap=0.8, vote_sec_cap_hi=0.0, vote_sec_cap_hi_turn=12,
                 mirror_vote=0,
                 rescan_open=1, report=1, **kw):
        # hi 默认 2^31：固定种子 randrange(1,2^31-1)，模板种子 likewise；扫空自动补扫 [2^31, 2^32)。
        # step_trans/lock_trans：每步/锁定步每个起点的 transitions 预算；starts：每步 GNRPA 起点数。
        # v3 缺省 starts=4 / lock_trans=2M（v2 为 2 / 1M）：高方差怪物题多探索盆地（缺口分析杠杆①）。
        # scan_wait_mode："done"（v3 缺省）等扫描进程真正完成（poll 非 None），上限 scan_wait_cap×budget，
        #   cut/mirror 管线 deadline=lock_pipe×budget —— 去墙钟化，减 sl3b 锁定等待悬崖；
        #   "wall" 恢复 v2：wait_until=0.7×budget、deadline=0.75×budget 墙钟截断。
        # forced_play=0（缺省）：允许 GNRPA 蓄体力主动 end（sl3b 池化 A/B + 本投稿 core8 门过采纳门）；
        # 1 = ex-seed 硬规矩「有可出牌绝不 end」（真机防 OCR 的历史约束，托管 obs 完美不适用）。
        super().__init__(scan_min=int(scan_min), procs=int(procs), hi=int(hi), tail_turns=int(tail_turns),
                         max_mirrors=int(max_mirrors), vote_worlds=int(vote_worlds), search_use=float(search_use),
                         use_prior=int(use_prior), step_trans=int(step_trans), lock_trans=int(lock_trans),
                         starts=int(starts), stabilization=int(stabilization), forced_play=int(forced_play),
                         scan_wait_mode=str(scan_wait_mode), scan_wait_cap=float(scan_wait_cap),
                         lock_pipe=float(lock_pipe), vote_sec_cap=float(vote_sec_cap),
                         rescan_open=int(rescan_open), **kw)
        self.scan_min, self.procs, self.hi = int(scan_min), max(1, int(procs)), int(hi)
        self.tail_turns, self.max_mirrors = int(tail_turns), int(max_mirrors)
        self.vote_worlds, self.search_use = int(vote_worlds), float(search_use)
        # use_prior=0 默认：旧规则版 prior 在 rules=69 引擎上实测更差（ex-seed / seedlock 同结论）。
        self.use_prior = bool(int(use_prior))
        self.step_trans, self.lock_trans = max(1000, int(step_trans)), max(1000, int(lock_trans))
        self.starts, self.stabilization = max(1, int(starts)), max(1, int(stabilization))
        # GNRPA 嵌套参数（v5 搜索质量杠杆）：默认 l2/i8/s3 是引擎缺省；同 transitions 预算下
        # l4/i16/s5 在固定状态上能多找 10–25% 终局分（out/_v5_engine_grid.json），成本几乎不变
        # （transitions 帽先到，嵌套层级只改变 rollout 的组织方式）→ 参数化，缺省仍 = v4 口径。
        self.levels = max(1, min(5, int(levels)))
        self.iterations = max(1, int(iterations))
        # 搜索配置组合（v5 搜索质量机制）：GNRPA 的 (levels,iterations,stabilization) 在同一状态下
        # 找的局部最优**不同**（out/_v5_engine_grid.json：同一状态 s5 在 5KZSXANK +31%、i16 在
        # AXME8QK2 +26%，但没有一组全胜）→ 逐波轮换配置 + 不同 sd，RoutePool 取更高终局分 =
        # 组合单调安全（≥ 任一单配置）。空 = 只用 (levels,iterations,stabilization)（= v4 口径）。
        self.portfolio = []
        self.portfolio_first = bool(int(portfolio_first))
        for part in str(portfolio or "").replace(" ", "").split(","):
            if not part:
                continue
            try:
                lv, it, stb = (int(x) for x in part.split("/"))
            except Exception:  # noqa: BLE001
                continue
            self.portfolio.append((max(1, min(5, lv)), max(1, it), max(1, stb)))
        # 规模自适应起点（v4 杠杆①）：12 回合决赛（FINAL）分数尺度大、盆地方差主导 →
        # 每步多起点（starts_hi）；9 回合中期题每起点分到的墙钟少、深度主导 → 保持 starts。
        # 证据（data/_v4_pair_s8a.json / _s6a.json，同题同 seed 配对）：AS-5KZSXANK(12T)
        # starts8 +1,496,003 / QV6QCSN9(12T) +280,434 / P8ZJTXNA(12T) 0；AS-3G6FFZZT(9T)
        # starts8 −210,772 / starts6 −224,133（深度稀释）。starts_hi=0 关闭=逐位同 v3g。
        self.starts_hi = max(self.starts, int(starts_hi or 0))
        self.starts_hi_turn = int(starts_hi_turn)
        # v5 搜索调度：waves=1 且 pool_threads=1 = v4 原串行路径（逐位复现）；waves=0 = 填满 t_end。
        self.waves = max(0, int(waves or 0))
        self.waves_hi = max(0, int(waves_hi or 0))
        self.waves_hi_turn = int(waves_hi_turn)
        self.pool_threads = max(1, int(pool_threads or 1))
        self.pool_threads_hi = max(1, int(pool_threads_hi or 1))
        self.pool_threads_hi_turn = int(pool_threads_hi_turn)
        self.search_deadline_cap = max(0.05, float(search_deadline_cap))
        self.min_search_sec = max(0.02, float(min_search_sec))
        self.tail_threads = max(1, int(tail_threads or 1))
        # 根动作枚举（v5 机制，root_scan=1 开）：restart 曲线实测不同 sd 常收敛到同一条路线 →
        # 随机起点可能整波没覆盖某个根动作。枚举每个合法根动作（先走一步再从后继完整续搜）保证覆盖。
        self.root_scan = bool(int(root_scan))
        self.root_scan_max = max(1, int(root_scan_max or 1))
        # 深浅混合（v5 机制，deep_trans=0 关）：restart 曲线实测有的题 500k 收敛到局部最优、
        # 2M 能再挖一层（3EW6E6HV 5.91M→6.32M）→ 前 deep_waves 波用深预算，其余波 500k 快探索。
        self.deep_trans = max(0, int(deep_trans or 0))
        self.deep_waves = max(0, int(deep_waves or 0))
        self.dbg_errors = []          # 并行 worker 异常留痕（debug=1 时段 meta 里上报）
        self._ex = None
        self.forced_play = bool(int(forced_play))
        self.scan_wait_mode = str(scan_wait_mode).lower()
        self.scan_wait_cap, self.lock_pipe = float(scan_wait_cap), float(lock_pipe)
        # vote_sec_cap：锁定前 worlds/candidates 投票每个世界的 GNRPA 秒数上限（v2=0.8，v3 缺省 2.0）。
        # 晚锁题（如 QV6QCSN9 lock turn6）锁定前多回合走 worlds 投票，0.8×4=3.2s 只用一小半预算→早期丢回合；
        # 2.0×4=8s 深搜修复锁定前打法（diag1 实证 QV6QCSN9 +324k）。失锁题整局 worlds 也受益。
        self.vote_sec_cap = max(0.05, float(vote_sec_cap))
        # 可选（v5 门单独测）：决赛（limit_turn>=vote_sec_cap_hi_turn）锁定前 worlds 投票加深。
        self.vote_sec_cap_hi = max(self.vote_sec_cap, float(vote_sec_cap_hi or 0.0))
        self.vote_sec_cap_hi_turn = int(vote_sec_cap_hi_turn)
        # v5 mirror_vote：锁定前用候选镜像（真后验）投票代替随机 worlds（见 decide）。
        self.mirror_vote = bool(int(mirror_vote))
        # rescan_open=1（v3g 缺省）：deck-modify 失锁时用首 obs 开局可靠抽牌重扫种子候选（杠杆④），
        # 仅对消费图 graph-clean 牌组启用（exam_risk opt-in 口径，vendor/m1_graph）；=0 复现 v3。
        self.rescan_open = bool(int(rescan_open))
        self.report = bool(int(report))
        self.games = 0
        self.g = None
        self.pool = None
        if self.report:
            atexit.register(self._report)

    def describe(self):
        d = super().describe()
        d["params"] = {"scan_min": self.scan_min, "procs": self.procs, "hi": self.hi,
                       "tail_turns": self.tail_turns, "step_trans": self.step_trans,
                       "lock_trans": self.lock_trans, "starts": self.starts,
                       "starts_hi": self.starts_hi, "starts_hi_turn": self.starts_hi_turn,
                       "levels": self.levels, "iterations": self.iterations,
                       "portfolio": ",".join(f"{a}/{b}/{c}" for a, b, c in self.portfolio),
                       "waves": self.waves, "waves_hi": self.waves_hi,
                       "pool_threads": self.pool_threads, "pool_threads_hi": self.pool_threads_hi,
                       "tail_threads": self.tail_threads,
                       "root_scan": int(self.root_scan),
                       "deep_trans": self.deep_trans, "deep_waves": self.deep_waves,
                       "vote_sec_cap_hi": self.vote_sec_cap_hi,
                       "mirror_vote": int(self.mirror_vote),
                       "stabilization": self.stabilization, "forced_play": int(self.forced_play),
                       "search_use": self.search_use, "use_prior": int(self.use_prior),
                       "scan_wait_mode": self.scan_wait_mode, "scan_wait_cap": self.scan_wait_cap,
                       "lock_pipe": self.lock_pipe, "vote_sec_cap": self.vote_sec_cap,
                       "rescan_open": int(self.rescan_open)}
        return d

    # -- 引擎 / 加载 -------------------------------------------------------------
    def _load(self):
        _configure_engine_paths()
        from gkbench import engine
        engine.setup()
        self.engine = engine
        self.master = engine.master()
        self.nat, self.ns = engine.native()
        self.pr = engine.prior() if self.use_prior else None
        import draws
        import fastcut
        import opening
        import seedscan
        import m1_graph
        self.draws_mod, self.fastcut_mod, self.opening_mod, self.seedscan = draws, fastcut, opening, seedscan
        self.m1_graph = m1_graph
        self.kernel = seedscan.kernel()
        if self.pool is None:
            self.pool = RoutePool(self.ns, prior=self.pr, stabilization=self.stabilization,
                                  levels=self.levels, iterations=self.iterations)

    def _report(self):
        g, self.g = self.g, None
        if g is None or not g.actions:
            return
        c = g.counts
        head = f"not locked ({g.state})" if g.lock_turn is None else \
            f"locked turn {g.lock_turn} seed {g.locked_seed}" + (f", lost turn {g.lost_turn}" if g.state == "lost" else "")
        scan = "" if g.scan_s is None else f"; scan {g.scan_s}s, {g.n_cands} cands"
        if getattr(g, "rescan_used", False):
            scan += "; RESCAN(opening)"
        pool = ""
        if self.pool is not None and g.lock_turn is not None:
            st = self.pool.stats
            pool = (f"; pool target {self.pool.target}, adopted {st['adopted']}, bad {st['bad_routes']}, "
                    f"searches {st['searches']}, trans {st['transitions']}, tails {st['tails']}")
        steps = ", ".join(f"{k} {c[k]}" for k in ("route", "search", "tail", "vote", "worlds", "forced", "fallback") if c.get(k))
        why = f"; {g.why}" if g.why else ""
        print(f"[ex-seed-v5] game {self.games}: {head}{scan}{pool}; steps: {steps}{why}", file=sys.stderr, flush=True)

    def begin(self, ctx):
        self._load()
        self._report()
        self.games += 1
        g = self.g = type("G", (), {})()
        g.state, g.why, g.near = "none", None, None
        g.actions, g.hands = [], []
        g.scan, g.cands, g.mirrors, g.mirror = None, None, {}, None
        g.lock_turn, g.locked_seed, g.lost_turn = None, None, None
        g.scan_s, g.n_cands, g.scan_draws = None, None, None
        g.cut_pos, g.cut_pile, g.cut_n, g.cut_s = None, None, 0, 0.0
        g.counts = {}
        g.scan_phase = 0
        g.did_lock_search = False
        g.opening_seen, g.opening_skip = None, None
        g.rescan_done, g.rescan_used = False, False
        g.graph_clean = None
        self.pool.reset()
        self.lo = {k: v for k, v in dict(ctx.loadout).items() if not k.startswith("_") and k != "source"}
        try:
            g.graph_clean = self.m1_graph.known_info_ok_graph(self.lo.get("deck_cards") or [])
        except Exception:  # noqa: BLE001
            g.graph_clean = None
        if g.scan is not None:
            g.scan.stop()
        try:
            with _ENGINE_LOCK:
                opens = [self.opening_mod.opening(self.master, self.lo, s) for s in OPENING_SEEDS]
                if any(o[0] != opens[0][0] or o[1] != opens[0][1] for o in opens):
                    raise RuntimeError("the opening depends on the seed")
                self.pre, self.k = opens[0][0], opens[0][1]
                self.pool_attr, self.mutable = self.opening_mod.turn_pool(opens[0][2])
                inv = self.draws_mod.invariant_hand([_ids(o[2].deck.hand) for o in opens])
                g.tracker = self.draws_mod.Draws(self.pre, inv)
                g.cutter = self.fastcut_mod.FastCut(self.master, self.lo)
            if self.kernel is None:
                raise RuntimeError("no seed_scan kernel")
        except Exception as e:  # noqa: BLE001
            g.state, g.why = "failed", f"{type(e).__name__}: {e}"

    # -- 种子搜索（ex-seed 原样保留） ----------------------------------------------
    def _start_scan(self, obs, g):
        tr = g.tracker
        turns = [int(t) for t in obs["exam"]["types"][:self.mutable]] if self.pool_attr else None
        lo, hi = (0, self.hi) if g.scan_phase == 0 else (self.hi, 1 << 32)
        # 重扫态（含 phase1 补扫）沿用开局可靠抽牌，避免冻结 seen 被 deck-modify 污染。
        if g.rescan_used and g.opening_seen:
            seen, skip = list(g.opening_seen), list(g.opening_skip or ())
        else:
            seen, skip = list(tr.seen), list(tr.skip.elements())
        g.scan = self.seedscan.Scan(self.k, self.pre, seen, skip,
                                    self.pool_attr, turns, procs=self.procs, lo=lo, hi=hi)
        g.state, g.scan_draws = "scanning", len(seen)

    def _start_rescan(self, obs, g):
        """杠杆④ deck-modify 失锁重扫：用首 obs 开局可靠抽牌（任何 deck-modify 之前）重扫种子候选。

        冻结的 tr.seen/tr.skip 被 deck-modify 污染时内核会排除真种子；opening_seen/opening_skip 在首 obs
        快照（turn1 开局抽牌），diag 实证 4 怪物 opening_match 全 True。重置候选管线，scan_phase 归 0
        （开局抽牌弱约束→候选多，FastCut 手牌回放 + 整屏核对收敛真种子）。"""
        turns = [int(t) for t in obs["exam"]["types"][:self.mutable]] if self.pool_attr else None
        seen = list(g.opening_seen or ())
        skip = list(g.opening_skip or ())
        g.cands, g.mirrors, g.mirror = None, {}, None
        g.cut_pos, g.cut_pile, g.cut_n = None, None, 0
        g.scan_phase, g.near = 0, None
        g.scan = self.seedscan.Scan(self.k, self.pre, seen, skip,
                                    self.pool_attr, turns, procs=self.procs, lo=0, hi=self.hi)
        g.state, g.scan_draws, g.rescan_used = "scanning", len(seen), True

    def _fail_or_rescan(self, obs, g, why):
        """主扫描失锁点：graph-clean 牌组（消费图 opt-in）且未重扫过 → 开局重扫；否则如实 failed。"""
        if (self.rescan_open and not g.rescan_done and g.graph_clean
                and g.opening_seen and len(g.opening_seen) >= 1):
            g.rescan_done = True
            self._start_rescan(obs, g)
            return
        g.state, g.why = "failed", why

    def _cut(self, obs, deadline, g):
        t = time.perf_counter()
        try:
            hands = g.hands + [[c["id"] for c in obs["hand"]]]
            cands, i, kept = g.cands, g.cut_pos, []
            with _ENGINE_LOCK:
                while i < len(cands) and time.perf_counter() < deadline:
                    if g.cutter.follows(cands[i], g.actions, hands):
                        kept.append(cands[i])
                    i += 1
            g.cut_n += i - g.cut_pos - len(kept)
            g.cands = cands[:g.cut_pos] + kept + cands[i:]
            g.cut_pos += len(kept)
            if g.cut_pos >= len(g.cands):
                g.cut_pos, g.cut_pile = None, len(obs["deck"])
        except Exception:  # noqa: BLE001
            g.cut_pos, g.cut_pile = None, len(obs["deck"])
        g.cut_s += time.perf_counter() - t

    def _search(self, obs, deadline, wait_until, g):
        from uinet.env import Battle
        tr = g.tracker
        turn = int(obs["exam"]["turn"])
        if g.state == "none":
            if len(tr.seen) >= self.scan_min or (not tr.open and len(tr.seen) >= 3):
                self._start_scan(obs, g)
            elif not tr.open:
                self._fail_or_rescan(obs, g, "too few draws read before the pile changed")
        if g.state == "scanning":
            seeds = g.scan.poll()
            while seeds is None and time.perf_counter() < wait_until:
                time.sleep(0.02)
                seeds = g.scan.poll()
            if seeds is None:
                return
            if not seeds and g.scan_phase == 0 and self.hi < (1 << 32):
                g.scan_phase = 1                     # 下半程没有：补扫上半程 [2^31, 2^32)
                self._start_scan(obs, g)
                return
            g.scan_s, g.n_cands, g.cands, g.state = round(g.scan.seconds, 2), len(seeds), seeds, "candidates"
            g.scan = None
            g.cut_pos = 0 if len(seeds) > self.max_mirrors else None
        if g.state != "candidates":
            return
        if g.cut_pos is None and len(g.cands) + len(g.mirrors) > self.max_mirrors and g.cut_pile != len(obs["deck"]):
            g.cut_pos = 0
        if g.cut_pos is not None:
            self._cut(obs, deadline, g)
            if g.cut_pos is not None:
                return
        while g.cands and len(g.mirrors) < self.max_mirrors and time.perf_counter() < deadline:
            s = g.cands.pop()
            m = None
            try:
                with _ENGINE_LOCK:
                    m = g.cutter.battle(s, g.actions)
            except Exception:  # noqa: BLE001
                m = None
            if m is None:
                try:
                    m = Battle(dict(self.lo, seed=int(s)))
                    for a in g.actions:
                        m.step(a)
                except Exception:  # noqa: BLE001
                    m = None
            if m is not None:
                g.mirrors[s] = m
        gone = [s for s, m in g.mirrors.items() if m.finished or not _same(m.obs(), obs)]
        if gone and len(gone) == len(g.mirrors) and not g.cands:
            m = g.mirrors[gone[-1]]
            g.near = "the battle is over" if m.finished else _differs(m.obs(), obs)
        for s in gone:
            del g.mirrors[s]
        if not g.cands:
            if len(g.mirrors) == 1:
                (seed, _m), = g.mirrors.items()
                try:
                    m = Battle(dict(self.lo, seed=int(seed)))
                    for a in g.actions:
                        m.step(a)
                    ok = not m.finished and _same(m.obs(), obs)
                except Exception:  # noqa: BLE001
                    ok = False
                if ok:
                    g.mirror, g.mirrors, g.state = m, {}, "locked"
                    g.lock_turn, g.locked_seed = turn, int(seed)
                    self.pool.reset()
                else:
                    g.mirrors = {}
                    self._fail_or_rescan(obs, g, "the last candidate does not rebuild to the screen")
            elif not g.mirrors:
                self._fail_or_rescan(obs, g, "no seed reproduces the screen")

    # -- 搜索原语 ----------------------------------------------------------------
    def _gnrpa(self, session, sec, sd=182):
        """锁定前投票 / 兜底用的 anytime 短搜（deadline 口径，ex-seed 原样）。"""
        return self.ns.policy_search(session, deadline=max(0.02, sec), seed=sd, variant="gnrpa",
                                     levels=self.levels, iterations=self.iterations,
                                     stabilization=self.stabilization, prior=self.pr)

    def _tail(self, session, sec):
        from GakumasCLI.native import tail_native as TN
        self._calibrate_tail(TN, session)
        path, score, st = TN.tail_exact(session, seconds=max(0.05, sec), nat=self.nat,
                                        threads=self.tail_threads, node_cap=20_000_000)
        status = st.get("status")                    # tail_native 给的是字符串（STATUS[rc]）
        if status in (2, "deadline") and st.get("seconds", 1) < 0.05 and sec > 0.5:
            raise RuntimeError("tail clock epoch mismatch")     # 退回 GNRPA，不拿浅搜结果
        if status in (0, 1, 2, "complete", "node_cap", "deadline") and path:
            return tuple(path), int(score), st
        raise RuntimeError(f"tail status {status}")

    def _calibrate_tail(self, TN, session):
        """tail 的 deadline 是绝对时刻：DLL 的 steady_clock 纪元随编译器不同
        （mingw ≈ Unix 纪元 = time.time()；MSVC / macOS ≈ 开机 = time.monotonic()）。
        用小节点上限探一次，纪元不对就改 _host_now。每进程一次。"""
        if _TAIL_CALIBRATED[0]:
            return
        import ctypes as C
        with _ENGINE_LOCK:
            if _TAIL_CALIBRATED[0]:
                return
            TN._bind(self.nat)
            own = session.search_tables()
            try:
                params = TN.TailParams(node_cap=20000, deadline=time.monotonic() + 1.0,
                                       tt_capacity=1 << 20, use_tt=1, threads=1,
                                       items_per_thread=0, pad=0)
                r = TN.TailResult()
                t0 = time.perf_counter()
                rc = self.nat.lib.gk_tail_exact(own.core, C.byref(params), C.byref(r))
                wall = time.perf_counter() - t0
                if rc == 2 and wall < 0.05:
                    TN._host_now = lambda nat: time.time()
            finally:
                own.free()
            _TAIL_CALIBRATED[0] = True

    # -- 锁定后：RoutePool 多起点搜索 ------------------------------------------------
    def _starts_now(self, g):
        """规模自适应起点：12 回合决赛多起点，其余保持 starts（starts_hi=0 时恒为 starts）。"""
        if self.starts_hi > self.starts and int(getattr(g, "limit_turn", 0) or 0) >= self.starts_hi_turn:
            return self.starts_hi
        return self.starts

    def _threads_now(self, g):
        """v5：决赛一波内并行起点数（1 = 串行，等同 v4 调度）。"""
        if (self.pool_threads_hi > self.pool_threads
                and int(getattr(g, "limit_turn", 0) or 0) >= self.pool_threads_hi_turn):
            return self.pool_threads_hi
        return self.pool_threads

    def _waves_now(self, g):
        """v5：波次上限（0 = 填满 t_end；1 = 一波 = v4 行为）。"""
        if self.waves_hi and int(getattr(g, "limit_turn", 0) or 0) >= self.waves_hi_turn:
            return self.waves_hi
        return self.waves

    def _executor(self, threads):
        """并行起点线程池（每个算法实例一个；线程数变了就重建）。"""
        ex = self._ex
        if ex is None or ex[0] != threads:
            if ex is not None:
                try:
                    ex[1].shutdown(wait=False)
                except Exception:  # noqa: BLE001
                    pass
            ex = (threads, ThreadPoolExecutor(max_workers=threads, thread_name_prefix="exseed-v5"))
            self._ex = ex
        return ex[1]

    def _search_task(self, clone, trans, sec, sd, cfg=None):
        """并行起点 worker：在**自己的 core 副本**（session.clone()）上跑一条 GNRPA 路线。
        返回 (route, stats)；核心拒绝/异常返 (None, None)。不在这里采纳（回放核分在主线程串行做）。"""
        lv, it, stb = cfg if cfg else (self.levels, self.iterations, self.stabilization)
        try:
            path, st = self.ns.policy_search(clone, transitions=int(trans), deadline=float(sec),
                                             seed=int(sd), variant="gnrpa",
                                             levels=int(lv), iterations=int(it),
                                             stabilization=int(stb), prior=self.pr)
        except Exception as e:  # noqa: BLE001 -- 核心拒绝的状态：没有提案
            if len(self.dbg_errors) < 8:
                import traceback
                self.dbg_errors.append(f"{type(e).__name__}: {e} | "
                                       f"{traceback.format_exc().strip().splitlines()[-1]}")
            return None, None
        return (tuple(path) if path else None), st

    def _root_task(self, clone, action, trans, sec, sd):
        """根动作枚举 worker：副本上先走 action，再从后继状态搜一条完整路线，返回整条 route。
        返回 (route, stats)；核心拒绝/不支持返 (None, st)。"""
        try:
            if clone.finished:
                return None, None
            clone.step(tuple(action), observe=False)
            if clone.finished:
                return (tuple(action),), {"status": 0, "expansions": 0}
            path, st = self.ns.policy_search(clone, transitions=int(trans), deadline=float(sec),
                                             seed=int(sd), variant="gnrpa",
                                             levels=self.levels, iterations=self.iterations,
                                             stabilization=self.stabilization, prior=self.pr)
        except Exception as e:  # noqa: BLE001
            if len(self.dbg_errors) < 8:
                import traceback
                self.dbg_errors.append(f"root {type(e).__name__}: {e} | "
                                       f"{traceback.format_exc().strip().splitlines()[-1]}")
            return None, None
        if not path or int(st.get("status", 0)) != 0:
            return None, st
        return (tuple(action),) + tuple(path), st

    def _root_scan(self, session, legal, t_end, g, meta, trans):
        """根动作枚举（v5）：每个合法根动作各先走一步、再从后继状态完整续搜一条路线（整条回放核分进池）。
        RoutePool 只采纳更高终局分 → 单调安全；枚举保证每个根动作都被完整续搜评估一次。"""
        pool = self.pool
        cand = [tuple(a) for a in legal][:self.root_scan_max]
        if not cand:
            return 0
        threads = self._threads_now(g)
        ex = self._executor(threads) if threads > 1 and len(cand) > 1 else None
        jobs = []
        for a in cand:
            left = t_end - time.perf_counter()
            if left < self.min_search_sec:
                break
            sec = max(0.05, min(left, self.search_deadline_cap))
            sd = pool.seed + 104729 + 7919 * len(jobs) + 1009 * pool.n
            if ex is None:
                jobs.append((a, None, sec, sd))
            else:
                jobs.append((a, ex.submit(self._root_task, session.clone(), a, trans, sec, sd), sec, sd))
        n = 0
        for a, fut, sec, sd in jobs:
            n += 1
            if fut is None:
                route, st = self._root_task(session.clone(), a, trans, sec, sd)
            else:
                try:
                    route, st = fut.result()
                except Exception:  # noqa: BLE001
                    continue
            pool.offer_stats(session, route, st)
        return n

    def _pool_search(self, session, t_end, g, meta, lock=False, legal=None):
        """一个搜索机会：starts×waves 个不同 sd 起点各搜一条路线，回放核分进池（跨步累积）。

        v4（waves=1 & pool_threads=1）逐位原路径见 `_pool_search_v4`。
        v5 机制：transitions 帽（500k/起点）≈0.4–0.6s 先到，10s 预算只用了 2–4s → 空转的墙钟换成
        **同深度的更多独立起点**（多波次 + 并行 core 副本）；root_scan=1 时先用根动作枚举覆盖每个
        合法首动作。RoutePool 只采纳更高终局分 → 单调安全。
        """
        if (self._waves_now(g) == 1 and self._threads_now(g) <= 1
                and not self.root_scan and not self.portfolio):
            self._pool_search_v4(session, t_end, g, meta, lock=lock)
            return
        pool = self.pool
        trans = self.lock_trans if lock else self.step_trans
        if self.root_scan and legal:
            meta["root_scan_n"] = self._root_scan(session, legal, t_end, g, meta, trans)
        n_starts = self._starts_now(g)
        threads = self._threads_now(g)
        waves = self._waves_now(g)
        ex = self._executor(threads) if threads > 1 else None
        searches, wave, refused, statuses, failed = 0, 0, False, {}, 0
        while True:
            if t_end - time.perf_counter() < self.min_search_sec:
                break
            if waves and wave >= waves:
                break
            trans_w = trans
            if self.deep_trans > trans and wave < self.deep_waves:
                trans_w = self.deep_trans                      # 前几波深预算（exploit），其余快探索
            batch = []
            for i in range(n_starts):
                left = t_end - time.perf_counter()
                if left < self.min_search_sec:
                    break
                sd = pool.seed + 1009 * pool.n + 7919 * i + 104729 * wave
                sec = max(0.05, min(left, self.search_deadline_cap))
                cfg = None
                if self.portfolio and (wave > 0 or self.portfolio_first):
                    # 组合轮换：portfolio_first=0 时 wave 0 保持 base 配置（严格不减）；=1 时
                    # 第一波就逐起点轮换（v4 的 6 个起点换成 6 种配置，墙钟与 v4 相同）。
                    cfg = self.portfolio[(wave * n_starts + i) % len(self.portfolio)]
                if ex is None:
                    batch.append((sd, sec, None, cfg))
                else:
                    batch.append((sd, sec, ex.submit(self._search_task, session.clone(), trans_w,
                                                     sec, sd, cfg), cfg))
            if not batch:
                break
            for sd, sec, fut, cfg in batch:
                searches += 1
                if fut is None:
                    st = pool.search_offer(session, trans_w, sec, sd, cfg=cfg)
                    if st is None:
                        meta["search_why"] = "policy_search refused the state"
                        refused = True
                        break
                    continue
                try:
                    path, st = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                key = (-2 if st is None else int((st or {}).get("status", -1)))
                statuses[key] = statuses.get(key, 0) + 1
                if st is None:
                    failed += 1
                pool.offer_stats(session, path, st)
            if failed and failed >= len(batch) and wave >= 1:
                # 整波 worker 全部异常（配置/环境问题）：不再空转，如实上报
                meta["pool_err"] = self.dbg_errors[-3:]
                break
            if refused:
                break
            wave += 1
        meta["pool_searches"] = searches
        meta["pool_waves"] = wave
        if threads > 1:
            meta["pool_threads"] = threads
        if self.dbg_errors and "pool_err" not in meta:
            meta["pool_err"] = self.dbg_errors[-3:]
        meta["pool_status"] = statuses
        meta["pool_adopted"] = pool.stats["adopted"]
        meta["pool_bad"] = pool.stats["bad_routes"]

    def _pool_search_v4(self, session, t_end, g, meta, lock=False):
        """v4 原调度（逐位复现用）：一波 starts 个不同 sd 起点，均分剩余时间，transitions 每起点封顶。"""
        pool = self.pool
        trans = self.lock_trans if lock else self.step_trans
        n_starts = self._starts_now(g)
        for i in range(n_starts):
            left = t_end - time.perf_counter()
            if left < 0.12:
                break
            sec = left / (n_starts - i)
            sd = pool.seed + 1009 * pool.n + 7919 * i
            st = pool.search_offer(session, trans, max(0.05, sec), sd)
            if st is None:
                meta["search_why"] = "policy_search refused the state"
                break

    def _greedy_play(self, obs, legal):
        """无路线兜底：引擎卡表即时分贪心（exam_session.greedy_policy 同口径）。"""
        best, best_value = None, -1
        for a in legal:
            if a[0] != "play":
                continue
            card = obs["hand"][a[1]]
            row = self.master.cards.get((card["id"], int(card.get("u") or 0)))
            if row is None:
                tiers = [u for (k, u) in self.master.cards if k == card["id"] and u <= int(card.get("u") or 0)]
                row = self.master.cards.get((card["id"], max(tiers))) if tiers else {}
            value = 0
            for link in (row or {}).get("playEffects") or ():
                effect = self.master.effects.get(link.get("produceExamEffectId")) if isinstance(link, dict) else None
                t = (effect or {}).get("effectType")
                t = t.get("number") if isinstance(t, dict) else t
                if t in (1, 56, 23):
                    value += int((effect or {}).get("effectValue1") or 0)
                elif t == 49:
                    value += 2 * int((effect or {}).get("effectValue1") or 0)
            if value > best_value:
                best, best_value = a, value
        if best is not None:
            return best
        for a in legal:
            if a[0] != "end":
                return a
        return legal[0]

    def _locked_action(self, obs, legal, plays, t_end, g, meta):
        s = g.mirror.session
        turn = int(obs["exam"].get("turn") or 0)
        turns_left = int(obs["exam"].get("limit") or 0) - turn + 1
        pool = self.pool
        adopted0 = pool.stats["adopted"]
        # 1) 末段精确尾搜索（剩 ≤tail_turns 回合且未证完）：整段剩余时间给它
        if 0 < turns_left <= self.tail_turns and not pool.proven and t_end - time.perf_counter() > 0.15:
            try:
                path, best, st = self._tail(s, t_end - time.perf_counter())
                meta["tail_status"] = st.get("status")
                pool.stats["tails"] += 1
                pool.offer(s, path, source="tail", proven=st.get("status") in (0, "complete"))
            except Exception as e:  # noqa: BLE001
                meta["tail_why"] = f"{type(e).__name__}: {e}"
        # 2) 每步多起点 GNRPA 重搜（路线池跨步累积；证完最优后不再搜）
        if not pool.proven and t_end - time.perf_counter() > 0.12:
            self._pool_search(s, t_end, g, meta, lock=not g.did_lock_search, legal=legal)
            g.did_lock_search = True               # 仅在锁定步搜索真正跑过后置位；晚锁定步时间不够则下步重试 lock_trans
        # 3) 照在手路线首动作打
        a = pool.take()
        if a is not None and (a[0] == "select" or a in legal):
            action = a
            mode = "tail" if pool.proven else ("search" if pool.stats["adopted"] > adopted0 else "route")
            meta["target"] = pool.target
        else:
            if a is not None:
                pool.played(a)                       # 路线首动作不合法：丢弃
                meta["route_illegal"] = list(a)
            action = self._greedy_play(obs, legal)
            mode = "fallback"
            pool.played(action)
        # 4) forced_play 硬规矩（缺省关；=1 恢复 ex-seed 行为）：有可出牌绝不 end
        if self.forced_play and action[0] == "end" and plays:
            action = self._best_play(s, plays, max(0.1, t_end - time.perf_counter()), meta)
            pool.played(action)                      # 偏离路线：丢弃，下步重搜
            mode = "forced"
            meta["hard_rule"] = "no-end"
        return action, mode

    def _best_play(self, session, plays, left, meta):
        """硬规矩兜底：逐 play 先走再短搜，取期望分最高（ex-seed 原样）。"""
        sec = min(0.6, max(0.05, left / max(1, len(plays))))
        vals = {}
        for a in plays:
            w = session.clone()
            try:
                w.step(a, observe=False)
            except Exception:  # noqa: BLE001
                continue
            if w.finished:
                vals[a] = int(w.state.score)
                continue
            _p, st = self._gnrpa(w, sec)
            vals[a] = max(int(st.get("best_score", 0)), int(w.state.score))
        if not vals:
            return plays[0]
        meta["play_vals"] = {str(list(a)): int(v) for a, v in vals.items()}
        return max(vals, key=vals.get)

    # -- 锁定前：候选世界投票（ex-seed 原样，forced_play 参数化） ----------------------
    def _vote_sessions(self, sessions, legal, plays, left, meta):
        """候选对局 / 重抽世界各搜一遍，首动作投票（平票比平均预期分）。"""
        n = len(sessions)
        cap = self.vote_sec_cap
        if (self.vote_sec_cap_hi > cap
                and int(getattr(self.g, "limit_turn", 0) or 0) >= self.vote_sec_cap_hi_turn):
            cap = self.vote_sec_cap_hi
        sec = min(cap, max(0.05, left / n))
        votes, scores = defaultdict(int), defaultdict(list)
        for i, s in enumerate(sessions):
            try:
                path, st = self._gnrpa(s, sec, sd=182 + i)
            except Exception:  # noqa: BLE001
                continue
            a = _first_legal(path, legal)
            if a is None:
                continue
            votes[a] += 1
            scores[a].append(int(st.get("best_score", 0)))
        if not votes:
            raise RuntimeError("no vote")
        best = max(votes, key=lambda a: (votes[a], sum(scores[a]) / len(scores[a])))
        if self.forced_play and best[0] == "end" and plays:
            pv = {a: v for a, v in votes.items() if a[0] == "play"}
            best = max(pv, key=lambda a: (pv[a], sum(scores[a]) / len(scores[a]))) if pv else plays[0]
            meta["hard_rule"] = "no-end"
        meta["votes"] = {str(list(a)): [votes[a], int(sum(scores[a]) / len(scores[a]))] for a in votes}
        return best

    def _worlds_action(self, ctx, legal, plays, left, meta):
        ws = ctx.worlds(self.vote_worlds)
        meta["worlds"] = len(ws)
        return self._vote_sessions([w for w in ws], legal, plays, left, meta)

    # -- 决策 --------------------------------------------------------------------
    def decide(self, ctx):
        t0 = time.perf_counter()
        budget = float(ctx.budget or 10.0)
        g = self.g
        obs = {k: v for k, v in ctx.obs.items() if k != "i"}
        legal = [tuple(a) for a in obs["legal"]]
        plays = [a for a in legal if a[0] == "play"]
        meta = {}
        g.limit_turn = int((obs.get("exam") or {}).get("limit") or 0)
        if g.state not in ("failed", "lost"):
            try:
                if g.state != "locked":
                    first = g.opening_seen is None
                    g.tracker.update(obs)
                    if first:
                        # 首 obs 开局可靠抽牌快照（任何 play/deck-modify 之前）= 失锁重扫的干净约束。
                        g.opening_seen = list(g.tracker.seen)
                        g.opening_skip = list(g.tracker.skip.elements())
                    if self.scan_wait_mode == "done":
                        # 去墙钟化（sl3b 锁定等待悬崖）：等扫描进程真正完成（上限 scan_wait_cap×budget），
                        # cut/mirror 管线 deadline=lock_pipe×budget；不再用 0.7×budget 墙钟截断翻锁定回合。
                        self._search(obs, t0 + self.lock_pipe * budget, t0 + self.scan_wait_cap * budget, g)
                    else:
                        self._search(obs, t0 + 0.75 * budget, t0 + 0.7 * budget, g)
                elif g.mirror.finished or not _same(g.mirror.obs(), obs):
                    g.near = "the battle is over" if g.mirror.finished else _differs(g.mirror.obs(), obs)
                    g.state, g.lost_turn = "lost", int(obs["exam"]["turn"])
                    g.why = f"the screen differs from the solved battle at turn {g.lost_turn}"
            except Exception as e:  # noqa: BLE001
                g.state, g.why = "failed", f"{type(e).__name__}: {e}"
        action, mode = None, "fallback"
        t_end = t0 + self.search_use * budget
        left = t_end - time.perf_counter()
        if len(legal) == 1:
            action, mode = legal[0], "forced"
            if g.state == "locked":
                self.pool.played(action)             # 强制动作与路线同步（一致则续，否则丢弃）
        elif g.state == "locked":
            try:
                action, mode = self._locked_action(obs, legal, plays, t_end, g, meta)
            except Exception as e:  # noqa: BLE001
                meta["search_why"] = f"{type(e).__name__}: {e}"
        elif (g.state == "candidates" and len(g.mirrors) > 1 and left > 0.2
              and (self.mirror_vote or (not g.cands and g.cut_pos is None))):
            # v5 mirror_vote：锁定前的候选世界是**与画面一致的后验样本**（含真种子），比
            # ctx.worlds() 随机重抽的先验世界信息量大得多 → 只要已有 ≥2 个候选就按后验投票
            # （等价 PIMC 用真 belief set；v4 只在候选管线跑空后才这么做）。
            try:
                sel = list(g.mirrors.values())
                if self.mirror_vote and len(sel) > self.vote_worlds:
                    n = len(sel)
                    sel = [sel[(i * n) // self.vote_worlds] for i in range(self.vote_worlds)]
                action = self._vote_sessions([m.session for m in sel], legal, plays, left, meta)
                mode = "vote"
                meta["vote_worlds"] = len(sel)
            except Exception as e:  # noqa: BLE001
                meta["vote_why"] = f"{type(e).__name__}: {e}"
        if action is None:
            try:
                action = self._worlds_action(ctx, legal, plays, max(0.2, t_end - time.perf_counter()), meta)
                mode = "worlds"
            except Exception as e:  # noqa: BLE001
                meta["error"] = f"{type(e).__name__}: {e}"
                action = plays[0] if plays else legal[0]
                mode = "fallback"
        if self.forced_play and action[0] == "end" and plays and mode in ("worlds", "fallback"):
            action = plays[0]
            meta["hard_rule"] = "no-end"
        g.actions.append(action)
        g.hands.append([c["id"] for c in obs["hand"]])
        for s, m in list(g.mirrors.items()):
            try:
                m.step(action)
            except Exception:  # noqa: BLE001
                del g.mirrors[s]
        if g.state == "locked":
            try:
                g.mirror.step(action)
            except Exception as e:  # noqa: BLE001
                g.state, g.why = "lost", f"{type(e).__name__}: {e}"
        meta.update(mode=mode, seed_state=g.state, ms=round((time.perf_counter() - t0) * 1000, 1))
        if g.graph_clean is not None:
            meta["graph_clean"] = bool(g.graph_clean)
        if g.rescan_used:
            meta["rescan_used"] = True
        g.counts[mode] = g.counts.get(mode, 0) + 1
        if g.state == "candidates":
            meta["candidates"] = len(g.cands or ()) + len(g.mirrors)
        if g.lock_turn is not None:
            meta["lock_turn"], meta["locked_seed"] = g.lock_turn, g.locked_seed
        if g.scan_s is not None:
            meta["scan_s"], meta["scan_hits"], meta["scan_draws"] = g.scan_s, g.n_cands, g.scan_draws
        if g.state == "locked" and self.pool is not None:
            meta["adopted"], meta["bad_routes"] = self.pool.stats["adopted"], self.pool.stats["bad_routes"]
        if g.why:
            meta["why"] = g.why
        if g.near and g.state in ("lost", "failed"):
            meta["differs"] = g.near
        return Decision(action, meta)
