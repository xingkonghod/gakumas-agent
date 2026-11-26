"""⑦ 全流程 sim 评估 glue（我们的代码，可提交；AGPL 引擎只外部 import，不拷源码进 src/gkagent）。

GKMSPS（data/GKMSMainWheel/GKMSPS，AGPL）完整培育局（選抜 produce-007 → 本戦 produce-008，
课程/外出/饮料/考试链）决策点 plug，配对评估我们的搜索+培育决策 vs GKMSPS 默认 policy：

- **考试段 plug**：GKMSPS 考试决策点 → r14 学生网真实投稿适配器 decide()（含硬规矩/异常回退）。
  状态映射承 data/bench_repo/submissions/gkagent-ei-r14/algo.py 的 UIObs→State 自包含口径
  （import 复用不重写）；obs 用引擎权威 UIObs 构造器 uinet.uiobs.from_session（与托管观测同口径，
  r14 已 329 局托管观测验证）。r14 从不主动喝饮料（投稿口径；OFFICIAL_AI_NOTES H10 同剪枝）。
- **培育段 plug**：我们 tasks/produce.py / produce_ui.py 决策规则的离线版（import 复用
  produce_ui.choose_action_kind 体力门 8/12；choose_training 的补短板原则；事件选项按效果估值
  = 评价点目标）+ 卡估值用 r14 card_profiles（我们的 id 键画像）+ 饮料估值用阶段1 catalog
  data/knowledge/drinks.json（SAFE 口径；青汁 pdrink_00-3-005 unknown RNG → 保守不喝臂）。
- **对照臂**：GKMSPS 自带 cli.auto(sensible=True)（smoke policy：拿卡/干活/买卡 + 考试单步贪心
  greedy_exam_index），即 GKMSPS 默认 policy，引擎文件零改动。
- **配对**：同 formation 同 root（選抜 root_i = sha256(tag:i)，本戦 root = sha256(root_i:hon)），
  两臂同 seed；RNG 是 label 流（GKMSPS ps/rng.py），同 root 保证排期/考试种子/NPC 同流。
- **青汁消融**（考试级注入配对，≤20 局）：本戦终试 loadout 注入 pdrink_00-3-005，
  r14+强制首口喝 vs r14 不喝，同 seed 配对，量化 unknown RNG 扰动代价。

纪律：不重编 DLL（UINET_NATIVE_LIB 指已编通 gkmscore.dll，先例 _gkmsps_offline_gate.py 同接法）；
不往引擎工作树写文件——本 checkout 缺 GKMSPS/data/master_ps.json（build_ps_data 生成件），
运行时从本地 ro/master/tables jsonl 生成到 data/_gkmsps_plug_data/（探针目录不提交）并
 monkeypatch GKMSPS.ps.data.DATA（只进程内存，引擎文件零改动，先例 _gkmsps_gen_run.py 同纪律）。

選抜 NPC 墙（probe11 实测，idol 固定难度带）：mid1 双 6035 / mid2 双 49806 / final 双 136347，
过关线 rank≤2。两臂培育上限远低于 mid2/final 墙（pilot5 真实選抜全 lost、全零），故评估用
--sel-assume 让两臂選抜考试同值强制过关（probe9 先例），选抜培育段仍真实、本戦全真实。
本戦 mid1 rank≤3 必过（2 NPC），final rank≤1 墙 ~618k（几乎必 lost，round2=接受结算分）。

用法（root）：
    .venv\\Scripts\\python.exe -B scripts\\gkmsps_plug.py --smoke
    .venv\\Scripts\\python.exe -B scripts\\gkmsps_plug.py --n 100 --ablation 20 --sel-assume 300000 `
        --formation data\\_gkmsps_plug_data\\formation_v2.json --resume `
        --out out\\_gkmsps_plug_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
DLL = WHEEL / "GakumasCLI" / "native" / "build" / "gkmscore.dll"
for _p in (WHEEL, WHEEL / "GKMSUINet", ROOT / "data" / "bench_repo", ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
os.environ.setdefault("UINET_NATIVE_LIB", str(DLL))

PLUG_DATA = ROOT / "data" / "_gkmsps_plug_data"          # 探针生成件，不提交
AOJIRU = ("pdrink_00-3-005", "pdrink_00-3-013")          # 青汁 / 青汁X（unknown RNG）
ATTRS = ("vocal", "dance", "visual")
LABEL = {"vocal": "Vo", "dance": "Da", "visual": "Vi"}
REST_THRESHOLD = 4          # 体力门阈值（produce_ui.choose_action_kind 复用，阈值按 sim 体力尺度调）
LESSON_RESERVE = 2          # 课后体力保留（sim 课程费 6-8 / 上限 44；考试前免费回复兜底）


# ---------------------------------------------------------------- 缺件①：master 枚举拼写
# 本 checkout 的 ro/master/tables 是客户端导出（枚举名混用 camelCase，如 ProduceCardRarity_N），
# 而 GKMSPS / GakumasCLI produce 层按 master-bootstrap 规范拼写读（PRODUCE_CARD_RARITY_N，
# 见 tools/master_schema.json enums）。解法：按 schema 的 norm→规范名 映射把本地表的枚举名
# 重拼写到探针目录（数值/number 全保留，引擎工作树零写入），再进程内存重定向读取点。
def _build_master_tables(out_dir: Path) -> dict:
    from GakumasCLI.tools import master_convert as MC
    schema = json.loads((WHEEL / "GakumasCLI" / "tools" / "master_schema.json").read_text(encoding="utf-8"))
    enums = {k: tuple(v) for k, v in schema["enums"].items()}
    src = WHEEL / "GakumasCLI" / "ro" / "master" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = out_dir / "_stamp.json"
    if stamp.is_file():
        return json.loads(stamp.read_text(encoding="utf-8"))
    renamed = mismatch = kept = files = 0

    def walk(x):
        nonlocal renamed, mismatch, kept
        if isinstance(x, dict):
            if set(x) == {"name", "number"} and isinstance(x["name"], str):
                e = enums.get(MC.norm(x["name"]))
                if e:
                    if x["name"] != e[0]:
                        renamed += 1
                    if x["number"] is not None and e[1] is not None and int(x["number"]) != int(e[1]):
                        mismatch += 1
                    x["name"] = e[0]
                else:
                    kept += 1
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for f in sorted(src.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh, open(out_dir / f.name, "w", encoding="utf-8", newline="\n") as oh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                walk(row.get("decoded"))
                oh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        files += 1
    info = {"files": files, "enum_renamed": renamed, "number_mismatch": mismatch, "not_in_schema": kept,
            "source": str(src), "schema": "tools/master_schema.json"}
    stamp.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def _patch_master(conv: Path) -> None:
    """读取点重定向（只进程内存，引擎文件零改动）：pe._rows / 各 MASTER_DIR 常量 /
    exam_loading 导入期默认行 / hif_seed_solve 考试 Master（→ master.master_dir 全链）。"""
    import GakumasCLI.paths as P
    from GakumasCLI.produce import produce_effects as pe
    from GakumasCLI.produce import offer_coverage as OC
    P.MASTER_DIR = conv
    pe.MASTER_DIR = conv
    OC.MASTER_DIR = conv
    _orig_rows = pe._rows

    def _rows(table, master=conv):
        return _orig_rows(table, conv)

    pe._rows = _rows
    from GakumasCLI.engine import exam_loading as EL

    def _row(fname, fid=None):
        p = conv / fname
        if p.is_file():
            for raw in p.read_text(encoding="utf-8").splitlines():
                if raw.strip():
                    d = json.loads(raw).get("decoded", {})
                    if fid is None or d.get("id") == fid:
                        return d
        return {}

    EL.DEFAULT_EXAM_SETTING = _row("ExamSetting.jsonl", "p_exam_setting-1")
    EL.DEFAULT_GLOBAL_SETTING = _row("Setting.jsonl")
    from GakumasCLI.tools import hif_seed_solve as H
    from GakumasCLI.scenario.exam_session import Master
    H._MASTER = Master.load(conv)


# ---------------------------------------------------------------- 缺件②：master_ps.json
def _build_master_ps(out: Path) -> None:
    """从本地 ro/master/tables（jsonl decoded）生成 GKMSPS 需要的 master_ps.json。

    字段与 GKMSPS/tools/build_ps_data.py master_ps() 逐一同构（dearness_skills / grade /
    true_end_bonus），只是数据源换成本 checkout 已有的 master 表（引擎工作树零写入）。
    """
    from GakumasCLI.produce import produce_effects as pe

    def grade_str(v):
        # RESULT_GRADE_SS_PLUS → SS+（memory_cost.py 同口径）
        return pe._name(v, "RESULT_GRADE_").replace("_PLUS", "+")

    def camel_member(v):
        # PRODUCE_TYPE_FIRST_STAR → FirstStar（GKMSPS TRUE_ENDS 口径）
        return "".join(p.title() for p in pe._name(v, "PRODUCE_TYPE_").split("_"))

    dear: dict = {}
    for r in pe._rows("CharacterDearnessLevel"):
        if r.get("produceSkills"):
            dear.setdefault(r["characterId"], {})[str(r["dearnessLevel"])] = [
                [s["id"], s["level"]] for s in r["produceSkills"]]
    grade = [[grade_str(r["grade"]), int(r.get("threshold") or 0)]
             for r in pe._rows("ProduceGrade") if r.get("produceGroupId") == "produce_group-003"]
    true_end: dict = {}
    for r in pe._rows("CharacterTrueEndBonus"):
        ch = r["id"].replace("character_true_end_bonus-", "")
        true_end.setdefault(ch, {})[camel_member(r["produceType"])] = {
            "vocal": int(r.get("produceVocal") or 0), "dance": int(r.get("produceDance") or 0),
            "visual": int(r.get("produceVisual") or 0),
            "g_vocal": int(r.get("produceVocalGrowthRatePermil") or 0),
            "g_dance": int(r.get("produceDanceGrowthRatePermil") or 0),
            "g_visual": int(r.get("produceVisualGrowthRatePermil") or 0),
            "stamina": int(r.get("produceStamina") or 0)}
    doc = {"format": "gkms.ps.master.v1",
           "source": {"mirror": "local GakumasCLI/ro/master/tables (jsonl decoded)", "commit": "local-checkout"},
           "dearness_skills": dear, "grade": grade, "true_end_bonus": true_end}
    out.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                   encoding="utf-8")


def _build_master_extra(out: Path) -> None:
    """从本地 jsonl master 生成 master_extra.json（formation.extra() 同构，数据源换本地表）。

    本 checkout 缺 GakumasCLI/produce/master_extra.json（master-bootstrap 生成件，仓库不含，
    先例 _gkmsps_gen_run.py 已记录）。IdolCards 需要 idol_cards 三段；support_events/open_lessons
    一并生成保持文档完整。引擎工作树零写入。
    """
    from GakumasCLI.produce import produce_effects as pe

    def rank(r):
        v = r.get("rank")
        return int(v["number"] if isinstance(v, dict) else str(v).rsplit("_", 1)[-1])

    from GakumasCLI.tools import master_convert as MC

    def etypes(r):
        return {MC.norm(pe._name(x) if isinstance(x, dict) else str(x)) for x in r.get("effectTypes") or ()}

    LL_STAMINA = MC.norm("IdolCardLevelLimitEffectType_ProduceStamina")
    POT_STAMINA = MC.norm("IdolCardPotentialEffectType_ProduceStamina")
    POT_ITEM = MC.norm("IdolCardPotentialEffectType_InitialProduceItemChange")
    status_up = [{"id": r["id"], "rank": rank(r), "vocal": int(r.get("produceVocal") or 0),
                  "dance": int(r.get("produceDance") or 0), "visual": int(r.get("produceVisual") or 0),
                  "stamina": int(r.get("effectValue") or 0) if LL_STAMINA in etypes(r) else 0}
                 for r in pe._rows("IdolCardLevelLimitStatusUp")]
    potential = [{"id": r["id"], "rank": rank(r), "g_vocal": int(r.get("produceVocalGrowthRatePermil") or 0),
                  "g_dance": int(r.get("produceDanceGrowthRatePermil") or 0),
                  "g_visual": int(r.get("produceVisualGrowthRatePermil") or 0),
                  "stamina": int(r.get("effectValue") or 0) if POT_STAMINA in etypes(r) else 0,
                  "item_change": POT_ITEM in etypes(r)}
                 for r in pe._rows("IdolCardPotential")
                 if any(r.get(k) for k in ("produceVocalGrowthRatePermil", "produceDanceGrowthRatePermil",
                                           "produceVisualGrowthRatePermil"))
                 or {POT_STAMINA, POT_ITEM} & etypes(r)]
    ll_skill = [{"id": r["id"], "rank": rank(r), "skill": r["produceSkillId"],
                 "level": int(r.get("produceSkillLevel") or 1)}
                for r in pe._rows("IdolCardLevelLimitProduceSkill")]
    details = {r["id"]: r.get("produceEffectIds") or [] for r in pe._rows("ProduceStepEventDetail")
               if str(r.get("id", "")).startswith("event-detail-s_card-")}
    events: dict = {}
    for r in pe._rows("ProduceEventSupportCard"):
        events.setdefault(r["supportCardId"], []).append(
            {"number": r["number"], "level": r.get("supportCardLevel") or 0,
             "detail": r["produceStepEventDetailId"],
             "effects": details.get(r["produceStepEventDetailId"], [])})
    doc = {"source": {"mirror": "local GakumasCLI/ro/master/tables (jsonl decoded)", "commit": "local-checkout"},
           "open_lessons": {r["id"]: {k: r[k] for k in ("mainParameter", "subParameter", "star", "stamina")}
                            for r in pe._rows("ProduceStepOpenLesson")},
           "support_events": {k: sorted(v, key=lambda e: e["number"]) for k, v in sorted(events.items())},
           "idol_cards": {"level_limit_status_up": status_up, "potential": potential,
                          "level_limit_produce_skill": ll_skill}}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def _patch_extra(extra_path: Path) -> None:
    """master_extra 缺件补丁（只进程内存）：formation/hif_route 的 EXTRA 常量 + IdolCards 默认参。"""
    import GakumasCLI.produce.formation as F
    import GakumasCLI.produce.hif_route as H
    import GakumasCLI.produce.hif_start as HS
    from GakumasCLI.produce import produce_effects as pe
    F.EXTRA = extra_path
    H.EXTRA = extra_path
    _orig = HS.IdolCards.__init__

    def _init(self, master=pe.MASTER_DIR, extra=extra_path):
        _orig(self, master, extra)

    HS.IdolCards.__init__ = _init


def ensure_ps_data() -> dict:
    from GKMSPS.ps import data as D
    PLUG_DATA.mkdir(parents=True, exist_ok=True)
    conv = PLUG_DATA / "master_tables"
    conv_info = _build_master_tables(conv)
    _patch_master(conv)
    extra = PLUG_DATA / "master_extra.json"
    if not (WHEEL / "GakumasCLI" / "produce" / "master_extra.json").is_file():
        if not extra.is_file():
            _build_master_extra(extra)
        _patch_extra(extra)
    if (D.DATA / "master_ps.json").is_file():
        return {"source": "engine-tree", "path": str(D.DATA), "master_extra": "engine-tree",
                "master_tables": conv_info}
    mp = PLUG_DATA / "master_ps.json"
    if not mp.is_file():
        _build_master_ps(mp)
    dm = PLUG_DATA / "draw_models.v1.json"
    if not dm.is_file():
        dm.write_bytes((D.DATA / "draw_models.v1.json").read_bytes())
    D.DATA = PLUG_DATA                      # 只进程内存 monkeypatch，引擎文件零改动
    return {"source": "generated-from-local-tables", "path": str(PLUG_DATA),
            "master_extra": str(extra) if extra.is_file() else "engine-tree",
            "master_tables": conv_info}


# ---------------------------------------------------------------- 我们的估值口径
def load_r14():
    algo_dir = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ei-r14"
    spec = importlib.util.spec_from_file_location("gkmsps_plug_r14", algo_dir / "algo.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gkmsps_plug_r14"] = mod
    spec.loader.exec_module(mod)
    return mod


class Values:
    """卡/饮料/课程/事件估值（我们的离线规则口径，全部透明可审）。"""

    def __init__(self, r14mod, drinks_path: Path):
        doc = json.loads((r14mod.HERE / "card_profiles.json").read_text(encoding="utf-8"))
        self.profiles = doc.get("cards") or {}
        catalog = json.loads(drinks_path.read_text(encoding="utf-8"))
        self.drinks = {r["id"]: r for r in catalog.get("drinks") or ()}

    # 卡：r14 23 维画像的**协同引擎**加权（v1.3）。
    # 关键发现（probe8）：真实 mid2 强牌组（引擎 537k-1.6M）满是 score=0 的引擎牌
    # （draw/extra_play/preservation/full_power_point/once），靠指針循环×乘法效果打分；
    # 静态打分牌（score 40-54）反而弱。故引擎列重权、静态分轻权（PLAN3 全力/集中尤甚）。
    def card(self, cid: str, up: int = 0, rarity: str = "", plan: str = "") -> float:
        hit = self.profiles.get(f"{cid}|{up}") or self.profiles.get(f"{cid}|0")
        if hit is None:
            return {"SSR": 5.0, "SR": 3.0, "R": 1.5}.get(rarity, 1.0) + 2.0 * int(up)
        p = hit["p"]
        # 列：0 score 1 cost 2 vitality 3 condition 4 focus 5 motivation 6 impression
        #     7 draw 8 imp_scale 9 preservation 10 fpp 11 extra_play 12 block_scale
        #     13 param_buff 14 strong 15 stam_rec 16 fp_scale 17 review_mult 18 cond_add
        #     19 fp_lesson 20 grow 21 encore 22 once
        engine = 3.0 * p[7] + 4.0 * p[11] + 3.0 * p[9] + 2.0 * p[10] + 2.0 * p[22]
        if plan == "PLAN3":                       # 全力/集中：fpp/温存/再动引擎加倍
            engine += 2.0 * p[10] + 1.5 * p[9] + 1.0 * p[16] + 1.0 * p[19]
        elif plan == "PLAN1":                     # 集中/好调：focus/condition 引擎
            engine += 1.5 * p[4] + 1.0 * p[3] + 1.0 * p[18]
        elif plan == "PLAN2":                     # 好印象/干劲：impression/review 引擎
            engine += 1.5 * p[6] + 1.0 * p[17] + 0.5 * p[5]
        body = (0.4 * p[0] + 0.5 * p[2] + 1.0 * p[4] + 0.8 * p[6] + 0.3 * p[5]
                + 0.03 * (p[8] + p[12]) + 0.6 * p[15] + 0.5 * p[13] + 0.5 * p[14]
                + 0.5 * p[21] - 0.3 * p[1])
        return engine + body + {"SSR": 1.5, "SR": 0.8, "R": 0.3}.get(rarity, 0.0) + 1.0 * int(up)

    # 饮料：阶段1 catalog SAFE 口径；unknown RNG 保守 ≤0（avoid 臂）/ 乐观 +8（take 臂）
    def drink(self, did: str, aojiru_mode: str = "avoid") -> tuple[float, bool]:
        row = self.drinks.get(did)
        if row is None:
            return (0.0, False)
        det = bool((row.get("rng") or {}).get("deterministic"))
        v = 0.0
        for e in row.get("effects") or ():
            k, val = e.get("kind"), float(e.get("value") or 0)
            v += {"stamina": 1.0, "score": 0.4, "vitality": 0.7, "focus": 2.0,
                  "condition": 3.0}.get(k, 0.0) * val
        if not det:
            v = 8.0 if aojiru_mode == "take" else min(v, 0.0) - 1.0
        return (v, det)


# ---------------------------------------------------------------- 培育段 plug 规则
class PlugProduce:
    """我们 tasks/produce.py / produce_ui.py 规则的 GKMSPS 离线版（信息集 = sim.s + 选项 +
    公开 master 数据 + 我们的 catalog；与默认臂同信息集，不用种子/不用未来信息）。"""

    def __init__(self, values: Values, aojiru_mode: str = "avoid"):
        self.v = values
        self.aojiru_mode = aojiru_mode
        self.stats = {"lessons": 0, "rests": 0, "schools": 0, "activities": 0, "presents": 0,
                      "shops": 0, "cards_gained": 0, "drinks_gained": 0, "aojiru_gained": 0,
                      "aojiru_declined": 0, "drinks_discarded": 0, "buys": 0, "upgrades": 0,
                      "suggests": 0, "fallbacks": 0}
        self._w_cache = None

    # -- 小工具 ---------------------------------------------------------------
    @staticmethod
    def _ok(opts):
        return [j for j, o in enumerate(opts) if not o.get("disabled")]

    def _rarity(self, sim, cid):
        from GKMSPS.ps.data import name
        return name(sim.d.card(cid).get("rarity"), "PRODUCE_CARD_RARITY_")

    def _card_v(self, sim, cid, up=0):
        return self.v.card(cid, up, self._rarity(sim, cid), sim.s.get("plan", ""))

    def _drink_v(self, sim, did):
        return self.v.drink(did, self.aojiru_mode)[0]

    def _weights(self, sim):
        if self._w_cache is None:
            crit = sim._criteria("final")
            tot = sum(crit.values()) or 1
            self._w_cache = {a: crit[a] / tot for a in ATTRS}
        return self._w_cache

    def _next_criteria(self, sim):
        """下一场考试的审查基准（选抜 mid1→mid2→final；本戦 mid1→final）。"""
        from GKMSPS.ps.sim import SELECTION
        s = sim.s
        if s["produce_id"] == SELECTION:
            order = ["mid1", "mid2", "final"]
        else:
            order = ["mid1", "final"]
        done = set(s["auditions"])
        nxt = next((x for x in order if x not in done), order[-1])
        return sim._criteria(nxt)

    def _lesson(self, sim, attr):
        from GKMSPS.ps.data import PARAM_TYPE, name
        s, d = sim.s, sim.d
        les = d.open_lessons[s["schedule"][str(s["step"])][attr]]
        sub = PARAM_TYPE[name(les.get("subParameterType"))]
        g = s["growth"]
        main = int(les["mainParameter"]) * (1000 + g[attr]) // 1000
        subv = int(les["subParameter"]) * (1000 + g[sub]) // 1000
        w = self._weights(sim)
        # 评价点目标 v1.1：审查基准加权 + 低于下一场基准的属性加倍（penalty 悬崖，
        # audition.base_permils keep=1000-penalty_permil）+ 少量总参数/星（rating 项）。
        crit = self._next_criteria(sim)
        gain = {attr: main, sub: subv}
        val = 0.0
        for a, gv in gain.items():
            c = max(crit.get(a, 0), 1)
            gap = max(0, c - s["params"][a])
            val += 10.0 * w[a] * gv * (1.0 + gap / c)
        val += 1.0 * (main + subv) + 1.0 * int(les["star"])
        return val, int(les["stamina"])

    def _suggest_v(self, sim, sid):
        from GKMSPS.ps.data import name
        s, d = sim.s, sim.d
        g = d.suggestions[sid]
        v = 0.0
        w = self._weights(sim)
        for eid in g.get("produceEffectIds") or ():
            e = d.effect(eid)
            et = name(e.get("produceEffectType"), "PRODUCE_EFFECT_TYPE_")
            val = int(e.get("effectValueMin") or 0)
            if et in ("VOCAL_ADDITION", "DANCE_ADDITION", "VISUAL_ADDITION"):
                a = {"VOCAL_ADDITION": "vocal", "DANCE_ADDITION": "dance", "VISUAL_ADDITION": "visual"}[et]
                v += 2.0 * val + 3.0 * w[a] * val
            elif et == "STAMINA_RECOVER_FIX":
                v += 0.5 * val
            elif et == "STAMINA_RECOVER_MULTIPLE":
                v += 0.03 * val
            elif et == "PRODUCE_POINT_ADDITION":
                v += 0.05 * val
            elif et == "PRODUCE_REWARD_SET":
                res = name(e.get("produceResourceType"), "PRODUCE_RESOURCE_TYPE_")
                v += {"PRODUCE_CARD": 6.0, "PRODUCE_DRINK": 4.0, "PRODUCE_ITEM": 8.0,
                      "PRODUCE_CUSTOMIZE_ITEM": 6.0}.get(res, 2.0)
            elif et == "PRODUCE_CARD_CHANGE_SELECT":
                v += 3.0
            elif et == "PRODUCE_REWARD":
                v += 4.0
            else:
                v += 1.0
        if g.get("produceCardId"):
            v += self._card_v(sim, g["produceCardId"], int(g.get("produceCardUpgradeCount") or 0))
        v -= 0.5 * int(g.get("stamina") or 0) + 0.05 * int(g.get("producePoint") or 0)
        p = g.get("successProbabilityPermyriad")
        if p and not g.get("alwaysSuccessful"):
            v *= int(p) / 10000.0
        return v

    def _deck_cards(self, sim):
        return sorted(sim._deck(), key=lambda c: c["n"])

    # -- 主入口 ---------------------------------------------------------------
    def pick(self, sim, dec) -> int:
        kind, opts = dec["kind"], dec["options"]
        ok = self._ok(opts)
        if not ok:
            return 0
        s = sim.s
        try:
            j = self._pick(sim, kind, opts, ok)
            if j is not None and j in ok:
                return j
        except Exception:  # noqa: BLE001 - 规则异常如实计数，退回第一个合法选项
            pass
        self.stats["fallbacks"] += 1
        return ok[0]

    def _pick(self, sim, kind, opts, ok):
        s = sim.s
        if kind == "day":
            return self._day(sim, opts, ok)
        if kind == "offer":
            return self._offer(sim, opts, ok)
        if kind == "suggest":
            self.stats["suggests"] += 1
            return max(ok, key=lambda j: self._suggest_v(sim, opts[j]["sid"]))
        if kind in ("shop", "interval"):
            return self._shop(sim, kind, opts, ok)
        if kind == "drink_choice":
            return 0 if self._drink_v(sim, opts[0]["id"]) > 0 else 1
        if kind == "discard":
            return self._discard(sim, opts, ok)
        if kind == "change_confirm":
            t = sim.s["queue"][0]
            old = sim._card_by_number(t["n"])
            return 0 if self._card_v(sim, t["new"]) > self._card_v(sim, old["id"], old["up"]) else 1
        if kind in ("target", "interval_target"):
            return self._target(sim, opts, ok)
        if kind == "customize":
            cards = [j for j in ok if "n" in opts[j]]
            if cards and s["queue"][0].get("left", 1) > 0:
                return max(cards, key=lambda j: self._card_v(sim, sim._card_by_number(opts[j]["n"])["id"],
                                                             sim._card_by_number(opts[j]["n"])["up"]))
            return next((j for j in ok if opts[j].get("leave")), ok[0])
        if kind == "customize_pick":
            return ok[0] if ok[0] != len(opts) - 1 else ok[-1]     # 第一个定制项；只剩返回就返回
        if kind == "customize_pick_card":
            cards = [j for j in ok if opts[j].get("n") is not None]
            return max(cards, key=lambda j: self._card_v(sim, sim._card_by_number(opts[j]["n"])["id"],
                                                         sim._card_by_number(opts[j]["n"])["up"])) if cards else ok[-1]
        if kind == "passed":
            return 0                                            # 接受（与默认臂同；不耗重试改 RNG）
        if kind == "lost":
            return 0 if not opts[0].get("disabled") else 1
        if kind in ("citem_pick", "citem_upgrade"):
            return ok[0]
        return None

    # -- 行动日 ---------------------------------------------------------------
    def _day(self, sim, opts, ok):
        from gkagent.tasks.produce_ui import choose_action_kind   # import 复用体力门
        from GKMSPS.ps.sim import SELECTION_DAYS, MAIN_DAYS
        s = sim.s
        lessons = [j for j in ok if opts[j].get("do") == "lesson"]
        rest = [j for j in ok if opts[j].get("do") == "refresh"]
        afford = []
        for j in lessons:
            _, cost = self._lesson(sim, opts[j]["attr"])
            if s["stamina"] - cost >= LESSON_RESERVE:
                afford.append(j)
        days = SELECTION_DAYS if s["produce_id"] == "produce-007" else MAIN_DAYS
        nxt = days.get(s["step"] + 1, ())
        pre_exam = bool(nxt) and nxt[0].startswith("audition:")
        # 考试前一天不休息（考试前免费回复 beforeAuditionRefresh 兜底），除非体力见底
        has_rest = bool(rest) and (not pre_exam or s["stamina"] < REST_THRESHOLD)
        kind = choose_action_kind(stamina=s["stamina"], has_rest=has_rest,
                                  has_lesson=bool(afford), has_training=False,
                                  rest_threshold=REST_THRESHOLD, lesson_threshold=6)
        if kind == "rest" and rest:
            self.stats["rests"] += 1
            return rest[0]
        if afford:
            self.stats["lessons"] += 1
            return max(afford, key=lambda j: self._lesson(sim, opts[j]["attr"])[0])
        school = [j for j in ok if opts[j].get("do") == "school"]
        if school:                                              # 补短板（choose_training attr_choice=lowest 原则）
            self.stats["schools"] += 1
            return min(school, key=lambda j: s["params"][opts[j]["attr"]])
        act = next((j for j in ok if opts[j].get("do") == "activity"), None)
        if act is not None and s["stamina"] < 0.3 * s["max_stamina"]:
            self.stats["activities"] += 1
            return act
        # 差し入れ优先（P+80 + 饮料三选一 + 卡三选一，免费价值；真机 mid2 局均 3-4 饮料）
        pres = next((j for j in ok if opts[j].get("do") == "present"), None)
        if pres is not None:
            self.stats["presents"] += 1
            return pres
        for do in ("shop", "customize", "activity"):
            j = next((j for j in ok if opts[j].get("do") == do), None)
            if j is not None:
                self.stats["shops" if do == "shop" else "presents" if do == "present" else "activities"] += 1
                return j
        if rest:
            self.stats["rests"] += 1
            return rest[0]
        return None

    # -- 三选一 ---------------------------------------------------------------
    def _offer(self, sim, opts, ok):
        s = sim.s
        t = s["queue"][0]
        picks = [j for j in ok if "pick" in opts[j]]
        if t["what"] == "card":
            if not picks:
                return None
            j = max(picks, key=lambda j: self._card_v(sim, *t["cands"][opts[j]["pick"]]))
            self.stats["cards_gained"] += 1
            return j
        # 饮料三选一
        vals = {j: self._drink_v(sim, t["cands"][opts[j]["pick"]][0]) for j in picks}
        decline = next((j for j in ok if opts[j].get("decline")), None)
        best = max(picks, key=lambda j: vals[j]) if picks else None
        if decline is not None:                                 # 栏满：比手里最差的
            held = [self._drink_v(sim, k) for k in s["drinks"]]
            if best is not None and vals[best] > (min(held) if held else 0.0):
                self.stats["drinks_gained"] += 1
                if t["cands"][opts[best]["pick"]][0] in AOJIRU:
                    self.stats["aojiru_gained"] += 1
                return best
            self.stats["aojiru_declined"] += 1
            return decline
        if best is None:
            return None
        self.stats["drinks_gained"] += 1
        if t["cands"][opts[best]["pick"]][0] in AOJIRU:
            self.stats["aojiru_gained"] += 1
        return best

    def _discard(self, sim, opts, ok):
        s = sim.s
        t = s["queue"][0]
        held = [(j, self._drink_v(sim, k)) for j, k in enumerate(s["drinks"])]
        new_v = self._drink_v(sim, t["new"]) if t.get("new") else None
        if new_v is not None and held and new_v < min(v for _, v in held):
            self.stats["aojiru_declined"] += 1
            return next(j for j in ok if opts[j].get("decline"))
        j = min(held, key=lambda x: x[1])[0] if held else ok[0]
        self.stats["drinks_discarded"] += 1
        return j

    # -- 商店 / インターバル ----------------------------------------------------
    def _shop(self, sim, kind, opts, ok):
        s = sim.s
        shelf = s["shop"]["shelf"]
        buys = [j for j in ok if "buy" in opts[j] or "slot" in opts[j]]
        card_buys, drink_buys = [], []
        for j in buys:
            it = shelf[opts[j].get("buy", opts[j].get("slot"))]
            if it.get("bought") and it["what"] in ("card", "drink", "change"):
                continue
            if it["what"] == "card":
                card_buys.append((j, it))
            elif it["what"] == "drink" and len(s["drinks"]) < s["drink_limit"]:
                drink_buys.append((j, it))
        # 买卡：估值 ≥3 且买得起（v1.2：真机 mid2 牌组 16-22 张，积极扩组）
        afford_cards = [(j, it) for j, it in card_buys
                        if s["pp"] >= it["price"] and self._card_v(sim, it["id"], it["up"]) >= 3.0]
        if afford_cards:
            j, it = max(afford_cards, key=lambda x: self._card_v(sim, x[1]["id"], x[1]["up"]) - 0.02 * x[1]["price"])
            self.stats["buys"] += 1
            self.stats["cards_gained"] += 1
            return j
        afford_drinks = [(j, it) for j, it in drink_buys
                         if s["pp"] >= it["price"] and self._drink_v(sim, it["id"]) >= 3.0]
        if afford_drinks:
            j, it = max(afford_drinks, key=lambda x: self._drink_v(sim, x[1]["id"]))
            self.stats["buys"] += 1
            self.stats["drinks_gained"] += 1
            if it["id"] in AOJIRU:
                self.stats["aojiru_gained"] += 1
            return j
        # 删除服务：删最弱起始牌（v1.2：真机牌组质量 > 数量；N 卡稀释抽牌）
        de = next((j for j in ok if opts[j].get("service") == "delete"), None)
        if de is not None and s["pp"] >= opts[de].get("price", 100):
            deck = self._deck_cards(sim)
            if deck:
                weakest = min(deck, key=lambda c: self._card_v(sim, c["id"], c["up"]))
                if self._card_v(sim, weakest["id"], weakest["up"]) < 3.0:
                    self.stats["buys"] += 1
                    return de
        # 强化服务：买得起且留 50P 余量（shop 的 service 选项 / interval 的 upgrade 货架位）
        up, price = None, 100
        for j in ok:
            o = opts[j]
            if o.get("service") == "upgrade":
                up, price = j, int(o.get("price") or 100)
                break
            if "slot" in o and shelf[o["slot"]]["what"] == "upgrade":
                up, price = j, int(shelf[o["slot"]]["price"])
                break
        if up is not None:
            ups = [c for c in self._deck_cards(sim) if sim._upgradable(c)]
            if ups and s["pp"] >= price:
                self.stats["upgrades"] += 1
                return up
        leave = next((j for j in ok if opts[j].get("leave")), None)
        return leave if leave is not None else None

    # -- 强化/删除/换卡目标 -----------------------------------------------------
    def _target(self, sim, opts, ok):
        t = sim.s["queue"][0]
        p = t.get("purpose")
        cards = [j for j in ok if opts[j].get("n") is not None]
        if not cards:
            return ok[-1] if ok else None
        def cv(j):
            c = sim._card_by_number(opts[j]["n"])
            return self._card_v(sim, c["id"], c["up"])
        if p in ("upgrade", "shop_upgrade", "customize", "duplicate"):
            return max(cards, key=cv)
        if p in ("delete", "shop_delete"):
            from GKMSPS.ps.data import name
            trouble = [j for j in cards
                       if name(sim.d.card(sim._card_by_number(opts[j]["n"])["id"]).get("category"))
                       == "PRODUCE_CARD_CATEGORY_TROUBLE"]
            if trouble:
                return trouble[0]
            best = min(cards, key=cv)
            return best if cv(best) < 2.0 else next((j for j in ok if opts[j].get("n") is None), best)
        if p == "change":
            return min(cards, key=cv)
        return max(cards, key=cv)


# ---------------------------------------------------------------- 考试段 plug（r14 适配器）
def play_exam(sim, algo, stats: dict, aojiru_mode: str = "none") -> None:
    """r14 真实投稿适配器打完整场考试；aojiru_mode="drink" 时强制首口喝青汁（消融臂）。"""
    from uinet import uiobs
    t = sim.exam_task()
    ctx = SimpleNamespace(loadout=t["loadout"], meta=None, budget=5.0, obs=None, rng=random.Random(0))
    algo.begin(ctx)
    guard = 0
    drank_aojiru = False
    while sim.exam is not None and not sim.exam.finished:
        guard += 1
        if guard > 4000:
            stats["exam_guard_break"] = stats.get("exam_guard_break", 0) + 1
            break
        sess = sim.exam
        legal = [tuple(a) for a in sess.legal_actions()]
        if not legal:
            break
        if len(legal) == 1:
            sim.act({"exam": list(legal[0])})
            continue
        if aojiru_mode == "drink" and not drank_aojiru:
            drinks = list(getattr(sess, "drinks", []) or [])
            hit = next((a for a in legal if a[0] == "drink" and 0 <= a[1] < len(drinks)
                        and drinks[a[1]] in AOJIRU), None)
            if hit is not None:
                sim.act({"exam": list(hit)})
                drank_aojiru = True
                stats["aojiru_drunk"] = stats.get("aojiru_drunk", 0) + 1
                continue
        obs = uiobs.from_session(sess, {})
        ctx.obs = obs
        d = algo.decide(ctx)
        if d.meta.get("error"):
            stats["exam_errors"] = stats.get("exam_errors", 0) + 1
        if "退回" in str(d.meta.get("why", "")):
            stats["exam_fallbacks"] = stats.get("exam_fallbacks", 0) + 1
        act = tuple(d.action)
        if act not in {tuple(x) for x in legal}:
            act = legal[0]
            stats["exam_illegal_fallback"] = stats.get("exam_illegal_fallback", 0) + 1
        if act[0] == "drink":
            stats["drinks_drunk_exam"] = stats.get("drinks_drunk_exam", 0) + 1
        sim.act({"exam": list(act)})


# ---------------------------------------------------------------- 完整局驱动
def _default_drive(sim, policy_seed: int, sel_assume: int) -> None:
    """cli.auto(sensible=True) 同口径镜像，唯一差别：選抜考试按 sel_assume 强制过关（两臂同值）。

    本戦考试仍走 greedy_exam_index（默认臂真实考试）。policy RNG 构造与 cli.auto 逐字一致，
    保证 sel_assume=0 时与 auto() 逐位同行为（除选抜 assume 外零差异）。
    """
    from GKMSPS.ps.cli import greedy_exam_index, sensible_choices
    from GKMSPS.ps.rng import Rng
    from GKMSPS.ps.sim import SELECTION
    pol = Rng(hashlib.sha256(b"GKMS-PS-policy" + str(policy_seed).encode()).digest())("policy")
    n = 0
    while not sim.s["done"] and n < 20000:
        dec = sim.decision()
        if dec is None:
            break
        opts = dec["options"]
        if dec["kind"] == "exam":
            if sel_assume > 0 and sim.s["produce_id"] == SELECTION:
                sim.exam_assume(sel_assume, [sel_assume // 3] * 3)
                n += 1
                continue
            i = greedy_exam_index(sim, opts)
        elif dec["kind"] == "lost":
            i = 0 if not opts[0].get("disabled") else 1
        elif dec["kind"] == "passed":
            i = 0
        else:
            ok = [j for j, o in enumerate(opts) if not o.get("disabled")]
            ok = sensible_choices(sim, dec, opts, ok, pol)
            if dec["kind"] in ("shop", "customize", "interval") and pol.uniform(3) == 0:
                ok = [j for j in ok if opts[j].get("leave")] or ok
            i = ok[pol.uniform(len(ok))]
        sim.act(i)
        n += 1


def run_arm(formation: dict, root: bytes, arm: str, r14mod, values: Values,
            aojiru_mode: str = "avoid", policy_seed: int = 0, sel_assume: int = 0) -> dict:
    from GKMSPS.ps.sim import Sim
    from GKMSPS.ps.cli import auto
    hon_root = hashlib.sha256(root + b":hon").digest()
    exams: list[dict] = []
    hon_final: list[dict] = []
    stats: dict = {}
    t0 = time.perf_counter()

    def capture_exams(sim):
        for stage, rec in sim.s["auditions"].items():
            if stage.endswith("_lost"):
                continue
            exams.append({"produce": sim.s["produce_id"], "stage": stage, "seed": rec.get("seed"),
                          "score": rec.get("score"), "parts": rec.get("parts"), "rank": rec.get("rank")})

    if arm == "default":
        sel = Sim(formation, timestamp_ms=0, root=root)
        if sel_assume > 0:
            _default_drive(sel, policy_seed, sel_assume)
        else:
            auto(sel, policy_seed, engine=False, sensible=True)
        capture_exams(sel)
        hon = None
        if (sel.s.get("result") or {}).get("outcome") == "selection_memory":
            hon = Sim.honsen(sel.s["result"]["selection_memory"], timestamp_ms=1, root=hon_root)
            auto(hon, policy_seed, engine=False, sensible=True)
            capture_exams(hon)
    else:
        algo = r14mod.EiR14Algo()
        pol = PlugProduce(values, aojiru_mode)
        stats = pol.stats
        engine_exam = arm == "plug-engine"      # 参考臂：我们培育 + 引擎 beam 考试（M10 oracle 在环）
        exam_loadouts: list[dict] = []

        def drive(sim):
            n = 0
            while not sim.s["done"] and n < 20000:
                dec = sim.decision()
                if dec is None:
                    break
                if dec["kind"] == "exam":
                    t = sim.exam_task()
                    exam_loadouts.append({"produce": sim.s["produce_id"], "stage": t["stage"],
                                          "loadout": t["loadout"], "seed": t["seed"]})
                    if sim.s["produce_id"] == "produce-008" and t["stage"] == "final":
                        hon_final.append({"loadout": t["loadout"], "seed": t["seed"]})
                    if sel_assume > 0 and sim.s["produce_id"] == "produce-007":
                        sim.exam_assume(sel_assume, [sel_assume // 3] * 3)
                    elif engine_exam:
                        sim.exam_auto(budget=1.0)
                    else:
                        play_exam(sim, algo, stats, aojiru_mode="none")
                else:
                    sim.act(pol.pick(sim, dec))
                n += 1
            return n

        sel = Sim(formation, timestamp_ms=0, root=root)
        drive(sel)
        capture_exams(sel)
        hon = None
        if (sel.s.get("result") or {}).get("outcome") == "selection_memory":
            hon = Sim.honsen(sel.s["result"]["selection_memory"], timestamp_ms=1, root=hon_root)
            drive(hon)
            capture_exams(hon)
        out_extra = {"exam_loadouts": exam_loadouts}

    out = {"arm": arm, "root": root.hex(), "elapsed_s": round(time.perf_counter() - t0, 2),
           "sel_assume": sel_assume, "stats": stats, "exams": exams,
           "sel": _summarize(sel), "hon": _summarize(hon) if hon is not None else None}
    if hon_final:
        out["hon_final_loadout"] = hon_final[-1]      # 真实终试 loadout+seed（青汁消融配对用）
    return out


def _summarize(sim):
    if sim is None:
        return None
    s = sim.s
    res = s.get("result") or {}
    aud = {}
    for stage, rec in s["auditions"].items():
        if stage.endswith("_lost"):
            continue
        aud[stage] = {k: rec.get(k) for k in ("score", "rank", "parts", "param_gain", "star_gain", "pp_gain")}
    return {"outcome": res.get("outcome"), "rating": res.get("rating"), "grade": res.get("grade"),
            "round1_point": res.get("round1_point"), "round2": res.get("round2"),
            "params": dict(s["params"]), "params_start": dict((s.get("at_start") or {}).get("params") or {}),
            "star": s["star"], "star_permil": s["star_permil"], "max_stamina": s["max_stamina"],
            "auditions": aud, "deck_size": len(sim._deck()), "drinks_left": list(s["drinks"]),
            "log_gain": [x["text"] for x in s["log"] if x.get("kind") == "gain"],
            "actions": len(s["actions"])}


# ---------------------------------------------------------------- 分段归因
_GAIN_RE = re.compile(r"^(Vo|Da|Vi)\+(\d+) (Vo|Da|Vi)\+(\d+)$")


def attribute(run: dict) -> dict:
    """课程分/考试分/饮料贡献拆解（失分归因方法论承 engine-gap：按来源拆参数增量 + rating 项）。"""
    out = {}
    for phase in ("sel", "hon"):
        ph = run.get(phase)
        if not ph:
            continue
        lesson = {a: 0 for a in ATTRS}
        for text in ph.get("log_gain") or ():
            m = _GAIN_RE.match(text)
            if m:
                inv = {v: k for k, v in LABEL.items()}
                lesson[inv[m.group(1)]] += int(m.group(2))
                lesson[inv[m.group(3)]] += int(m.group(4))
        reward = {a: 0 for a in ATTRS}
        for rec in (ph.get("auditions") or {}).values():
            for i, a in enumerate(ATTRS):
                reward[a] += int((rec.get("param_gain") or [0, 0, 0])[i])
        start, end = ph.get("params_start") or {}, ph.get("params") or {}
        total = {a: int(end.get(a, 0)) - int(start.get(a, 0)) for a in ATTRS}
        other = {a: total[a] - lesson[a] - reward[a] for a in ATTRS}
        out[phase] = {"param_gain_total": total, "lesson_param": lesson, "exam_reward_param": reward,
                      "school_event_other_param": other,
                      "exam_scores": {k: v.get("score") for k, v in (ph.get("auditions") or {}).items()},
                      "star_end": ph.get("star")}
    hon = run.get("hon")
    if hon and hon.get("rating") is not None:
        from GakumasCLI.produce import produce_effects as pe
        import math
        params = [hon["params"][a] for a in ATTRS]
        stats = sum(min(3200, max(0, x)) for x in params)
        r1 = math.floor(pe._piecewise(math.floor(int(hon.get("round1_point") or 0) / 1.2), pe.HIF_ROUND1))
        r2 = math.floor(pe._piecewise(int(hon.get("round2") or 0), pe.HIF_ROUND2))
        param_term = math.floor(stats * 2)
        out["rating_terms"] = {"param_term": param_term, "star_term": hon["rating"] - param_term - r1 - r2 + 2000,
                               "round1_term": r1, "round2_term": r2, "offset": -2000, "rating": hon["rating"]}
    st = run.get("stats") or {}
    out["drinks"] = {"gained": st.get("drinks_gained", 0), "aojiru_gained": st.get("aojiru_gained", 0),
                     "discarded": st.get("drinks_discarded", 0), "drunk_exam": st.get("drinks_drunk_exam", 0)}
    return out


# ---------------------------------------------------------------- 统计
def boot_ci(x: np.ndarray, n_boot: int = 10000, seed: int = 7) -> dict:
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, x.size, size=(n_boot, x.size))].mean(axis=1)
    return {"mean": float(x.mean()), "lo": float(np.percentile(means, 2.5)),
            "hi": float(np.percentile(means, 97.5)), "n": int(x.size),
            "median": float(np.median(x)), "std": float(x.std(ddof=1)) if x.size > 1 else 0.0}


def paired_stats(plug: list[dict], default: list[dict]) -> dict:
    def metric(run, key):
        hon = run.get("hon") or {}
        if key == "round2":
            return float(hon.get("round2") or 0)
        if key == "rating":
            return float(hon.get("rating") or 0)
        if key == "sel_final":
            return float(((run.get("sel") or {}).get("auditions") or {}).get("final", {}).get("score") or 0)
        if key == "params_total":
            return float(sum((hon.get("params") or {}).values()))
        if key == "hon_mid1":
            return float((hon.get("auditions") or {}).get("mid1", {}).get("score") or 0)
        return 0.0

    out = {}
    for key in ("round2", "rating", "sel_final", "hon_mid1", "params_total"):
        p = np.array([metric(r, key) for r in plug])
        d = np.array([metric(r, key) for r in default])
        diff = p - d
        out[key] = {"plug": boot_ci(p), "default": boot_ci(d), "paired_diff": boot_ci(diff),
                    "wins_plug": int((diff > 0).sum()), "wins_default": int((diff < 0).sum()),
                    "ties": int((diff == 0).sum())}
    out["completed"] = {"plug": sum(1 for r in plug if (r.get("hon") or {}).get("rating") is not None),
                        "default": sum(1 for r in default if (r.get("hon") or {}).get("rating") is not None)}
    return out


# ---------------------------------------------------------------- 青汁消融（考试级注入配对）
def aojiru_ablation(cases: list[dict], r14mod, n_boot: int = 10000) -> dict:
    from GKMSPS.ps import exam as X
    rows = []
    for c in cases:
        lo, seed = c["loadout"], int(c["seed"])
        algo = r14mod.EiR14Algo()
        # 不喝臂：r14 原样（从不主动喝）
        s0 = X.open_session(lo, seed)
        st0: dict = {}
        _play_session(s0, algo, st0, drink_aojiru=False)
        score0 = int(s0.observe()["score"])
        # 喝臂：loadout 注入青汁，强制首口喝
        lo2 = dict(lo)
        lo2["drink_ids"] = list(lo.get("drink_ids") or []) + ["pdrink_00-3-005"]
        s1 = X.open_session(lo2, seed)
        st1: dict = {}
        _play_session(s1, algo, st1, drink_aojiru=True)
        score1 = int(s1.observe()["score"])
        rows.append({"seed": seed, "no_aojiru": score0, "aojiru": score1, "diff": score1 - score0,
                     "drunk": st1.get("aojiru_drunk", 0)})
    diff = np.array([r["diff"] for r in rows], dtype=np.float64)
    return {"n": len(rows), "paired_diff": boot_ci(diff, n_boot),
            "no_aojiru": boot_ci(np.array([r["no_aojiru"] for r in rows], dtype=np.float64), n_boot),
            "aojiru": boot_ci(np.array([r["aojiru"] for r in rows], dtype=np.float64), n_boot),
            "std_diff": float(diff.std(ddof=1)) if diff.size > 1 else 0.0,
            "drunk_count": sum(r["drunk"] for r in rows), "rows": rows}


def _play_session(sess, algo, stats: dict, drink_aojiru: bool) -> None:
    from uinet import uiobs
    ctx = SimpleNamespace(loadout={}, meta=None, budget=5.0, obs=None, rng=random.Random(0))
    algo.begin(ctx)
    guard = 0
    drank = False
    while not sess.finished:
        guard += 1
        if guard > 4000:
            break
        legal = [tuple(a) for a in sess.legal_actions()]
        if not legal:
            break
        if len(legal) == 1:
            sess.step(legal[0], observe=False)
            continue
        if drink_aojiru and not drank:
            drinks = list(getattr(sess, "drinks", []) or [])
            hit = next((a for a in legal if a[0] == "drink" and 0 <= a[1] < len(drinks)
                        and drinks[a[1]] in AOJIRU), None)
            if hit is not None:
                sess.step(hit, observe=False)
                drank = True
                stats["aojiru_drunk"] = stats.get("aojiru_drunk", 0) + 1
                continue
        ctx.obs = uiobs.from_session(sess, {})
        d = algo.decide(ctx)
        act = tuple(d.action)
        if act not in {tuple(x) for x in legal}:
            act = legal[0]
        sess.step(act if act[0] != "select" else ("select", list(act[1])), observe=False)


# ---------------------------------------------------------------- 内存自节流
def mem_free_gb() -> float:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / (1024 ** 3)


def throttle(every: int, k: int) -> None:
    if k % every:
        return
    while mem_free_gb() < 0.9:
        print(f"free {mem_free_gb():.2f}GB < 0.9GB → sleep 60s 自节流", flush=True)
        time.sleep(60)


# ---------------------------------------------------------------- main
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--ablation", type=int, default=0)
    ap.add_argument("--sel-assume", type=int, default=0,
                    help="選抜考试两臂同值强制过关分（0=关；本戦真实考试不受影响）。選抜 NPC 墙 "
                         "mid2=49806/final=136347 远超两臂培育上限，真实選抜几乎必 lost（pilot5 全零）；"
                         "probe9 先例用 assume 强制过关以评估本戦全流程。")
    ap.add_argument("--resume", action="store_true",
                    help="复用 --games-out 已完成配对局增量跑（崩溃续跑；按 i 去重）")
    ap.add_argument("--seed-tag", default="gkmsps-plug-v1")
    ap.add_argument("--formation", type=Path, default=WHEEL / "GKMSPS" / "examples" / "formation.json")
    ap.add_argument("--drinks", type=Path, default=ROOT / "data" / "knowledge" / "drinks.json")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "_gkmsps_plug_report.json")
    ap.add_argument("--games-out", type=Path, default=ROOT / "out" / "_gkmsps_plug_games.jsonl")
    a = ap.parse_args()

    ps_data = ensure_ps_data()
    r14mod = load_r14()
    values = Values(r14mod, a.drinks)
    formation = json.loads(a.formation.read_text(encoding="utf-8"))
    n = 1 if a.smoke else a.n
    print(f"ps_data={ps_data['source']} formation={a.formation.name} n={n} tag={a.seed_tag}", flush=True)

    plug_runs, default_runs = [], []
    done_i: set = set()
    if a.resume and a.games_out.is_file():
        with open(a.games_out, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001 - 损坏行跳过
                    continue
                if "default" in rec and "plug" in rec and rec["plug"].get("i") is not None:
                    default_runs.append(rec["default"])
                    plug_runs.append(rec["plug"])
                    done_i.add(int(rec["plug"]["i"]))
        print(f"resume: 复用 {len(done_i)} 对已完成局（{a.games_out.name}）", flush=True)
    if a.sel_assume > 0:
        print(f"⚠ sel-assume={a.sel_assume}：選抜考试两臂同值强制过关（本戦真实）；選抜考试段归因不可比", flush=True)
    t0 = time.perf_counter()
    with open(a.games_out, "a" if a.resume else "w", encoding="utf-8") as fh:
        for i in range(n):
            if i in done_i:
                continue
            throttle(5, i)
            root = hashlib.sha256(f"{a.seed_tag}:{i}".encode()).digest()
            dp = run_arm(formation, root, "default", r14mod, values, sel_assume=a.sel_assume)
            pp = run_arm(formation, root, "plug", r14mod, values, aojiru_mode="avoid", sel_assume=a.sel_assume)
            dp["i"], pp["i"] = i, i
            dp["attr"], pp["attr"] = attribute(dp), attribute(pp)
            default_runs.append(dp)
            plug_runs.append(pp)
            fh.write(json.dumps({"default": dp, "plug": pp}, ensure_ascii=False) + "\n")
            fh.flush()
            hr = (pp.get("hon") or {}).get("rating")
            hd = (dp.get("hon") or {}).get("rating")
            print(f"{i + 1}/{n} plug rating={hr} round2={(pp.get('hon') or {}).get('round2')} "
                  f"vs default rating={hd} round2={(dp.get('hon') or {}).get('round2')} "
                  f"({time.perf_counter() - t0:.0f}s, plug {pp['elapsed_s']}s/def {dp['elapsed_s']}s)", flush=True)

    report = {"n": len(plug_runs), "n_target": n, "seed_tag": a.seed_tag, "formation": str(a.formation),
              "sel_assume": a.sel_assume, "ps_data": ps_data,
              "paired": paired_stats(plug_runs, default_runs),
              "plug_mean_elapsed_s": float(np.mean([r["elapsed_s"] for r in plug_runs])),
              "default_mean_elapsed_s": float(np.mean([r["elapsed_s"] for r in default_runs])),
              "elapsed_s": round(time.perf_counter() - t0, 1)}
    # 分段归因汇总（均值）
    agg = {}
    for arm, runs in (("plug", plug_runs), ("default", default_runs)):
        keys = ["lesson_param", "exam_reward_param", "school_event_other_param", "param_gain_total"]
        sel_sum = {k: {a: float(np.mean([r["attr"]["sel"][k][a] for r in runs if "sel" in r["attr"]]))
                       for a in ATTRS} for k in keys}
        hon_runs = [r for r in runs if "hon" in r["attr"]]
        hon_sum = {k: {a: float(np.mean([r["attr"]["hon"][k][a] for r in hon_runs])) for a in ATTRS}
                   for k in keys} if hon_runs else {}
        rt = [r["attr"]["rating_terms"] for r in runs if "rating_terms" in r["attr"]]
        agg[arm] = {"sel_param_mean": sel_sum, "hon_param_mean": hon_sum,
                    "rating_terms_mean": {k: float(np.mean([x[k] for x in rt])) for k in
                                          ("param_term", "star_term", "round1_term", "round2_term", "rating")} if rt else {},
                    "drinks_mean": {k: float(np.mean([r["attr"]["drinks"][k] for r in runs]))
                                    for k in ("gained", "aojiru_gained", "discarded", "drunk_exam")},
                    "stats_mean": {k: float(np.mean([r["stats"].get(k, 0) for r in runs]))
                                   for k in ("lessons", "rests", "schools", "activities", "presents",
                                             "cards_gained", "buys", "upgrades", "fallbacks",
                                             "exam_errors", "exam_fallbacks")} if runs and runs[0]["stats"] else {}}
    report["attribution_mean"] = agg

    if a.ablation > 0:
        cases = []
        for r in plug_runs:
            fl = r.get("hon_final_loadout")
            if fl and fl.get("seed") and len(cases) < a.ablation:
                cases.append(fl)
        print(f"青汁消融：{len(cases)} 场本戦终试配对", flush=True)
        report["aojiru_ablation"] = aojiru_ablation(cases, r14mod)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    slim = {k: v for k, v in report.items() if k not in ("aojiru_ablation",)}
    if "aojiru_ablation" in report:
        slim["aojiru_ablation"] = {k: v for k, v in report["aojiru_ablation"].items() if k != "rows"}
    print(json.dumps(slim, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())