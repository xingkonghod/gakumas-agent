# 交接清单：补什么 · 做什么（GDE / gakumas-agent）

> **这份文档是行动型交接**：`HANDOVER.md` 讲"发生过什么"，本文讲**接下来还缺什么、按什么顺序做、怎么验收**。
> **总顺序以 [WORKPLAN.md](WORKPLAN.md) 为准**（离线 A→B→C→D 全部做完 → 真机 E：T3→T1→T2 → gkbench F）。
> 新会话第一句话：
> 「读 `docs/INDEX.md` → `docs/WORKPLAN.md`，然后照 `docs/HANDOVER_NEXT.md` §2 跑四条基线，
> 再从 WORKPLAN 阶段 A 的下一项（A3）开始。」
>
> 维护方式：完成一个任务 → 把对应状态改成 ✅（A 阶段在 WORKPLAN、T1–T8 在本文 §4）并在 §8 记一条；
> 本文档是 T1–T8 的"下一件事"真源，WORKPLAN 是总序列真源。

---

## 0. 十秒版

```
已完成：采集链路 / 牌序破解 / 完全信息搜索数据链路 / 生产接线接口（233e9d7）
         决策可观测性 + 出牌引擎接线 + T1 流程修复 + T3 实时接线代码（a9537b0/304d393）
         真机第一次完整跑完一局：期中 914/第3 → 最终 C/4242；20:55–22:20 七次短跑修掉 7 类卡点
         根因已定：课程"读不到价值 → 搜索建议 SKIP → 规则执行跳过"（C/4242 主因）
         已落地用户规则：**只有所有牌都付不起（真没体力）才允许 SKIP**（4b07fa7/8a2af2b/b231b3f）
         已落地用户规则：**bot 不许回退 rules**——搜索引擎失败 → [engine][BLOCKED] 中止本局，
         绝不静默改用规则；入口默认 expectimax（见 F#40，本次提交）
         上真机前模拟器整局 A/B 已绿：76 局 0 blocked / 0 异常 / C+率 100%（sim_engine_ab.py）
         真机防卡死：auto_produce --max-minutes（默认 30）超时主动停局，不再无限空转
         2026-11-22 A1：OCR 换官方 PP-OCRv6 多语言模型（Apache-2.0）——日文剧情/选项完整可读，
         下载脚本/配置/probe/测试齐全（见 HANDOVER 二·补十四）
         2026-11-22 A2：F#42 课程硬打必须得分——修掉课程 HUD 语义（右上=属性值、圆环=还差分）
         与「游戏默认每回合 1 张牌」两个模型错误；硬打先打正分牌（HANDOVER 二·补十五 / FAILURES #42）
         全量 pytest 934 passed / 1 skipped（935 收集 / 66 文件）
未完成：① 还没跑出一局"不再乱跳 + 分数达标"的整局（上局 C/4242，期中不合格）
        ② 没做过同卡组真机 A/B（三引擎谁强不知道）
        ③ 采集进程 ↔ 决策进程**代码已接**，但真机跑局时采集没开 → 全知 0 锁定，差实战验收
        ④ 策略强度：V_leaf 是瓶颈（2026-11-22 已定位：档位效用平手项 + beam 采样分支可 +20，
           但仍比回合内 expectimax 低 22%；下一步受控 policy-evaluation / rollout 监督 v_leaf）；机制建模缺 P 道具/回忆/附魔/选牌/减益
        ⑤ 分数/费用 OCR 仍需用新截图校准（已加回退原因日志：complete/nodes/ms、CardSpec 失配）
当前最高优先：**阶段 A 离线收尾**（A2 ✅ → **A3 F#43 结果页空转** → A4 离线回放素材 →
A5 T3 离线预演）→ 阶段 B/C/D → 真机 T3→T1→T2 → gkbench（总计划见 WORKPLAN.md）
```

> **新会话先读 [WORKPLAN.md](WORKPLAN.md)**：总顺序 = **离线全部做完 → 真机（T3→T1→T2）→ 去 gkbench 比算法**。
> WORKPLAN 里含完整任务表（A1 OCR ✅ / A2 F#42 ✅ / A3 F#43 / B T4·T5 / C 可靠性 / D 数据 / E 真机 / F gkbench / G 收尾）
> 和「已完成不要重做」清单。

> **2026-11-21 用户硬规矩（不许破）**：SKIP 只在"所有牌都付不起"时允许；读不到分数/费用不是跳过理由，
> 那是 OCR/卡表 bug，去修它，不许用 SKIP 补偿。**bot 不许回退 rules**：搜索/规划/神经网络失败 =
> 记 `[engine][BLOCKED]` 并中止本局、去修 root cause，不许静默改用规则引擎（见 §4 硬约束 5/6）。
> 真机整局必须带 `--ignore-user`（人别碰键鼠/别最小化窗口）。

当前最好成绩对照（都是"初/REGULAR-PRO"路线，口径见 [RUNS.md L229](RUNS.md#L229)）：

| 谁 | 评价 | 说明 |
|---|---:|---|
| bot（2026-11-21 晚接管局） | **C / 4242** | 期中 914/第3 → 培育终了；原因：课程大面积跳过 + 考试搜索退回规则 + 全知未启用；修复见 [HANDOVER 二·补七](HANDOVER.md#L269) |
| bot（2026-11-15 旧版） | **C+ / 5992** | 11.8 分钟，差 B 门槛 8 点；之后未再跑完全局 |
| 用户手动 | **A / 10237** | 20.2 分钟，True End 3/3；这是追赶目标 |
| 用户手动（采集局） | B / 7404 | 11-20 一局两场考试，全部考试数据已采到 |

> 对手 hiro 的 A / 10 428 是不同账号/卡组/模式，**不能直接和 5992 比**；要可比必须走 T2 的同环境 A/B。

---

## 1. 已完成、不要再做（先读这一节，避免重做）

| 能力 | 产物 | 验证 / 数字 |
|---|---|---|
| MITM 采集链路 | `C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl` | 四场考试全采到；见 [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) |
| 考试牌堆重建 | `scripts/reconstruct_deck.py` → `deck_snapshots.json` | 期中 18 / 期末 26 张逐张吻合 |
| 洗牌模型破解 | [exam_shuffle.py](../src/gkagent/sim/exam_shuffle.py) | 4/4 场整段复现；3/3 重洗样本 |
| 牌序全知数据链路 | [exam_oracle.py](../src/gkagent/sim/exam_oracle.py) + [exam_plan.py](../src/gkagent/sim/exam_plan.py) | 每回合预测手牌 vs 实机逐张核对 |
| 采集数据 → setup | `scripts/build_exam_setup.py` → `out/exam_setup.json` | 4/4 场、86/86 张；重洗段 24/24 |
| 完全信息搜索（搜索侧） | `ExpectState.known_draw` / `discard_order` / `reshuffle` 钩子 | 17 条测试；重洗后段可确定分支 |
| 生产接线接口 | `LessonPolicy(draw_plan=…)` + `auto_produce --exam-setup` | [verify_exam_wiring.py](../scripts/verify_exam_wiring.py)：36/36 手牌、3/3 重洗、29/29 known_draw |
| 跨回合 beam 选项 | `lesson.engine="beam"`（`beam_width=4` / `beam_deadline_ms=250`） | 7 条测试；无 known_draw 自动退回回合内搜索 |
| 决策可观测性 + 引擎接线 | 日志首行 `[engine]`、每步 `| eng=…` / `fallback=…`；真机引擎由 `--engine` > `produce.engine` 决定 | 4 条测试；能回答"到底是不是 rule 在打、为什么退回"；2026-11-21 深夜起搜索引擎**禁止回退 rules**（失败→`[engine][BLOCKED]`，见 F#40） |
| T3 实时接线（代码） | `build_exam_setup.py --current` + `ExamPlanSelector` + `auto_produce` 运行时重载 | 4 条 selector 测试；已用采集局离线验证第 2 回合锁定正确 config_turns |
| 模拟器 + 评价公式 | [hajime_eval.py](../src/gkagent/sim/hajime_eval.py)、[hajime_data.py](../src/gkagent/sim/hajime_data.py) | 4 局实机逐分回归（9973/10428/8790/12903） |
| 主数据库 | `data/hiro/vendor/.../catalog.sqlite` | 286 表 / 163,974 行 |
| A1 日文 OCR 模型 | `configs/ocr_jp.example.yaml` + `scripts/download_ocr_models.py` | 真图 4 条 + 配置 17 条；见 HANDOVER 二·补十四 |
| A2 课程硬打必须得分（F#42） | [vision/lesson.py](../src/gkagent/vision/lesson.py) 课程 HUD 换算 + [policy/lesson.py](../src/gkagent/policy/lesson.py) 每回合 1 张/硬打保分 | `tests/test_lesson_play_f42.py` 真图回放 3 条 + HUD 换算 4 条 + flat-tie 硬打 1 条；见 HANDOVER 二·补十五 |

**改动以上任何部分的规矩**：先跑 §2 四条基线命令；数值/状态语义改动必须补单测并更新对应文档（`EXPECTIMAX.md` / `MASTER_DATA.md` / `HANDOVER.md`）。

---

## 2. 开工自检（每次新会话，5–10 分钟，四条命令）

```powershell
cd D:\Games\gakumas-agent
# ① 洗牌重放：应为 4/4 场（期中 18/18、期末 26/26、PRO 期中 15/15、PRO 期末 27/27）+ 3/3 重洗样本
.venv\Scripts\python.exe scripts\verify_shuffle.py

# ② 全量测试：应为 934 passed, 1 skipped（935 条收集 / 66 个测试文件；含 A1 日文 OCR 21 条 + A2 F#42 8 条）
.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=data/pytest-tmp-<日期>

# ③ 采集数据 → 考试牌序：应为 4/4 场、初始段 86/86 张、重洗段 24/24 张
.venv\Scripts\python.exe scripts\build_exam_setup.py

# ④ 生产接线端到端：应为手牌 36/36 回合、重洗 3/3、known_draw 29/29、策略链路 beam 出牌 28 次
.venv\Scripts\python.exe scripts\verify_exam_wiring.py
```

**环境前提**：

- 采集文件在 `C:\GakumasLocal\GakumasUnlock\out\`（`traffic.jsonl` / `deck_snapshots.json` / `exam_truth.json`）。**不在就只跑 ①②**，并把 ③④ 标记为"待采集"。
- **日文 OCR 模型**：`.venv\Scripts\python.exe scripts\download_ocr_models.py --check` 应显示"全部就绪"；
  缺了就重跑（不带 `--check`）下载。日文模型缺失时 `OcrEngine` 会**直接报错**（不静默回退），
  配置/模型在 `data/models/ocr_jp/` + `configs/ocr_jp.yaml`（均 gitignore）。
- Windows + DMM 客户端；VPN 日本节点（TUN 或 7897 任一）；游戏窗口客户区 **540x960**（代码自动缩放，别改成 720x1280，会截崩，见 F#10）。
- `out/exam_setup.json` 已 gitignore，**每次采集后要重建**。
- 基线不绿就先修基线，不要在新功能上叠 bug。

---

## 3. 补什么（差距清单，按影响排序）

| 编号 | 缺口 | 现状 / 证据 | 影响 | 对应任务 |
|---|---|---|---|---|
| G1 | **自动化完成度**：bot 没跑完整局 | 2026-11-21 晚已修 10 类真机卡点（点击双重缩放/难度坐标/自动编成确认框/外出事件/领卡坐标/考试浮层/网络重试弹窗/加载快速路径逃逸/无决策空转/暂停误判同屏卡死，见 [FAILURES #27-32](FAILURES.md#L6)），**还没整局真机验收** | 自动拿分的**前提**；没有它一切策略都只是离线数字 | T1 |
| G2 | **没有真机 A/B** | 三引擎（rules / expectimax / beam+全知）从没同卡组同账号跑过 | 不知道 search 值不值；无法向用户证明 | T2 |
| G3 | **采集↔决策未打通**（原 item④） | bot 读离线 `out/exam_setup.json`；换一局/换一场考试就对不上（`ExamDrawPlan` 会安全停用） | 全知搜索（known_draw/beam）**实战用不上**，只在离线核对里有效 | T3 |
| G4 | **策略强度**：V_leaf 是瓶颈 | [EXPECTIMAX.md](EXPECTIMAX.md)：真实牌组 beam 只 +3.0、构造抽牌牌组 +44.6；leaf 仅 6 特征 vs 官方 AI 50+；learned leaf 两次失败（[EXPECTIMAX L329-377](EXPECTIMAX.md#L262)） | 考试分（评价点的主要来源之一） | T4 |
| G5 | **机制建模缺口** | [OFFICIAL_AI_NOTES §3/§5](OFFICIAL_AI_NOTES.md#L330)：P 道具/回忆/附魔、选牌评估器、饮料、考试减益、考试内生成卡；回合内重洗（11-20 期末 T9）、同局多次重洗 RNG 快照未建模 | 模拟器与实战偏差 → 搜索决策偏 | T5 / T6 |
| G6 | **工程可靠性**：无互验/复盘 | 对照 hiro 三条原则（[HIRO_VIDEO_NOTES L32](HIRO_VIDEO_NOTES.md#L32)）：动作前预算下一帧、纯函数状态、自动复盘页——我们都没有 | 排障慢、回归靠人肉 | T7 |
| G7 | **情报跟踪** | hiro Windows 版进展、QQ 群 seed 口径都在变（[QQ_GROUP_NOTES](QQ_GROUP_NOTES.md#L59)） | 方向判断；低成本 | T8 |

**明确不需要补的**（ADR 已定，别浪费预算）：

- 不做日常/商店/启动/汉化（MaaGakumasu 已做，[PROJECT_PLAN ADR-001](PROJECT_PLAN.md#L180)）；
- 不替 MAA 抢输入；LLM 只做兜底、不做每步决策（[ADR-006](PROJECT_PLAN.md#L185)）；
- 不拷 `data/hiro/` 的 AGPL 代码。

---

## 4. 做什么（任务表：目标 → 步骤 → 验收 → 预算）

> 顺序建议：**T1 → T3 → T2 → T4 → T5/T6 → T7 → T8**。
> "预算"是按成本纪律估的**单次会话 token 量级**；做完一项就更新状态、开新会话（见 §8）。

> **本轮新增硬约束（2026-11-21 用户指定，违反即返工）**
> 1. **SKIP 只在"所有牌都付不起（真没体力）"时允许**；读不到分数/费用/搜索建议 SKIP 都不算理由。
> 2. "读不到" = OCR 或卡表 bug → 去修识别/卡表，不许用 SKIP/降级补偿。
> 3. 真机整局必须 `--ignore-user`（无人值守），人不要碰键鼠、不要最小化窗口。
> 4. 每步日志必须能回答"这手是谁决定的、为什么退回"（`eng=… fallback=…`）；新增决策引擎必须接这个口径。
> 5. **bot 不许回退 rules**（2026-11-21 追加）：搜索引擎/规划/神经网络失败时不许静默改用 rules。
>    状态没读全 → `wait` 等下一帧；搜索异常/结果失配 → `[engine][BLOCKED]` 中止本局，去修 OCR/卡表/参数。
> 6. bot 入口默认 `expectimax`；`--engine rules` 只用于 A/B 对照/离线复现，正常整局跑局不许用。
> 7. **一局必须有墙钟上限**：`auto_produce --max-minutes 30`（默认 30，0=关闭）。卡住时写
>    `episode-timeout` 主动停局并留日志，不许再出现"卡两个多小时还跑到 C"。

### T1（P0）无人值守跑完整局 🟡（流程卡点已修，差整局真机验收）
**目标**：bot 从主页起跑，一路到期末考试/结算，**不停机、不白给回合**，一局 ≤20 分钟。

**已完成（2026-11-21 晚，a9537b0 起）**
- 12 次真机短跑定位并修掉 10 类卡点（详见 [FAILURES #27-32](FAILURES.md#L6) + [TROUBLESHOOTING](TROUBLESHOOTING.md)）：
  点击坐标双重缩放、难度按钮坐标、自动编成确认框误判、外出/事件屏、领卡卡面中心、
  考试详情浮层（「得分+」/「仅限1次」）、通信错误弹窗重试、加载快速路径定时回看、
  无可用决策空转（连续 2 步强制 SKIP）、暂停帧计入同屏判死（暂停时 reset 同屏计数）。
- 出牌引擎接线 + 决策可观测性（见 T2 前置）：`[engine]`/`[training] … | eng=…` 日志能一眼看出
  这手是 expectimax 还是 rules 退回，以及退回原因（体力/回合/手牌读不到/搜索异常）。
- 新增回归测试：`tests/test_device_click_coords.py`、`tests/test_produce_ui.py` 增补。

**第二段（2026-11-21 22:00–22:20，4b07fa7/8a2af2b/b231b3f）**
- 7 次真机短跑，第一次**完整跑到结算**：期中 914/第 3 → 培育终了 → **最终 C/4242**（FAILURES #34-39）。
- 修掉：授课答题屏误判剧情（95 步循环）、领奖弹窗误判答题屏、课程快速路径吞「回合结束」确认框、
  用户操作时点击被拒→强制 SKIP（`--ignore-user`）、费用预览读歪（4 费记成 29 费）、
  **搜索 SKIP 被直接执行**（主因，已按用户规则全面禁止）。
- 现在课程/考试里 **SKIP 只在"所有牌都付不起"时发生**；四引擎（rules/expectimax/beam/uinet）统一拦截。

**第三段（2026-11-22 凌晨，采集+真机首次合体）**
- 采集链路通了（服务 18443/18444、token 刷新、C 盘副本）；4 次短跑 ep-t3-1..4 全部中途停。
- 已修：培育开场**日文剧情二选一**（布局识别选项气泡 + 补读中下部 OCR，`584f742`，FAILURES #41）。
- 待修（→ WORKPLAN A2/A3）：**#42 舞蹈课程连打 buff → 0 分 FAILED**（禁跳硬打必须保证得分）；
  **#43 结果页 result-tap 循环**。
- 群文件情报（论文/2B run/GKMSMAA AGPL）见 HANDOVER 二·补十二；**A1 OCR 换日文模型已完成**
  （2026-11-22，官方 PP-OCRv6 Apache-2.0，见 HANDOVER 二·补十四 / WORKPLAN A1）；
  **A2 F#42 已完成**（2026-11-22，课程 HUD 语义 + 每回合 1 张 + 硬打保分，见 HANDOVER 二·补十五 /
  WORKPLAN A2）；**#43 未修**。按 WORKPLAN 顺序先做离线阶段 A 剩余（**A3 F#43 → A4 回放素材 →
  A5 T3 离线预演**），再上真机重验 F#42/#43 与 T3。

**剩余（跑一局验收）**
1. **上真机前先跑模拟器整局 A/B（不碰游戏）**：
   `sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --out out\sim_engine_ab.json`
   → 验收：0 `RuleFallbackBlocked`、0 error、满局 C+ 率 100%、单局模拟耗时正常；
   2026-11-21 实测 76 局（3 组种子）全绿，见 [HANDOVER 二·补八](HANDOVER.md)。
2. 按 [LIVE_RUN.md](LIVE_RUN.md) §0 自检；起跑必须带 `--ignore-user`（人别碰键鼠/别最小化），
   并带墙钟上限（默认 30 分钟，卡住会写 `episode-timeout` 停局）：
   `auto_produce.py 300 ep-<名字> --skip-home --engine expectimax --ignore-user --max-minutes 30`。
3. 验收点：整局 **不再出现"还有牌却 SKIP"**，也**不再出现 `fallback=…退回规则`**（搜索引擎已禁止回退 rules）；
   若出现 `[engine][BLOCKED]`，按后面原因修 OCR/卡表，别把 rules 加回来兜底。
   期中/期末分数、评价、时长记进 `docs/RUNS.md`；若分数仍低，看日志 `| eng=… fallback=…` 与
   `[unknown-card]` 定位是 OCR 还是策略问题。
4. 完成一局后把记录写进 `docs/RUNS.md`，再决定是否上 T3（开采集）。

**改哪儿**：`scripts/auto_produce.py`、`src/gkagent/tasks/produce_ui.py`、`docs/FAILURES.md`、`docs/RUNS.md`

**验收（DoD）**
- `docs/RUNS.md` 新增一局记录：起止/步数/时长/是否完成/评价/卡点；
- 完成时：评价 ≥ C+（课题达标）、时长 ≤20 分钟；未完成时：明确写出卡在第几屏、复现步骤、截图路径；
- `pytest tests/ -q` 仍全绿（改了识别/UI 逻辑必须补测试）。

**预算**：1–2 小时真机 + 30–60k token。

### T3（P0，依赖 T1 的稳定起跑）采集进程 ↔ 决策进程实时打通（原 item④）🟡（代码已接，差真机考试验收）
**目标**：bot 进入考试的那一刻，自动从采集数据拿到**当前这一场**的 seed / 支援编成 / 牌堆 / 配置回合，建 `ExamDrawPlan`；每回合手牌核对通过，2–3 回合内锁定牌序。

**已完成（2026-11-21 晚，a9537b0 起）**
1. ✅ `scripts/build_exam_setup.py --current`：只读最新 `StepAuditionStart`（不依赖 EndExamBattle），
   牌堆用 `reconstruct_deck.build_snapshots()` 现场重放；`config_turns` 输出多个候选（默认 9/11/12）。
   `--allow-finished` 用于对已结束的采集做离线核对。
2. ✅ `ExamPlanSelector`（[exam_plan.py](../src/gkagent/sim/exam_plan.py)）：逐回合用实机手牌**收窄候选**，
   唯一剩下即锁定（第 1 回合可能因 isInitial 卡相同分不出，第 2–3 回合收敛；实测采集局第 2 回合锁定）；
   全部淘汰会重置重试（有上限），过期数据不会无限烧 CPU。
3. ✅ `reconstruct_deck.build_snapshots()` 抽成函数（运行时可调用，不复制逻辑）。
4. ✅ `auto_produce`：进入考试时按文件 mtime **运行时重载** `out/exam_setup.json`、新考试换新 selector、
   考试结束打 `[exam-plan] summary`（锁定回合/候选/核对回合数）。

**剩余（需要游戏+采集进程）**
1. 开采集（`一键采集启动.bat`）→ 起 bot 到考试 → **考试进行中**另开一个进程跑
   `build_exam_setup.py --current`（默认输出 `out/exam_setup.json`）→ bot 下一帧自动重载并开始核对；
2. 验收日志：`[exam-plan] 重载/挂上` + `[exam-plan] summary` 里 `locked_turn` 2–3、`verified == 实战回合数`；
3. 离线兜底验证（不依赖真机）：`build_exam_setup.py --current --allow-finished` 对一个已结束的采集
   生成候选，用 truth 逐回合喂 `ExamPlanSelector` 应能锁定正确 `config_turns`（2026-11-21 已实测 12）。

**改哪儿**：`scripts/build_exam_setup.py`、`scripts/auto_produce.py`、`scripts/reconstruct_deck.py`、`src/gkagent/sim/exam_plan.py`

**风险**：traffic.jsonl 写入缓冲/时序；deck 快照与考试开始时刻的对齐；`forceEndScore` 提前结束时 config_turns 仍按配置回合（见 [HANDOVER 二·补二](HANDOVER.md#L113)）。
**兜底**：对不上就自动停用（现有设计），**绝不能**用错牌序。

> 2026-11-22 情报补充（**已实现事前检测**：`exam_risk.py` + `rng_risk` 字段 + bot 跳过候选）：考试 RNG 还有恐慌/搜索排序/随机选取/生成卡/随机移动等入口（见
> [QQ_GROUP_NOTES](QQ_GROUP_NOTES.md) 凌晨条目），我们的 K 模型未覆盖。牌组含这些效果的考试
> **known_draw 只能用到第一个此类事件**；T3 验收时用"纯牌组"考试跑，或在建 setup 时前置标记不可验。

**验收（DoD）**：真机一局考试的每回合核对通过 + selector 单测（已加 4 条）+ 文档更新。
**预算**：60–100k token（代码已完成，剩真机验收 ~20k）。

### T2（P0，依赖 T3）三引擎真机 A/B ⬜
**目标**：同偶像、同卡组、同 seed（能同 seed 最好），各跑 rules / expectimax / beam+全知 一局，比考试分。

**前置（2026-11-21 已做）**：真机之前先跑**模拟器整局 A/B**（`scripts/sim_engine_ab.py`）——
训练+考试都注入真 `LessonPolicy`，16 局×3 引擎全绿：0 `RuleFallbackBlocked`、0 error、C+ 率 100%，
expectimax 与 rules 评价点差异在噪声内（P50 5063 vs 5049）。模拟器不覆盖 UI/OCR 卡屏，
所以真机 A/B 仍要做；但"引擎选牌导致掉分/卡死"这一层已先排掉。

**步骤**
1. 引擎开关（**已接线**）：真机 bot 读 `--engine` > `policy.json` 的 `produce.engine`；
   `lesson.engine` 只是 `LessonPolicy` 独立/单测默认（保持 rules，别只改它）。
   ```powershell
   auto_produce.py 300 ep-ab-rules   --engine rules
   auto_produce.py 300 ep-ab-exp     --engine expectimax
   auto_produce.py 300 ep-ab-beam    --engine beam --exam-setup out\exam_setup.json
   ```
2. 每局看日志首行 `[engine]` 和每步 `| eng=…`：确认搜索真的在出牌，退回率（`fallback=`）多少。
3. 每局跑完：`scripts/extract_exams.py` 记录期中/期末分数、名次、三维；记 `docs/RUNS.md`。
4. 注意：**beam 只在有 `known_draw` 且核对通过时才生效**（否则自动退回 expectimax）——所以 T3 必须先做，否则测不出 beam。
5. 结论写回 [EXPECTIMAX.md](EXPECTIMAX.md)（新增"真机 A/B"小节）。

**验收（DoD）**：三局成绩表（考试分 + 评价 + 时长 + `fallback=` 次数）+ 明确结论"哪个引擎值得默认"。
**预算**：3 局×20 分钟真机 + 30–50k token。

### T4（P1）策略强度：V_leaf + beam 调优 🟡（已定位平手项/采样；主因 μ 不准，下一步 rollout 叶子）
**目标**：让"全知 + beam"的离线优势变成分数。当前证据：构造抽牌牌组 beam known−unknown **+44.6**，但真实牌组只有 **+3.0**，因为 leaf 估不准（[EXPECTIMAX L399-417](EXPECTIMAX.md#L399)）。

**2026-11-22 凌晨已做（实验，默认关闭，生产不变）**
- 诊断：真实小牌组上 beam 91.3 vs 回合内 expectimax 143.1——档位效用封顶 2.0 导致大量平手，
  搜索平手 tie-break 优先存体力/出牌位；σ 扫描无影响，beam `branching` 有影响。
- 加了 `AnalyticLeafValue.score_tiebreak`（默认 0）破平手 + `eval_known_draw.py` 的
  `--score-tiebreak` / `--branching`；配对 60 局：beam **+14.3**（CI [7.9,20.6]）→ 再加
  branching=10 共 **+19.9**（CI [12.8,27.1]），within 基本不变（+0.3）。
- **但 beam 仍比 within 低 22.3%（111.2 vs 143.1），T4 决策门未达成**；生产默认仍 expectimax/leaf tiebreak=0。

**2026-11-22 凌晨（rollout 叶子，负结果，代码保留但默认关闭）**
- 实现 `RolloutLeafValue` + `sim_from_state`（`expectimax.py`），eval 加 `--leaf rollout --rollouts
  --rollout-policy {greedy,within}`；叶子用 `LessonSim` 跑完剩余回合取 μ。
- 60 局 small：analytic beam unknown/known 111.3/111.4；rollout greedy r=3 只有 103.0/104.1
  （**−8.3/−7.3**）；rollout 无 tiebreak / within-policy 更差（78.8~89.0）。
- 结论：rollout 策略（greedy）弱于执行策略（within），leaf μ 排序与实际执行错位；
  rollout 次数 1/3/6 不改变结论。细节见 [HANDOVER 二·补十](HANDOVER.md#L397)。

**下一步（按性价比）**
1. **受控 policy-evaluation 叶子**：只对 beam 最深端点做 rollout，且用执行同策略（within）+ 缓存 + 小预算，
   验证 μ 排序是否变好（不要全叶子 rollout，成本爆炸）；
2. **rollout 数据 → 学 V_leaf**：用 rollout 的（状态, 最终分）样本重训 `v_leaf.json`（新增监督信号）；
3. 继续扫 `eval_expectimax.py --sweep` 的 beam 宽度 + `--branching`；draw 场景跑 `--full-info`；
4. 决策门不变：真实牌组 beam 显著优于 expectimax（P50 提升 + 不回退）再进真机。

**步骤**
1. 先读 [EXPECTIMAX.md L329-377](EXPECTIMAX.md#L262) 里两次 learned leaf 失败的教训（搜索/模拟器不同源、权重塌缩）。
2. leaf 加特征（官方 AI 的 H4/H8/H9）：`extra_plays`、层数 × 剩余回合、指针切换次数、累计全力值；`AnalyticLeafValue` 或重训 `v_leaf.json`。
3. 用 `scripts/eval_expectimax.py --sweep` 扫 beam 宽度；用 `scripts/eval_known_draw.py --scenario small --policy beam --full-info` 看真实牌组增益。
4. 决策门：真实牌组 beam 相比 expectimax 的配对提升要有统计意义（P50 提升 + 不回退），再进真机。

**改哪儿**：`src/gkagent/sim/expectimax.py`（leaf）、`src/gkagent/sim/v_leaf.py`、`data/knowledge/v_leaf.json`、`scripts/eval_*.py`
**验收（DoD）**：配对评测数字写进 EXPECTIMAX.md；`pytest` 全绿；真机考试分不低于 rules（T2 验证）。
**预算**：80–150k token（这是最难的一块，别一次会话硬啃）。

### T5（P1/P2）机制建模补齐（按官方 AI 对比表挑）⬜
**目标**：缩小"模拟器 vs 实战"偏差。按性价比排序：

1. **选牌评估器**（官方 H7；我们 `+1 抽` 近似）——奖励选卡/考试内选牌；
2. **P 道具 / 回忆 / 附魔**（官方最大分数缺口，[OFFICIAL_AI_NOTES L538-546](OFFICIAL_AI_NOTES.md#L538)）；
3. **考试减益 / 限制**（我们基本没建模）；
4. **饮料**（官方 AI 直接不喝 = 最强剪枝，可作为 A/B 对照）。

**验收（DoD）**：每补一项 → 模拟器 4 局逐分回归仍一致（`tests/test_hajime_eval.py`）+ 新机制单测 + 对应文档小节。
**预算**：每项 40–80k token。

### T6（P2）补采数据（需要真机 + 采集）⬜
- **非 5 NPC 的 produce 类型**：K 公式的 `npc_count*turns` 项只验过 5 NPC（[HANDOVER 四①](HANDOVER.md#L266)）。
- **11-20 期末 T9 回合内重洗**：考试内生成卡导致 grave 不可重建；需带更多日志信息采集或换一局同类样本。
- **同局两次重洗**：验证 `oracle.reshuffle` 的 RNG 快照第二次是否需推进（当前只按"一次重洗"快照，[EXPECTIMAX L505-510](EXPECTIMAX.md#L500)）。

**验收（DoD）**：`verify_shuffle.py` 新增样本全过 + 测试加回归（参考现有 6 条"实战回合算 K 会错"防线）。
**预算**：采集 1–2 小时 + 40–80k token。

### T7（P2）可靠性工程（照 hiro 三条原则补）⬜
1. **动作前互验**：点之前预算"下一帧应读到什么"，对不上丢弃重读（照 hiro 原则 3）；
2. **纯函数状态 + 离线重放**：`run_record` 有雏形，改成"同观测序列 → 同状态 → 可逐步比对"；
3. **自动复盘页**：每局生成逐回合页 + 人工标注转回归用例。

**验收（DoD）**：新增测试（互验的假观测序列）；一局自动复盘页样例；`LIVE_RUN.md` 更新。
**预算**：60–120k token。

### T8（P3，低成本）情报与决策记录 ⬜
- 每完成一个任务：更新 `QQ_GROUP_NOTES.md` / `HIRO_VIDEO_NOTES.md`（有变化时）、写一条 ADR（`ARCHITECTURE.md`）。
- 只在有明确收益时更新；别为写文档而写。

---

## 5. 里程碑建议（按会话切分）

| 里程碑 | 内容 | 完成标志 | 预估 |
|---|---|---|---|
| M1 | T1 跑完整局 | RUNS.md 有完整一局记录 | 1 个会话 |
| M2 | T3 实时打通 | 真机考试 `[exam-plan] verified` | 1 个会话 |
| M3 | T2 三引擎 A/B | 同卡组三局成绩表 + 结论 | 1 个会话 |
| M4 | T4 leaf 调优 | 真实牌组配对评测有显著提升 | 1–2 个会话 |
| M5 | T5/T6 机制+数据 | 模拟器回归不破 + 新样本全过 | 2–3 个会话 |
| 终态 | **真机评价 A（10237+）** | 同账号同卡组追平/超过手动 | — |

---

## 6. 路径 / 命令速查（交接必用）

```
采集数据        C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl
考试牌堆快照    C:\GakumasLocal\GakumasUnlock\out\deck_snapshots.json
逐回合真值      C:\GakumasLocal\GakumasUnlock\out\exam_truth.json
考试牌序 setup  D:\Games\gakumas-agent\out\exam_setup.json     （gitignore，可重建）
主数据库        D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master
策略配置        D:\Games\gakumas-agent\data\knowledge\policy.json
真机日志        D:\Games\gakumas-agent\data\auto\auto_log_<ep>.log + step_*.png
```

```powershell
# 单场/全量考试牌序数据（生产接线用）
.venv\Scripts\python.exe scripts\build_exam_setup.py
# T3：当前这场考试的候选（考试进行中也能跑；bot 会运行时重载并逐回合锁定）
.venv\Scripts\python.exe scripts\build_exam_setup.py --current
# 离线核对 --current（对已结束的采集；真机没在考试时用）
.venv\Scripts\python.exe scripts\build_exam_setup.py --current --allow-finished --out out\exam_setup_current_test.json
# 生产接线端到端核对（36/36 手牌、3/3 重洗）
.venv\Scripts\python.exe scripts\verify_exam_wiring.py
# F#42 课程帧回放回归（真机课程截图 → LessonReader → expectimax 决策，最后一个用例不选 buff）
.venv\Scripts\python.exe -m pytest tests\test_lesson_play_f42.py -q
# 上真机前：模拟器整局 A/B（训练+考试都注入真 LessonPolicy；0 blocked/0 error/C+率）
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --out out\sim_engine_ab.json
# 离线配对评测：known_draw / beam / full-info（重洗后段全知）
.venv\Scripts\python.exe scripts\eval_known_draw.py --games 40 --scenario small --policy beam --full-info
# 真机跑局（引擎：--engine > policy.json produce.engine > 默认 expectimax；rules 只用于 A/B 对照）
# --max-minutes 默认 30：卡住会写 episode-timeout 主动停局，不再无限空转
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 300 ep-xxx --skip-home --exam-setup out\exam_setup.json --engine expectimax --max-minutes 30" --timeout 2400
# 考试分数提取（A/B 对比用）
.venv\Scripts\python.exe scripts\extract_exams.py
# 一局体检
.venv\Scripts\python.exe scripts\episode_report.py ep-xxx
```

---

## 7. 坑与红线（先看，别踩）

| 类别 | 内容 |
|---|---|
| 四条铁律 | ① 不碰 `D:\Games\Gakumas\gakumas`（用户在用）；② 采集必须 `GKM_UNLOCK=0 / GKM_FORGE=0 / GKM_STATIC_USER=0`；③ `data/hiro/` 是 AGPL 只参考；④ 成本纪律（见 [HANDOVER 八](HANDOVER.md#L404)） |
| 真机 | 一局只允许一个 `auto_produce` 进程；窗口 540x960、不能最小化；游戏重启后必须重启 `GDEAgent`；`data/STOP` 要清 |
| 卡死上限 | `auto_produce --max-minutes 30`（默认 30，0=关闭）：超时写 `episode-timeout` failure 主动停局，不许无限空转（用户 2026-11-21：见过卡两个多小时还跑到 C） |
| 跳过红线 | **SKIP 只在所有牌都付不起时允许**（用户 2026-11-21 指定）；读不到分/费用=去修 OCR/卡表，不许跳过补偿。`--ignore-user` 是无人值守跑整局的默认参数 |
| 规则回退 | **bot 不许回退 rules**（用户 2026-11-21）：搜索失败 = `[engine][BLOCKED]` 中止本局 + 修 OCR/卡表/参数，不许静默改用 rules 兜底；`--engine rules` 仅 A/B/离线；`allow_rule_fallback=True` 只是代码级调试开关（policy.json 不可配） |
| 快速路径 | 课程/加载帧的模板快速路径会吞掉遮罩弹窗（回合结束确认框、通信错误弹窗）：新增弹窗必须配"同屏重复→强制整屏 OCR"的逃生门 |
| 全知搜索 | 牌序**核对失败自动停用**是设计（宁可用期望模型也不用错牌序）；离线回放里策略出牌与实机不同会在重洗前停用，属正常 |
| 课程/考试 HUD | 课程右上角是**培育属性值**（不是课程分，`LessonState.attr`），课程分 = 属性值 − 开课基线；正中圆环「CLEAR截止 / PERFECT截止 N」是**还差 N 分**（不是过关线）。`LessonReader.read(kind="lesson")` 已换算好 `score/gauge/perfect/goal`；新读屏字段别再把语义弄反（F#42 就是这么 0 分的） |
| 出牌上限 | **游戏默认每回合只能出 1 张牌**（额外出牌来自卡效果 `ExamPlayableValueAdd`/P 道具），课程和考试都成立；搜索 `play_limit=1` 是刻意的，别改回 3（否则会偏好"buff+补刀"→ 0 分）。模拟器 `plays_per_turn=3` 尚未对齐，属 T5 待办 |
| 配置陷阱 | 引擎优先级：`--engine` CLI > `policy.json` 的 `produce.engine`（真机 bot）> 默认 **expectimax**（bot 入口；`LessonPolicy` 自身默认仍是 rules，供离线/单测）；`lesson.engine` 只作 `LessonPolicy` 独立使用/单测默认（保持 rules，别只改它）。每局日志首行 `[engine]` 写明实际用了谁。OCR 模型优先级：`OcrEngine(config_path=)` > `GKAGENT_OCR_CONFIG` > 本地 `configs/ocr_jp.yaml`（下载脚本生成）> 内置中文模型；日志首行 `[ocr] 模型=` 可确认；配置/模型文件缺失**直接报错**，不静默回退中文模型 |
| 数据 | 主数据缺 11-21 新卡：`verify_shuffle.py` 用 `SUPPLEMENT_*` 兜底，更新主数据后可删；`out/` 不进 git |
| 时间口径 | 期中考试有 `forceEndScore` 提前结束，但 K（洗牌前 RNG 消耗）**按配置回合**算，不是实战回合 |
| 提交 | 一次任务一个 `feat(...)` 提交（含测试+文档），再一个 `docs(handover): 补提交记录哈希`；`.gitignore` 已忽略 `out/` |
| 存档 | 私有存档/私有仓库见 [ARCHIVE.md](ARCHIVE.md)：`scripts\archive_private.ps1`（bundle+裸仓库+采集数据备份，`-Push` 推 Gitee 私有仓）；**只能私有** |

---

## 8. 交接程序

1. **开新会话**：工作目录 `D:\Games\gakumas-agent`，第一句话用本文件开头那段。
2. **先跑 §2 四条基线**，不绿先修基线。
3. **挑任务**：默认从 §4 状态为 ⬜ 的最高优先级开始；一次会话**只做 1 个任务**（成本纪律：上下文 >3 小时/20 万 token 就该换会话）。
4. **完成后**：
   - 更新 §4 该任务状态 ⬜→✅，并把实测数字写进正文；
   - 更新相关文档（任务里写明的那些）；
   - 提交代码 + 文档 + 测试，再补一条哈希提交；
   - 在 [HANDOVER.md](HANDOVER.md) 的提交记录里加一行。
5. **写不清=没完成**：DoD 必须能用命令/数字验证；"感觉能跑"不算。

**新会话开场白（复制）**

```
工作目录 D:\Games\gakumas-agent。
读 docs/INDEX.md → docs/WORKPLAN.md（总计划）→ docs/HANDOVER_NEXT.md §2 跑四条基线。
期望：洗牌 4/4 场 + 3/3 重洗；pytest 934 passed / 1 skipped（935 条收集 / 66 文件）；
exam_setup 4/4 场 86/86 张 + 重洗 24/24；wiring 36/36 手牌 + 3/3 重洗 + known_draw 29/29 + beam 28。
A1（OCR 换日文模型）已于 2026-11-22 完成（官方 PP-OCRv6 Apache-2.0，见 WORKPLAN A1 / HANDOVER 二·补十四）；
A2（F#42 课程硬打必须得分）也已完成（HUD 语义 + 每回合 1 张 + 硬打保分，见 WORKPLAN A2 / HANDOVER 二·补十五）。
基线绿后按 WORKPLAN 从 A3 开始：A3 F#43 结果页空转 → A4 离线回放素材 → A5 T3 离线预演
→ 阶段 B/C/D，全部离线做完再上真机（T3→T1→T2），最后 gkbench。
用户规则：SKIP 只在真没体力；禁止静默回退 rules（搜索失败=[engine][BLOCKED] 中止+修 root cause）；
真机整局 --ignore-user。一次会话只做 1 个任务。
```

---

## 9. 对手情报速查（写作这份文档时的状态，2026-11-21）

| 项目 | 他们强在哪 | 他们弱在哪（我们的机会） |
|---|---|---|
| **hiro-gakumas-hero**（matto49，AGPL，[HIRO_VIDEO_NOTES](HIRO_VIDEO_NOTES.md)） | Mac+PlayCover 40+ 局稳定；初 REGULAR A/10428；H.I.F. 本战最高 130 万；三层架构 + 规则/LLM 权衡；互验 + 自动复盘页；~120 模块/600+ 测试 | **Windows DMM 不成熟**（只到第 2/3 名）；没有 seed/牌序途径；LLM 有 token 成本 |
| **QQ 群「初星学园情报处理部」**（[QQ_GROUP_NOTES](QQ_GROUP_NOTES.md)） | seed 反推（2^31 枚举+观测剪枝）信息论口径清晰（3 回合收敛 ~1000 候选）；nodejs 实现 | 自己定规矩**实战不用 seed**；uihorizon/uinet "到头了"（10× 训练量反而倒退）；无公开成绩 |
| **官方 AI**（GKMS 私有，[OFFICIAL_AI_NOTES](OFFICIAL_AI_NOTES.md)） | 真实牌序 + 50+ 特征评估 + 计划重放 + 限深/命令预算；考试机制覆盖最全 | 私有、不可移植、需 GKMS 原生核心；我们拿不到权重 |
| **MaaGakumasu**（[MAA_INTEGRATION](MAA_INTEGRATION.md)） | 手和眼：截屏/识别/点击/日常/汉化完整 | 出牌只到启发式；我们只做决策层（ADR-001） |
| **我们** | **唯一**把 MITM 采集→seed→整段牌序（含弃牌重洗）做成生产接口并经实机逐张验证；纯 Python/Windows 原生；0 token | 自动化最后一公里（T1）、无 A/B（T2）、全知未实时接通（T3）、leaf 弱（T4） |

**定位一句话**：信息维度我们领先，执行与策略强度落后 hiro；先把"能无人值守跑完整局 + 真机 A/B"做出来，故事才完整。
