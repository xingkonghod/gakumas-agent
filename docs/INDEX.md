# 📖 新对话从这里开始

> **第一句话这样说**：
> 「读 `docs/INDEX.md`，然后按里面的清单继续做」
>
> 本文件只做**导航**，不写内容。具体内容在各专题文档里。
>
> **要动手做事，先看 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)**（交接清单：补什么 · 做什么 · 每个任务的验收标准）。
> 只想了解现状看 [HANDOVER.md](HANDOVER.md)，想知道还差什么/下一步做什么看 HANDOVER_NEXT。

---

## 一、按任务查文档

### 想继续做「拿 seed / 完全信息」

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 0 | [HANDOVER_NEXT.md](HANDOVER_NEXT.md) | **补什么 · 做什么 · 任务验收**（行动型交接，先看这个）|
| 1 | [HANDOVER.md](HANDOVER.md) | 现状 + 已完成什么（二·补五）|
| 2 | [MASTER_DATA.md](MASTER_DATA.md) | 主数据库怎么建的、seed 字段在哪 |
| 4 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 采集链路的坑（改之前必看）|
| 5 | [EXPECTIMAX.md](EXPECTIMAX.md) | 搜索/全知牌序/beam 与已知限制 |

### 想继续做「自动化 bot 跑完整局 / 真机 A/B」

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 0 | [HANDOVER_NEXT.md](HANDOVER_NEXT.md) | 任务 T1/T2/T3（跑完整局 → 实时打通 → A/B）|
| 1 | [LIVE_RUN.md](LIVE_RUN.md) | **真机跑局操作手册**（自检清单、起跑、跑完三件事）|
| 2 | [FAILURES.md](FAILURES.md) | 真机失败记录（现象→根因→修复→教训）|
| 3 | [RUNS.md](RUNS.md) | 历史跑局与成绩对照（bot 最好 C+/5992，手动 A/10237）|
| 4 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 屏幕识别/点击类的坑 |

### 想改模拟器 / 评价公式

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 1 | [SIMULATOR.md](SIMULATOR.md) | 模拟器结构 |
| 2 | [RULES_REFERENCE.md](RULES_REFERENCE.md) | 规则核验表（对照 gakumas-tools 参考引擎/官方 wiki/真机；逐条状态）|
| 3 | [MASTER_DATA.md](MASTER_DATA.md) | 真实主数据在哪、字段含义 |
| 4 | [EXPECTIMAX.md](EXPECTIMAX.md) | 搜索与叶子评估 |

### 想继续做真机采集

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 1 | [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) | 结构、配置、四个坑 |
| 2 | [UNLOCK_REPORT.md](UNLOCK_REPORT.md) | 解锁工具怎么工作（端点/加密）|
| 3 | [UNLOCK_ADAPT.md](UNLOCK_ADAPT.md) | hook 机制、版本适配 |
| 4 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 踩过的坑 |
| 5 | [LOCAL_DEPLOY_VIDEO.md](LOCAL_DEPLOY_VIDEO.md) | 本地化部署路线（视频解剖 + 2026-11-22 整合包指针）|
| 6 | [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md) | **作者 2026-11-22 四游戏整合包分析**：新版本变化/修复、与我们的采集安装的关系（只读参考，勿覆盖）|

### 想备份 / 存档 / 私有仓库

| 文档 | 内容 |
|---|---|
| [ARCHIVE.md](ARCHIVE.md) | 私有存档：本地裸仓库 + bundle + 采集数据备份 + Gitee/GitHub 私有仓库推送与恢复 |

### 想了解项目来历 / 引用 / 图表

| 文档 | 内容 |
|---|---|
| [../README.md](../README.md) | **项目总览**：来历时间线、架构图、全知链路图、关键结果表、引用致谢 |
| **[WORKPLAN.md](WORKPLAN.md)** | **总作战计划**：离线全部做完 → 真机 → gkbench；完整任务表/DoD/已完成清单 |
| [PROVENANCE.md](PROVENANCE.md) | **来历/数据血缘/引用清单/许可证边界**（每个数据从哪来、借了谁什么）|
| [ARCHIVE.md](ARCHIVE.md) | 私有存档与私有仓库流程 |
| [GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md) | 群文件分析：OCR 根因（日文模型）、魔改 MAA 结构、手机实验版 APK、许可证边界 |

### 想了解社区在做什么 / 我们跟别人的进度对比

| 文档 | 内容 |
|---|---|
| [COMPARE.md](COMPARE.md) | **我们 vs hiro / QQ 群 / 官方 AI 的进度对照（口径、数字、唯一可比路径）** |
| [GKBENCH.md](GKBENCH.md) | **gkbench 数据/口径：公开 API、批量下载、参考分（fixed/template）、哪些要登录令牌** |
| [HIRO_VIDEO_NOTES.md](HIRO_VIDEO_NOTES.md) | hiro-gakumas-hero 的架构（视频 + 仓库）|
| [AUTO_GAKUMAS_NOTES.md](AUTO_GAKUMAS_NOTES.md) | auto-gakumas 分析（Android ADB + 每战在线 PPO + SO-ISMCTS，H.I.F 本戦实机 2回戦 1.59M；无许可证只参考，2026-11-23）|
| [OFFICIAL_AI_NOTES.md](OFFICIAL_AI_NOTES.md) | 官方 AI 的启发式（10 条）|

---

## 二、全文档清单

| 文档 | 一句话 |
|---|---|
| **INDEX.md** | 本文件，导航 |
| **../README.md** | 项目总览：来历/架构图/结果/引用 |
| **PROVENANCE.md** | 来历/数据血缘/引用清单/许可证边界 |
| **WORKPLAN.md** | 总作战计划（离线→真机→gkbench）|
| **HANDOVER_NEXT.md** | **交接清单：补什么 · 做什么 · 每个任务的验收（行动型，先看）** |
| **HANDOVER.md** | 项目现状 + 已完成什么 + 路径速查 + 坑 |
| **COMPARE.md** | 我们 vs 对手的进度对照（口径/数字/唯一可比路径） |
| **GKBENCH.md** | gkbench 数据与口径（公开 API/批量下载/参考分/令牌） |
| **TROUBLESHOOTING.md** | 踩坑记录（采集 9 项 / bot 7 项 / 评测与方法论 7 项 / **§四 游戏更新·协议·代理·TLS 断链 13 条（外部经验，⚠️ 本项目待验证）** / 工具与环境）|
| **FAILURES.md** | 真机失败记录（现象→根因→修复→教训）|
| **CAPTURE_PIPELINE.md** | 采集链路：结构、配置、四个坑、已采数据 |
| **MASTER_DATA.md** | 主数据库（286 表）+ seed 发现 |
| **SIMULATOR.md** | 模拟器设计与实现 |
| **EXPECTIMAX.md** | 回合内搜索引擎 |
| **R9_ANALYSIS.md** | B11 r9-large 解释报告（small 回退机制：信号稀释+输入漂移+v1 拉扯；修复预测）+ §8 r10 实测验证（预测 vs 实测）+ §9 r10 行为探针（残留回退已非 v1 贪即时分） |
| **RULES_REFERENCE.md** | **规则核验表**（回合规则/结算顺序/取整/buff/牌序，对照 gakumas-tools + 真机）|
| **RULES_FROM_BINARY.md** | 元数据解包结果（枚举/字段/方法签名）|
| **UNLOCK_REPORT.md** | GakumasUnlock 工具分析 |
| **UNLOCK_ADAPT.md** | hook 机制与版本适配 |
| **HIRO_VIDEO_NOTES.md** | hiro 项目视频要点 |
| **AUTO_GAKUMAS_NOTES.md** | auto-gakumas 外部情报（零 LLM / ADB / 每战在线 PPO + SO-ISMCTS / 回忆限 1；许可证红线）|
| **OFFICIAL_AI_NOTES.md** | 官方 AI 的策略启发式 |
| **RUNS.md** | 实机跑局记录 |
| **ARCHIVE.md** | 私有存档/私有仓库（bundle、裸仓库、采集数据备份、推送/恢复）|
| **LIVE_CHECK.md** | 真机检查清单 |
| **LIVE_RUN.md** | 真机跑局流程 |
| **ARCHITECTURE.md** | 架构与 ADR |
| **PROJECT_PLAN.md** | 项目规划 |
| **MAA_INTEGRATION.md** | 与 MAA 的关系 |
| **META_STRATEGY.md** | 元策略 |
| **WIKI_DUAL_SOURCE.md** | Wiki 双数据源 |
| **I18N_TODO.md** | 汉化待办 |
| **LOCAL_DEPLOY_VIDEO.md** | 本地化部署视频分析（GakumasUnlock 早期路线；2026-11-22 已拿到新整合包，见下） |
| **LOCAL_LAUNCHER_20261122.md** | 作者 2026-11-22 四游戏整合启动器包分析（新版本变化/修复 + 与采集安装的边界，只读参考；T9-B7/C0 已完成、剩 E0） |

---

## 三、四条铁律（先看，别踩）

```
① 不要碰 D:\Games\Gakumas\gakumas —— 那是用户正在用的 DMM 客户端
   采集用的是副本 C:\GakumasLocal

② 采集必须 UNLOCK=0 / FORGE=0 / STATIC_USER=0
   否则会污染用户账号的真实数据

③ data/hiro/ 是 AGPL-3.0
   只做参考和对照，不要拷进本项目

④ 成本纪律（详见 HANDOVER.md 第八节）
   · 派子智能体时机械活用 reasoning_effort: low，实现用 medium
   · 大文件只 grep，不 read（dump.cs 75MB）
   · 完成一个子任务就提醒用户开新会话（上下文 >3 小时就该换）
```

---

## 四、当前一句话状态

**采集链路已通、主数据已入库、seed 在流量里、考试牌堆已定位重建；洗牌模型完整破解并经四场实机验证——
回合属性/NPC 消耗 + Fisher-Yates 全对上，配置 9/11/12 回合与提前结束场景都精确复现（期中 18/18、
期末 26/26、PRO 期中 15/15、PRO 期末 27/27）。支援强化掷点 + 弃牌堆重洗也已完整建模：三组重洗样本
重洗前掷点 45/29/46 次，洗后手牌 9/9、6/6、9/9 逐张复现。完全信息搜索第二段已接完：
**生产接线**（采集数据 → `ExamSetup`/`ExamDrawPlan` → `LessonPolicy` → `ExpectState.known_draw`，
端到端 4/4 场、手牌 36/36 回合、重洗 3/3）+ **重洗后段全知**（`ExpectState.discard_order` +
确定性重洗钩子）+ **`lesson.engine="beam"` 跨回合规划选项**。真机侧：决策可观测性 + 引擎接线
（`--engine` > `produce.engine`）+ T1 十类流程卡点修复（[FAILURES #27-32](FAILURES.md#L6)）已提交；
T3 实时接线代码已接（`build_exam_setup --current` + `ExamPlanSelector` + 运行时重载），**差真机考试验收**。
2026-11-21 22:00 后第一次真机跑完整局：期中 914/第 3 → **最终 C/4242**；根因是"读不到牌价值→搜索建议 SKIP→
执行跳过"，已按用户规则封死：**只有所有牌都付不起才允许 SKIP**，四引擎统一拦截（[FAILURES #34-39](FAILURES.md#L6)，
提交 4b07fa7/8a2af2b/b231b3f）。2026-11-21 深夜追加用户规则：**bot 不许回退 rules**——
搜索引擎失败不再静默改用规则：状态没读全→等下一帧，搜索异常/失配→`[engine][BLOCKED]` 中止本局并去修
OCR/卡表；bot 入口默认 expectimax（[FAILURES #40](FAILURES.md#L293)，提交见 HANDOVER 二·补八）。
上真机前已在模拟器跑整局 A/B（训练+考试都注入真 LessonPolicy）：3 组种子共 76 局，0 `RuleFallbackBlocked`、
0 异常、满局 C+ 率 100%，expectimax 与 rules 评价点在噪声内（[SIMULATOR §10](SIMULATOR.md)）；真机侧新增
`auto_produce --max-minutes 30` 墙钟上限，卡住会写 `episode-timeout` 主动停局（不再卡两个多小时）。
按用户要求暂不跑真机、先补「我们 vs 别人的差距」：**T4 策略强度**在 B1 修正——旧结论
「beam 比 within 低 22.3%」是评测执行器 `_execute_plan` 白丢回合的 bug；修正后 60 局配对
**beam unknown 164.0 / known 165.5 vs within 143.1**（+20.9/+22.4，CI 全正），决策门 PASS；
受控 frontier 叶子中性，`score_tiebreak=1e-3` 是真增益（详见 [EXPECTIMAX](EXPECTIMAX.md)「T4 修正」）。
**2026-11-22 A1 已完成**：OCR 换官方 **PP-OCRv6 small 多语言模型（Apache-2.0）**——日文剧情/选项
完整可读（`ヨーグルトパフェ`/`つくねハンバーグ`/`ドリンクバー` + 整句对白），中文 UI 不受影响；
`scripts/download_ocr_models.py` 下载+sha256 校验，`OcrEngine` 自动加载 `configs/ocr_jp.yaml`
（缺失直接报错，不静默回退中文模型），真机日志 `[ocr] 模型=` 可确认。
**同日 A2 已完成**（F#42 课程硬打必须得分）：查出并修掉两个课程/考试模型错误——课程右上角是
**培育属性值**（不是课程分）、正中圆环「CLEAR截止 N」是**还差 N 分**（不是过关线）；且游戏
**默认每回合只能出 1 张牌**（旧搜索写死 3 → 每回合先打 buff → 整节课 0 分 FAILED）。
现在硬打保证得分（正分牌优先），真机课程帧回放从"选 buff"变成"选魅力的基础 29 分"。
**同日 A3 已完成**（F#43 结果页空转）：真根因不是结果页，是**日文饮料选择事件屏**——旧中文 OCR
读不出假名选项，且飘字正则把 P 费标签「-100 / -50」当成 +N 飘字 → 每步点屏幕中央空转 10 次停机。
修法：`_GAIN_RE` 只认正收益 + 事件屏用 P 费标签定位免费项 + 静态页第 3 次起找「下一步」；
真机帧回放（`tests/test_produce_ui_f43.py` 7 条）从 `result-tap/gain` 变成 `event-choice/last-row → confirm`。
**同日 A4 已完成**（离线回放素材）：`tests/fixtures/` 归档 8 张关键真机帧（`README.md` 有溯源表），
`tests/test_frames_replay_a4.py` 9 条「真像素→真 OCR→生产 `decide`」回放（日文剧情二选一 / 课程 buff /
结果页 / 外出事件 / 考试浮层 / 回合结束确认框 / 真机确认弹窗 / 持有上限保留饮料）；新增
`scripts/scan_frames.py` 批量挑帧工具。回放顺手抓到并修掉 `_checkbox_bands` 缺 `@staticmethod` 的真机
`TypeError`（FAILURES #44）。**回合结束确认框的真机帧已被 `step_NNN` 轮转覆盖**（扫 1352 张 0 命中），
该条暂用真机课程帧 OCR 行 + F#36 真实文案回放，下次真机跑局补拍。
**同日 A5 已完成**（T3 离线预演）：新增 `scripts/verify_exam_plan_offline.py`——`build_exam_setup
--current --allow-finished` 对最新场生成 3 个 `config_turns` 候选（9/11/12），用采集 truth 驱动
`ExamPlanSelector`：**第 2 回合锁定 config_turns=12（真值 12）**、锁定后逐回合核对 11/11、
`known_draw` 覆盖下一手 9/9；四场 sweep 也全部 T1–T2 锁定且选中真值，候选收敛到 1、`locked_turn≤3`。
**同日 B1 已完成**（T4 修正）：查出 `scripts/eval_known_draw.py::_execute_plan` 在「手牌打空自动
结束回合」后又补 SKIP、白丢下一回合的评测 bug；修后 60 局配对 beam unknown 164.0 / known 165.5
vs within 143.1（+20.9/+22.4，CI 全正；决策门 114.6%/115.7% PASS）；新增 `scripts/eval_t4_b1.py`
与 `tests/test_beam_frontier.py` 6 条（含受控 frontier 叶子，实测中性）。
全量 pytest **964 passed / 1 skipped**（965 收集 / 70 文件）。细节见 HANDOVER 二·补十九 / EXPECTIMAX「T4 修正」。
**同日 B2 已完成**（全知数据训练 MLP 叶子）：`scripts/build_b2_dataset.py` 用 beam **全知**自对弈在
**叶子状态**（`end_turn_state` 形态）采 26.5k 样本（标签 = on-policy 实际后续得分），
`src/gkagent/sim/leaf_mlp.py` 104 维结构化特征 + MLP 104→96→48（val r²=0.943），
`scripts/eval_b2.py` 用 **B1 修正 harness** 配对评测：选择段 seed 2000–2079 beam 解析式
166.8 → **learned 173.7（+6.8）/ ensemble 0.25 174.4（+7.5）**；**确认段 seed 3000–3119
（120 局，未参与选择）beam 157.8 → 165.5（+7.7，CI [+4.2,+11.2]）/ ensemble 0.5 166.9
（+9.0，CI [+5.8,+12.2]）**，CLEAR 95→98.3%、PERFECT 33.3→50%；known 条件同向（+7.2~+7.8）。
within 用 learned 叶子显著变差 −3.3（负结果：教师策略收益偏乐观，**只对 engine=beam 有益**）；
生产 `LessonPolicy` 已加可选 `leaf_model`/`leaf_model_weight`（默认 None = 行为不变、缓存），
T2 真机 A/B 再决定是否打开。细节见 [EXPECTIMAX](EXPECTIMAX.md)「B2 学习叶子」/ HANDOVER 二·补二十。
**同日 B3 已完成**（T5 机制建模：模拟器回合规则对齐真机 + RULES_REFERENCE 核验表）：
核实真机**每回合基础只出 1 张牌**（一手 3 张是"选 1 张"）、打完最后一张**自动结束回合**、
回合末还有剩余次数（SKIP）**回 2 体力封顶**（gakumas-tools `TurnManager`/`CardManager` 证据 +
真机 4 场考试 39 回合日志：32 回合 1 张、7 回合 2 张、每回合手牌都 3 张）。补丁：`plays_per_turn`/
`play_limit`/`DEFAULT_PLAY_LIMIT` 默认 3→1、自动结束回合、SKIP 回体力、取整对齐 `safeCeil`
（旧课程 floor / 考试 round 一次；实机回放黄金值 9→23、5→8、2→3 等 12 条）。`RULES_REFERENCE.md`
重写为逐条核验表（回合/结算顺序/buff 生命周期/牌序 ✅/审查倍率 ❌ 仍常量 4.11/熱意/P 道具等 Gap）；
新增 `scripts/export_t5_turn_rules.py` + `tests/fixtures/t5_exam_turn_rules.json` +
`tests/test_t5_turn_rules.py` 9 条真机回合规则配对回归。**重标定**：`sim_engine_ab` 76 局里
expectimax 从噪声内变**显著强于 rules**（+342~+429 评价点）；B1 60 局 within 89.1→beam 95.7
（+6.6，决策门 107.4% PASS）；**B2 旧模型在 B3 规则下重测 FAIL（确认段 beam −27.9）→ 必须按
新规则重采数据重训**；400 局培育标定带 650–1100→950–1450。全量 pytest **985 passed / 1 skipped**
（986 收集 / 72 文件）。细节见 [RULES_REFERENCE](RULES_REFERENCE.md) / [SIMULATOR §11](SIMULATOR.md) /
[EXPECTIMAX「B3 规则修正与重标定」](EXPECTIMAX.md) / HANDOVER 二·补二十一。
**同日 F 阶段数据 + F0 预检已完成**（gkbench）：用户登录 `hiro.matto.top/gkbench` 并给了
**命令行令牌**（存仓库外 `~/.config/gkbench/token`，可随时网页吊销）→ 新增 `scripts/bench_download.py`
（公开 API + 令牌、断点续传）：已下 hif **80 run / 36,350 条对局路线**、**329 题官方开发种子 + `check`**、
505 题模板存档、fixed/template 两种榜单与参考分（best-known 1,452,088 / UIHorizon 631,129=0.5113 /
UINet 578,722=0.4551 / official-ai 232,710=0.2131）；F0 预检用官方 `check.hand` 核洗牌模型
**286/384=74.5%**（npc 按 stage：選抜 5、本戦 2；不一致根因 = `initial_add` + `isInitial` 变体，
后由 F0 收尾修正）。细节见 [GKBENCH.md](GKBENCH.md) / HANDOVER 二·补二十二。
**同日 17:2x 新会话开工基线复核四项全绿**：① 4/4+3/3、② 985/1、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28，与文档期望逐项一致；② 唯一 skip = `tests/test_produce_ui.py:1181`
（`step_047` 被真机跑局覆写、当前不是行动页，属预期）。见 HANDOVER 二·补二十三。
**同日 F0 收尾完成**（gkbench 官方种子校准）：新增 `scripts/verify_gkbench_shuffle.py`（只读本地
种子+主数据）——**initial 按 base 卡 id（含强化变体）+ `initial_add`、npc 按 idol 卡**
（本戦 jsna 4 人制=3 / fktn 2 人制=1 / 其余 3 人制=2；缺 step 字段用 round 兜底）；官方
`check.hand` 核洗牌模型 **286/384（74.5%）→ 366/384=95.3% 精确 / 97.4% 逐张**（選抜 100%，
逐题 311/329 全中；剩余 18 组全是考试开始加卡机制：`ExamInitialDeck` 15 + kllj 开局 +1 手牌 3，
**无一洗牌错误**）；起点校准 `check.turn=1 / score=0 / stamina 96.1%=starting_stamina / rules=55`
（15 组体力差=偶像卡 P 道具考试开始附魔常量）→ 基准复算用 `check.stamina` 覆盖 loadout。
细节见 [GKBENCH.md §4.5](GKBENCH.md) / [COMPARE.md](COMPARE.md) / HANDOVER 二·补二十四。
**同日 B4（T5①）已完成**（审查倍率分段 + 联动惩罚）：考试每回合的属性倍率不再是常量 4.11，
改为客户端真实公式——主数据分数表**分段折线** × 审查基准**联动惩罚**（`common=1000−Σpenalties`
三项共乘）× 单精度取整，落地 `sim/exam_multiplier.py` + 主数据解析 `data/exam_bonus.py`；
模拟器按回合属性乘（含依赖分/回合末好印象）、生产搜索改用屏幕读到的真实倍率
（真机帧「舞蹈 207%」→ `attr=2.07` 进日志）；真机采集局夹具期中 Vo/Da/Vi
**4.09/2.20/2.60×**、期末 **6.97/2.85/4.96×**（低于审查基准的联动惩罚已对上）；
`tests/test_exam_multiplier.py` 21 条；全量 pytest **1006 passed / 1 skipped**
（1007 收集 / 73 文件）。细节见 [RULES_REFERENCE §5.1](RULES_REFERENCE.md) / HANDOVER 二·补二十五。
**同日 B5（T5②）已完成**（熱意 + 温存解除）：熱意改为**独立整数分数资源**（出牌分在集中之后加算、
获得时向上取整、回合末清零/有「熱意延長」则保留）；温存解除 1 段 +5 熱意 / 2 段 +8 熱意
+5 固定元気（不吃やる気）+ 解除当回合 **+1 出牌次数**（同回合可重复、温存→全力回合边界也触发）；
卡牌熱意追加/増加/延長/本牌適用倍数 ×2 接入 `sim_produce`（MODELED_EFFECTS 29→32）与生产卡表；
`sim/enthusiasm.py` 纯规则 + `LessonSim`/`ExpectState` 镜像；`tests/test_t5_enthusiasm.py` 16 条；
全量 pytest **1023 passed / 1 skipped（1024 收集 / 74 文件）**。
细节见 [RULES_REFERENCE §5.2](RULES_REFERENCE.md) / HANDOVER 二·补二十六 / WORKPLAN B5。
**同日 B6（T5③）已完成**（P 道具数据接入）：新增 `src/gkagent/data/p_items_db.py` 把对局
loadout 的 `produce_item_ids` 解析成 `PItemSpec`（未知 id 显式上报、缺数据抛错）；
`sim/p_items.py` 新增 **`exam_start`** 触发时机（288 段素材）与 **`ExamPlayableValueAdd →
extra_plays`**（51 段，取 `count` 列）；`LessonSim` 构造时先于 turn_start 结算考试开始效果、
`ExpectState` 镜像；`local_bench` 从 gkbench 题模板 loadout 接入（505 题 / 83 唯一 id /
72 已知 / 11 未知，`--p-items auto/off`）+ gkbench 提交从 `ctx.loadout`（公开配置、不含种子）
接入；离线 A/B（hif 30 题×2 seed 配对）greedy **+128.9（+3.36%，CI[+9.5,+248.4]）** /
expectimax +149.6（+3.98%）；新增 29 条测试，全量 pytest **1051 passed / 1 skipped
（1052 收集 / 76 文件）**。仍缺：真机培育侧 P 道具列表（T6/D1 补采）、效果覆盖
（gkbench 已知 131 段 spec 只实现 31 段）、主道具附魔/回忆。
细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) / HANDOVER 二·补二十七 / WORKPLAN B6。
**同日外部情报（11-22）**：用户提供作者**四游戏整合启动器包**（215 MB，11-22 构建）→ 已解包
静态分析（`交付文件清单` 1457 条 sha256 逐条通过；7z 归档 `data/dl/`、解包在仓库外），
文档 [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)（提交 `ddf221f`）；帮助属
参考级：可吸收更新/代理/TLS 排障经验、Produce API 语义、P 道具 47 条 id 清单；**不能**拿
考试算分公式、**不能**替换我们的采集安装。由此新增候选任务 **T9：B7 P 道具 47 条补全（默认
首选）/ C0 采集更新可靠性经验吸收 / E0 离线培育测试台实验**（三选一，见 HANDOVER_NEXT §4）。
**同日 T9-B7 已完成**（P 道具 47 条补全）：`build_p_items.py` 合并本地中文 masterTrans 1068 +
gakumasu-diff `ProduceItem.yaml` 新增 47 → `data/knowledge/p_items.json` **1068→1115 件**
（spec 1764→1849、已实现 421→445；新增 47 条卡名用仓库自译表、中文描述缺失处保留日文并
标 `i18n_text_source="ja"`、新触发 id 条件未解析的 22 件记 `condition_known=False` 且
**保守不触发**）；**gkbench 505 题模板 83 唯一 id 全部已知、未知 0**（B6: 72 已知/11 未知）；
离线 A/B（hif 30 题×2 seed）greedy **3840.7→3969.7（+128.9，+3.36%，CI[+9.5,+248.4]）**
（与 B6 逐位相同——新道具目前 0 分贡献）、expectimax 3732.0→3953.6（+221.5，CI[−71.4,+514.4]）；
新增 3 条测试，全量 pytest **1054 passed / 1 skipped（1055 收集 / 76 文件）**。
仍缺：真机培育侧 P 道具列表（T6/D1 补采）、新增 47 条的条件/效果语义（catalog 445/1849 段
已实现）、主道具附魔/回忆。细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) /
HANDOVER 二·补二十九 / WORKPLAN B7。
**同日 T9-C0 已完成**（采集/更新断链排障判据吸收，纯文档）：把作者包 11-07→11-14 踩过并修过的
「游戏更新/协议/代理/TLS 断链」经验整理成可执行判据——[TROUBLESHOOTING.md](TROUBLESHOOTING.md)
新增 **§四 13 条清单**（触发→症状/证据→处理→参考：`System/Check` 200 空体 + `x-error-code=2004`
= 客户端太旧；DMM 更新还原 hook DLL；协议 hash 变化即停；master 清单结构/长度/SQLCipher 判据 +
版本哈希不透明；`http1_bridge` 丢客户端版本/平台/会话头与业务错误头；`Auth/Login`
`req_body_len` 865/833→1003 与 `x-p-s` 需 DMM 常驻；上游端口写死→10061/`OFFLINE-FALLBACK`；
停服务先还原系统代理再停进程；CA 精确指纹/TLS 回退；代理残留自清理；诊断脱敏；更新互斥）+
§4.2 与本文 1.3–1.9 的对应表；[CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) 新增「游戏客户端大版本
更新后自检」8 步。**外部经验、本项目待验证**；只写结论未拷代码/未加依赖/未动数据，pytest 不变
（**1054/1**）。细节见 HANDOVER 二·补三十 / HANDOVER_NEXT §4 T9-C0。
**同日 B8（T5④ P 道具条件/效果语义第一批）已完成**（纯离线代码）：新语法 trigger id 从后缀
结构化解析条件（`remaining_turn-N`/`parameter_buff_up-N`/`stamina_up_multiple-N`/
`full_power_point_get_sum_up-N`/…；条件未知 22→**6 件**）+ 指定卡名/手牌张数缺映射
（`trigger_known=False` 103 件/185 段）保守跳过 + 依赖换算「X 的 N% 数值变为 Y」（65 段，
`depends_on`+`percent`）+ 固定/最大体力百分比体力（9 段）+「X 变为 0」（3 段）+ 5 类新触发
（`turn_start_after`/`turn_interval`/`status_gain_interval`/`stance_change`/`stamina_reduce`，
`LessonSim`/`ExpectState` 事件与累计量双镜）；数据层 **445→676/1849 段**（no-op 1404→1173）、
gkbench hif 83 唯一 id **34→59/153 段**；离线 A/B（hif 30 题×2 seed）greedy 3840.7→
**4065.9（+225.2，+5.86%，CI[+86.7,+363.6]，17胜/1负/42平）**、expectimax 3726.4→3921.8
（+195.4，CI 含 0，墙钟噪声）；新增 `tests/test_p_items_b8.py` 19 条，全量 pytest
**1067 passed / 1 skipped（1068 收集 / 77 文件）**，基线 ①③④⑤ 不变。
仍缺：~~持续倍率/modifier 类效果（`ExamLessonValueMultiple` 等）~~ ✅ **B9 已完成（见下）**、
生成卡 `ExamCardCreateId` / 强化状态花费卡、指定卡名/手牌映射、
真机培育侧 P 道具列表、主道具附魔/回忆。细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) /
HANDOVER 二·补三十一 / WORKPLAN B8。
**同日 B9（T5④ P 道具持久倍率 / modifier 类效果，第二批）已完成**（纯离线代码）：按参考引擎
（gakumas-tools BSD-3 `resolveScore` f/g、`resolveCost`、`BuffManager.setScoreBuff(amount,turns)`）
实现 **20 类 target / 369 段 / 298 件道具**——`ExamLessonValueMultiple(+Down)` 持久分数倍率
（加算列表 + 回合末倒计时，作用于出牌分与回合末好印象）、`ExamReviewMultiple`/`ExamReviewCountAdd`
好印象强化/追加发动、热意/集中/好印象/干劲/全力值**增益倍率**、绝好调/不调回合、
`ExamStaminaConsumption*` **费用修正**（永久加减 + 接下来 N 回合 ×0.5/×2）、`ExamExtraTurn`
回合追加、`ExamPreservation`/`ExamConcentration` **指針直给**；同时解析描述里的
「（训练内N次）」→ `max_uses` **9→896 件**（修正 B6–B8 期生效效果可无限触发的口径），
`LessonSim`/`ExpectState` 新字段 + canonical + 双镜全镜像；数据层 **676→1025/1849 段**
（no-op 1173→824）、gkbench hif 83 唯一 id 已实现 **59→103/153 段**；离线 A/B（hif 30 题×2 seed）
greedy 3840.7→**3951.0（+110.3，+2.87%，CI[+39.6,+193.3]，20胜/2负/38平）**、
expectimax +156.2（CI 含 0，墙钟噪声）；新增 `tests/test_p_items_b9.py` 49 条，全量 pytest
**1116 passed / 1 skipped（1117 收集 / 78 文件）**，基线 ①③④⑤ 不变。**保持 no-op 并如实记录**：
`ExamBuffConsumptionAdd`（强化状态花费卡机制不在模型里）、`ExamCardCreateId` 生成卡、
指定卡名/手牌映射。细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) /
HANDOVER 二·补三十二 / WORKPLAN B9。
**同日 B10（T5 剩余①② 生成卡 + 指定卡名/手牌张数映射）已完成**（纯离线代码）：新
`card_meta`（卡名→idol_unique/effect_groups/日文别名；idol_unique 判据
`originIdolCardId`/`originCharacterId` 与参考引擎 pIdol 交叉验证 **340/342、0 误报**）+
`parse_card_search` 结构化触发限定（**play_filter 234 件 / zone_count 27 件**：指定卡名
base id 不限强化 / 偶像固有 / 效果组 / 原本费用 / 类别 / 稀有度 / 手牌·牌堆·弃牌·除外四区
张数含取反）+ **`ExamCardCreateId` 确定式生成卡 11 段**（手牌≥5 不生成 / 牌堆顶 / 弃牌堆，
参考 `addCardTo*` 语义 + 生成卡 id 交叉验证）+ `exam_start_after` 新时机 + **次数上限按
道具计**（`limit:N` 口径修正，多段道具不再提前用完）。触发未知 **103→3 件 / 185→6 段**
（hold 保留区 2 + hotfix 1）、条件未知 **6→0**；数据层 **1025→1042/1849 段**；gkbench
103/153 段（loadout 4 件/8 段原 trigger 未知道具现在真实触发）；离线 A/B（hif 30 题×2 seed）
greedy 3840.7→**4638.2（+797.5，+20.76%，CI[+399.0,+1250.1]，31胜/3负/26平）** /
expectimax 3665.8→**4466.9（+801.1，CI[+66.3,+1697.9]）**（off 与 B9 逐位相同；不可直接比
B9 auto——触发映射+次数口径修正；确定式生成卡不在 hif loadout，① 的 A/B 贡献 0）；
新增 `tests/test_p_items_b10.py` 38 条，全量 pytest **1154 passed / 1 skipped
（1155 收集 / 79 文件）**，基线 ①③④⑤ 不变。**保持 no-op 并如实记录**：随机生成卡
（H.I.F应援棒 6 段 / gkbench 172 段权重，考试 RNG 流未知）、`ExamBuffConsumptionAdd`
（强化状态花费卡，不猜）、hold 保留区张数条件（2 件）。细节见
[RULES_REFERENCE §5.3](RULES_REFERENCE.md) / HANDOVER 二·补三十三 / WORKPLAN B10。
**同日 B2-R（B2 按 B3+ 规则重训）已完成**（纯离线，**可复现负结果**）：旧模型 FAIL 复现
（选择段 −26.1，与 B3 重测逐位一致 → B4–B10 对 small harness 零影响）；2000 叶子快照 vs
`end_turn_state` 逐字段等价探针 + 温存→全力回合边界解除收益快照口径修正
（`RecordingLessonSim._pre_end_turn_stance`，+1 回归测试）；重采 **26,500** beam 全知叶子样本
（纯分数标签、**不加 PBRS 塑形**，auto-gakumas −26,884 负结果同向）→ MLP 104→96→48
（val r²=0.906 / MAE 7.0）；**确认段 120 局 unknown beam 94.9→learned 87.7（−7.2 CI[−9.5,−5.0]）/
known −11.5 / ensemble 0.75 中性**；σ×2/×4 更差（μ 排序本身有害）。**同日高预算验证
（width8/300ms 选择段 80 局）也 FAIL：93.9→89.4（−4.4 CI[−8.8,−0.0]）/ ens 0.75 中性；
收窄主因是解析式基线自己变差（97.3→93.9），learned 绝对分几乎不动 → 学习叶子路线关闭**。
**生产 leaf_model 保持关闭、beam 默认解析式叶子、T2 候选去掉 learned leaf**；重训候选保留
out/，tracked 模型按用户指定回退旧版（两版都 FAIL、生产关闭故行为无差）；根因诊断已完成：
锐利 σ 放大 + 价值-策略失配（EXPECTIMAX B2-R·根因诊断/高预算验证）；
`test_b2_leaf.py` 12 条，全量 pytest **1155 passed / 1 skipped（1156 收集 / 79 文件）**，
基线 ①③④⑤ 不变。细节见 [EXPECTIMAX「B2 重训（B2-R）」](EXPECTIMAX.md) / HANDOVER 二·补三十四/三十五。
**同日 C1 执行层可靠性已完成**（用户指定；纯离线代码+单测，真机验收留阶段 E）：新
`runtime/tapguard.py`（**动作前预算下一帧** TapExpectation + TapGuard 互验：confirmed /
画面已推进 moved 不重试 / 同屏未生效 retap≤2 / **lost 上报绝不静默 SKIP** / 加载暂停帧
postpone；PickerGuard 两段式选牌：选中后只重试确认不重点卡位）+ `device/privilege.py`
（**提权检查**：游戏 elevated/本进程 non-elevated → UIPI 静默丢点击，启动 blocked 拒跑 +
`elevation-blocked` failure + 管理员提示）+ `runtime/trace.py` + `scripts/replay_steps.py`
（**每步可复盘**：`data/step_trace.jsonl` 含动作理由/预算/互验结果，离线逐步复盘）；
`produce_ui.decide()` 每击自动预算（弹窗确认/回合结束「是」/通信错误=dialog-gone）+
card-reward 接 PickerGuard；`auto_produce` 接 tap 互验（**连续 3 次 lost 止损停局**）+
`attempt_drink`（**对话未开**重试槽位≤2，失败留痕）+ 局末 `[tap]` 汇总。参考 GKMSMAA
follow/winpriv 架构**自写不拷贝**（AGPL）。新增 4 测试文件 **68 条**失败场景单测，
全量 pytest **1223 passed / 1 skipped（1224 收集 / 83 文件）**，基线 ①③④⑤ 不变。
细节见 WORKPLAN C1 / HANDOVER 二·补三十六。
**同日 B11 渐退式专家迭代第 1 轮完成**（用户选定启动；纯离线代码+单测）：B2-R 关闭学习叶子
（状态价值）路线后**换目标量**——学 policy/advantage（该打哪张牌/比平均好多少），标签来自
学生自己的对局（**精确重放分支** on-policy 优势 A=R−mean(R)，逐字段全等校验、不走搜索镜像，
绕开价值-策略失配根因）。新 `sim/policy_mlp.py`（137 维=B2 104 状态特征+33 动作特征 →
96→48→1 优势分；`net_action` 硬规矩：有牌绝不 SKIP、无静默回退）+ `sim/policy_data.py` +
`build_ei_dataset.py`/`train_ei_policy.py`/`eval_ei.py`（`eval_known_draw.play` 加 net/greedy，
默认逐位不变）。教师示范 400 局 5747 样本（beam width4/100ms+tiebreak）→ v0 BC（val 排序
命中 0.889）→ v0 自对弈 1000 局 14314 优势样本 → v1 70/30 混合。**确认段 120 局
（seed 3000–3119）v1 97.5 vs beam 教师 94.9：Δ=+2.6 CI[+1.1,+4.1] 显著正 → 评测门 PASS
（按设计放手）**；稳健块 4000–4119 +3.8 CI[+1.6,+6.0]；学生 0.40ms/决策（纯策略无搜索）。
**消融（如实）**：纯 BC v0 也过门（+2.4 CI[+0.7,+4.1]），v1−v0=+0.2 不显著 → 第 1 轮红利
主力=逐决策蒸馏+硬规矩禁跳（教师每回合规划一次会过期/提前 SKIP），on-policy 优势成分
方向正但未独立证明 → 第 2 轮（教师←v1、占比 30→15、加 large 场景）继续验证。
新增 28 条测试，全量 pytest **1251 passed / 1 skipped（1252 收集 / 84 文件）**，
基线 ①③④⑤ 不变。生产接线未做（T2 候选暂不变）；模拟器保真度是天花板、真机 T2 才算数。
细节见 EXPECTIMAX B11 / WORKPLAN B11 / HANDOVER 二·补三十七。
**同日 B11 第 2 轮完成**（用户选定；教师←v1、占比 30→15、large 首测）：
`--teacher-net`/`--baseline-net`/`--round` 纯增量（默认逐位不变）；v1 示范 5773 +
v1 自对弈 14526 优势样本（seed 400000+/300000+）→ v2 17089 样本（占比精确 0.150）。
**确认段 120 局 v2 97.9 vs v1 97.5：+0.4 CI[−0.4,+1.2] → CONTINUE（平台期）**，
选择/稳健 4000/新鲜块 5000 四段全中性；消融 v2−v2_bc=+0.54 CI[−0.40,+1.48] →
on-policy 成分连续两轮方向正、未独立证明。**large 首测（31 张/9 回合）：v1 比 beam
−28.1 CI[−36.0,−20.2]（CLEAR 36.7% vs 53.3%），v2 比 v1 还略差（选择段 −14.8 显著）
→ small 训练不泛化 large**；绝对水位 v2−beam small +2.99 CI[+1.37,+4.62] 保持。
处置：占比不降（保持 0.15）、生产接线未做、T2 候选不变；新增 15 条测试，全量 pytest
**1266 passed / 1 skipped（1267 收集 / 85 文件）**，基线 ①③④⑤ 不变。
细节见 EXPECTIMAX B11 第 2 轮 / WORKPLAN B11 / HANDOVER 二·补三十九。
**同日 B11 r3–r8 继续扶完成**（用户指令「显著强于老师才结束」）：六轮换变量
（数据×10/epochs×3/容量×2/ε-greedy 探索 `--explore-eps`），val 排序饱和 0.862，
确认段七轮恒 +0.2~0.6（**种子段结构，非模型问题**）；**门协议修正（用户批准）：
确认段扩 500 局 3000–3499 → v6 98.6 vs v1 98.1：+0.6 CI[+0.2,+0.9] PASS**，
新鲜块 6000 +1.7 CI[+0.6,+2.8] 佐证，池化 820 局 +0.71 CI[+0.40,+1.02]。
**v6（192×96）= 当前最佳学生，显著强于 v1**；large 泛化显著改善（v6 +14.4 vs v1，
vs beam 缺口 −28.1→−13.7）但仍低于 beam；生产接线仍未做。
新增 7 条探索测试，全量 pytest **1273 passed / 1 skipped（1274 收集 / 86 文件）**，
基线 ①③④⑤ 不变。细节见 EXPECTIMAX B11 r3–r8 续 / HANDOVER 二·补四十。
**同日 B11 v6 生产接线完成**（用户授权综合推荐后选定；纯增量代码+单测，opt-in 默认逐位不变）：
`LessonPolicy(engine="net", net_model=…)` 在可观测状态可出牌里 argmax 优势分（无搜索、
不用 known_draw/牌序，public-safe）；硬规矩有牌绝不 SKIP / 全付不起才 SKIP；缺模型/推理异常/
失配 → `[engine][BLOCKED]`（禁回退 rules）；`eng=net` + 优势分进 reason；auto_produce
`--net-model` > `produce.net_model` > 默认入库 v6（`data/knowledge/ei_policy_v6.json`，tracked，
gate 溯源 meta），缺模型起跑前报错；T2 增第四臂 `--engine net`（large 生产候选仍是 beam，
net 值不值由真机 A/B 定；生产 deck/discard 读不到 → 特征空集，与离线全牌库分布有差，如实记录）。
新增 21 条测试，全量 pytest **1294 passed / 1 skipped（1295 收集 / 87 文件）**，
基线 ①③④⑤ 不变。细节见 EXPECTIMAX「B11 v6 生产接线」/ HANDOVER 二·补四十一。
**同日 B11 r9-large 完成**（用户授权安排；small+large 混合训练，单变量=加 large 数据）：
`train_ei_policy --selfplay/--demos` 多文件纯增量（**单文件 sha256 逐位不变** + 12 条回归测试）；
large 自对弈 5000 局 126969 样本（v6 学生，seed 900000+）+ small r5 全量 145605 + 示范 48101
（补采 v1 1600 局解锁 0.15 上限）= 320675 行，192×96/1200ep 全同 r6。**large500（3000–3499）
r9 315.4 vs v6 285.8：+29.6 CI[+26.2,+33.0] PASS，vs beam 301.3 +14.2 CI[+10.9,+17.5]——
首个 large 显著超 beam 的学生网**（CLEAR 62.6% vs 50.6%；新鲜块 6000 +24.0 独立佐证）；
**但 small500 r9 98.2 vs v6 98.6：−0.42 CI[−0.67,−0.17] 显著回退**（池化 580 −0.47；
vs v1 原门未保持）→ **复合门未过，不入库**：生产 ei_policy_v6.json 保持 r6 权重，
r9 留 out/ 作 large specialist（T2 可 --net-model 换臂）；诊断假设=全局 std 稀释 small
信号（18.71 vs 12.21 → 65%）+ v1 示范拉扯，候选修复=按场景 std 归一化（r10，先问用户）。
新增 12 条测试，全量 pytest **1306 passed / 1 skipped（1307 收集 / 88 文件）**，
基线 ①③④⑤ 不变。细节见 EXPECTIMAX B11 r9-large / HANDOVER 二·补四十二。
**同日 B11 r10 完成**（用户选定；按场景 std 归一化，单变量=归一化口径）：
`train_ei_policy --norm-by-scenario` 纯增量（默认关=逐位不变，4 参照 sha256 改前/改后一致 +
12 条回归测试）；复用 r9 数据 320675 行重训（small std 12.2115 / large 24.0878 各除自身，
vs 全局 18.7065）；能量份额 small 20.9%→49.0% / large 70.9%→42.7%（R9_ANALYSIS 预测吻合）。
**large500 r10 314.9 vs v6 285.8：+29.1 CI[+25.8,+32.3] PASS，vs beam +13.6 仍显著超**
（r10−r9 同 seed 中性 → 增益保持）；**small500 r10 98.38 vs v6 98.64：−0.256 CI[−0.500,−0.012]
仍显著回退**（r9 −0.42 收窄 39%；vs v1 原门恢复 +0.32 CI[+0.03,+0.61]）→ **复合门未过，不入库**：
生产 ei_policy_v6.json 保持 r6 权重；r10 留 out/ei_r10_v10_mix.json。**归一化修复有效但不充分**
（输入侧场景漂移仍在，R9_ANALYSIS §8 证实）；下一候选 r11 叠加 small 上采样（先问用户）。
新增 12 条测试，全量 pytest **1318 passed / 1 skipped（1319 收集 / 89 文件）**，
基线 ①③④⑤ 不变。细节见 EXPECTIMAX B11 r10 / R9_ANALYSIS §8 / HANDOVER 二·补四十三。
**2026-11-24 P1-1 完成**（阶段1 首批，用户确认 A 顺序；纯离线规则+探针，BSD-3 有据）：
**① r10 行为探针**（复用 r9 口径，R9_ANALYSIS §9）——残留 small 回退 −0.256 **已非 v1 风格
贪即时分**（首分歧贪即时分偏置 24:9→11:8、对 v1 耐心比恢复 v6 水平、CLEAR 翻转 1:1 对称）
→ 无方向漂移噪声（通道 2），r11 small 上采样仍对症；**② 全力回合** +1 出牌（连续全力每回合）/
保留牌回手钩子（held 来源留 P1-3）/全力期间禁切指針；**③ のんびり指針** 分数/费用 ×0 +
解除（元気+5/次数+1/熱意+10，→全力 = 全体卡打分成长+10）+ 温存→のんびり不触发温存解除 +
4 族卡预约来源（ExamOverPreservation，CSV 逐卡证据表）+ P 道具 stance_leisure 直给（2 件标注，
触发时机未支持仍保守不触发）；LessonSim/ExpectState 双镜 + 叶子对齐；**评测牌组组成不变**
→ sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，expectimax 仍显著强于 rules）；
旧 B11 数据/模型旧规则口径全保留（阶段2 重采新批再对比）。
新增 `tests/test_p1_stance_rules.py` 36 条，全量 pytest **1354 passed / 1 skipped
（1355 收集 / 90 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.4 / R9_ANALYSIS §9 /
WORKPLAN P1-1 / HANDOVER 二·补四十四。
**2026-11-24 P1-2 完成**（阶段1 第二批，用户确认 A 顺序；纯离线规则，BSD-3 有据）：
**④ handDecrease 抽牌修正**——`cardsToDraw=max(3−Σ handDecrease,0)`（参考
`TurnManager.startTurn` + `BuffManager.setHandDecrease/getHandDecrease`；timed 列表
合算/回合末倒计时/∞永久；**只减回合开始抽牌、卡效果抽牌不受影响**，wiki buffs.json 口径）；
来源=主数据 `ExamGimmickStartTurnCardDrawDown`（塔 gimmick「手牌减少1∞回合」12 段，
exam_start）；nullifyDebuff 拦截未建模如实记。**⑤ pride 自尊**——`resolveScore` f
`min(好印象,干劲)×0.02` 上限+0.5（千分比 min×20/500，与 score_buffs 累加后一次乘；
prideTurns 回合末 -1；score>0 门）；**来源离线可确定**（主数据+参考 DSL 交叉，
pIdol 117/118=雨夜燕）：卡「我、绝不」turn=5、条件门出牌前干劲>=9（trigger 结构化解析，
未知保守不给）+ P 道具「一笔入魂」turn=2/3 + 干劲+4/5（status_gain aggressive &
好印象>=6 & limit1）。LessonSim/ExpectState 双镜 + canonical + 叶子对齐；
sim_produce MODELED 33→34、p_items.json implemented **1042→1056/1849**（modifier 371→385，
仅 14 条记录标注变化）；**评测牌组/gkbench loadout 组成不变**（自尊卡 score 0/SSR 不进池；
94 唯一 loadout id 无 117/tower）→ sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，
expectimax 仍显著强于 rules）；旧 B11 数据/模型旧规则口径全保留（阶段2 重采新批再对比）。
新增 `tests/test_p12_hand_decrease_pride.py` 36 条（既有 no-op 参数表移除已实现类型 −1），
全量 pytest **1389 passed / 1 skipped（1390 收集 / 91 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.5 /
WORKPLAN P1-2 / HANDOVER 二·补四十五。
**2026-11-24 P1-3 完成**（阶段1 第三批，用户确认 A 顺序；纯离线规则，BSD-3 有据）：
**⑥ hold 保留区建模**（CardManager hold/enforceHoldLimit/holdThisCard/holdSelected/
moveHeldCardsToHand）——新 `sim/hold.py`（上限 2 + **13 族卡逐卡证据表**，主数据
ExamCardMove values 恒空 → skill_cards.csv 行号交叉；冲刺/积累 holdThis 温存中、
潜在能力/互动的基础 holdSelected[hand]、切磋琢磨/觉悟/新的舞台/努力了，哦/那一天，在这里
（+2张）/对战请多指教！/让群星散落吧 holdSelected[deck|grave]、爱意彩虹 holdSelected[deck]、
一点一滴的进步 moveHeldCardsToHand；**表外卡保留旧 +1 抽牌近似**不猜）+ 跨回合保留/
holdThisCard 不进弃牌除外/known_draw・discard_order 同步/回手 **LIFO**；
**lockStanceTurns 指針固定**（切磋琢磨 StanceLock turn=1，EOT 递减 + **fresh 保护锁下一回合** +
setStance 守卫 + 全力进入门 lockStanceTurns==0）；**B10 遗留 trigger_unknown 3 件清零**
（hold 区张数条件：实现的觉悟 countCards[held]>=1 ↔ 叶える覚悟；hotfix：咲季营养餐・改
period810_hotfix 三源证实非限定标记 ↔ 咲季の完全食・改）+ **温存 2 段階直给 preservation2**
（7 段）。LessonSim/ExpectState 双镜 + canonical + 叶子对齐；sim_produce MODELED 34→35、
41 元组；implemented 保持 **1056/1849**（机制本就支持，触发保守不解析→真实触发）。
**large 评测牌组组成变化**（冲刺/积累 draw 近似移除，保真度修正；small 不变）→
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，冲刺/积累 未被这 64 局奖励采到；
expectimax 仍显著强于 rules Δ+372.2/+219.1）；旧 B11 数据/模型旧规则口径全保留。
新增 `tests/test_p13_hold_zone.py` 46 条，全量 pytest **1435 passed / 1 skipped
（1436 收集 / 92 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.6 /
WORKPLAN P1-3 / HANDOVER 二·补四十六。
**2026-11-24 P1-4 完成**（阶段1 第四批，用户确认 A 顺序；纯离线，BSD-3 有据）：
**nullifyDebuff 低下状态无效拦截**（P1-2 遗留；参考 Executor executeAssignment :429 /
executeCallAction :507 / executeSpecialAction :545——nullifyDebuff>0 拦截一次 debuff 施加
并 -1，消耗式计数器无回合倒计时）：`LessonSim/ExpectState.nullify_debuff` + canonical +
快照往返 + `intercept_debuff_entries` 纯函数，拦截已建模的 setScoreDebuff/setHandDecrease
（列表逐条）；来源 P 道具侧 `ExamAntiDebuff` values.count **11 段**（偷懒的毛巾
pitem_00-2-116-0 ↔ p_items.csv 317 + 塔 gimmick 初星灯光/旗帜/道具 10 段）。
**⑦ ExamBuffConsumptionAdd 评估保持 no-op**（参考 doubleBuffCostTurns 语义/主数据 4 段
「不息的风暴/迷倒世界的模样±」/gkbench 22 loadout 如实记；**卡模型不承载 buff 花费**——
88 张参考 buff-cost 卡 card_table cost=0、CardSpec 无 buff_cost 字段，无落点不猜）；
**countDebuffs 无落点**（低下状態の数参考+主数据零使用，仅 removeDebuffs 用于「属于我的色彩」）。
卡侧 4 SSR 族来源（values 恒空需逐卡证据表）/标量 DEBUFF_FIELDS 拦截/decreaseFullPowerCharge
留后续。implemented **1056→1067/1849**（+11，modifier 385→396，p_items.json 仅 11 条记录变化）；
评测零落点 → sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，expectimax 仍显著强于
rules Δ+372.2/+219.1）；旧 B11 数据/模型旧规则口径全保留。新增 `tests/test_p14_nullify_debuff.py`
30 条（+test_p13 implemented 断言更新），全量 pytest **1465 passed / 1 skipped
（1466 收集 / 93 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.7 /
WORKPLAN P1-4 / HANDOVER 二·补四十七。
**2026-11-24 P1-5 完成**（阶段1 第五批，用户确认 A 顺序；纯离线，BSD-3 + DSL 三重核实）：
**P 道具剩余效果语义补全（bounded batch）**——层数减少类（干劲/集中/全力值 -= N 夹取 ≥0，
DSL motivation-=1/concentration-=1/fullPowerCharge-=2；全力值独立 PItemDelta.full_power_point_reduce
不计累计）+ 体力减少（ExamStaminaDamage 并入 STAMINA_LOSS，cost-=1 genki==0 穿透）+
好调N回合（ExamParameterBuff turn 列 → condition_turns，DSL goodConditionTurns+=N）+
好调依赖换算（好调的N%数值变为打分/集中，CONVERSION_SOURCES 加 好调:parameter_buff，DSL
score+=goodConditionTurns*0.3）。**留后续**（证据充分需新机制，no-op 如实记）：好调增加量增加/
元气增加无效/不安/塔 gimmick/全力・强气效果卡打分/日文好調の%分。implemented **1067→1164/1849**
（+97）、依赖换算 65→76（p_items.json 仅 24 条记录变化）；**sim_produce 不引用 p_items →
评测零 P 道具结算** → sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，expectimax 仍
显著强于 rules Δ+372.2/+219.1）；旧 B11 数据/模型旧规则口径全保留。新增
`tests/test_p15_reduce_condition.py` 38 条，全量 pytest **1503 passed / 1 skipped
（1504 收集 / 94 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.8 /
WORKPLAN P1-5 / HANDOVER 二·补四十九。
**2026-11-24 P1-6 完成**（阶段1 第六批，用户确认 A 顺序；**T7②③ 离线可靠性工程，
不改考试规则、不作废 B11 数据**）：**⑨ 纯函数状态重放**——新 `data/run_replay.py`
（`apply_event` 无副作用 + 深不可变 `RunState`；**同观测序列两遍重放指纹逐位相等** +
`compare_replays` 逐步比对首个分歧步 + `legacy_events` 旧格式确定式重建 +
`consistency_check` 三方对账）；`RunRecorder` 增量 `events` 观测日志（旧文件续跑先重建）；
`scripts/replay_run.py --verify/--compare`（退出码=DoD）。**⑩ 自动复盘页 + 标注闭环**——
新 `report/review_page.py` 自包含 HTML（逐回合/考试/结算/重放一致性/C1 逐步轨迹/行内标注
导出导入，全量转义+内嵌 JSON 防逃逸）+ `report/annotations.py`（verdict=bad 带 expected →
整态/分类结论**冻结**进 `tests/fixtures/review_regressions.json`）+ `scripts/review_page.py` /
`annotations_to_regression.py`；**auto_produce 局末自动生成**（`[review]`，best-effort）；
样例页 [review_sample.html](review_sample.html)（ep-rule1 真实记录 + 合成演示轨迹显著标注）。
**sim/ 零引用新模块 → 评测零影响、无需重标定**；真实记录端到端 ep-kinami1/ep-rule1/
ep-verify1 三方对账全一致，**ep-t1-g 卡屏局 28 次重复观测被显式 surfaced**。
新增 61 条测试（38+20+3），全量 pytest **1564 passed / 1 skipped（1565 收集 / 97 文件）**，
基线 ①③④⑤ 不变。细节见 WORKPLAN P1-6 / LIVE_RUN §2.1 / HANDOVER 二·补五十。
**2026-11-24 P1-7 完成**（阶段1 第七批，用户选定 P 道具批次；纯离线，BSD-3 + DSL 三重核实）：
**P 道具后续批次（bounded batch）**——好调增加量增加 ExamParameterBuffAdditive → condition_gain
（resolveGoodConditionTurns ×(1+Σbuffs)，夜闇の星 313/314；卡 + P 道具双渠道）+ 元气增加无效
ExamBlockRestriction → nullify_genki_turns / 不安 ExamBlockAddDown → unease_turns（resolveGenki
return / ×0.67 向上取整，∈ EOT_DECREMENT+DEBUFF_FIELDS；いたずらパペット/初陣の証・美鈴/雨上がりの花）+
ExamBlockFix 分离 fixed_vitality（resolveFixedGenki 不受闸门）+ **通用延迟生效**（yaml exam_effect_timer-NNNN
↔ DSL delay:N-1/嵌套 at:turn，EffectManager.decrementDelay；34 段标注，修正おさぼりタオル/美铃/温存变更类
等已实现道具时序）。**保持 no-op 如实记**：塔 gimmick（参考无字段）/塔 ∞ 段（value=0）/全力・强气效果卡
打分（per-card g.score 成长）/日文好調の%分/ExamParameterBuffReduce。implemented **1164→1179/1849**（+15）、
modifier 409→442；**sim_produce 不引用 p_items + genki_gate/condition_gain 无来源恒等 → 评测零影响**，
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，expectimax 仍显著强于 rules Δ+372.2/+219.1）；
旧 B11 数据/模型旧规则口径全保留。新增 `tests/test_p17_genki_condition_delay.py` 48 条，全量 pytest
**1612 passed / 1 skipped（1613 收集 / 98 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.9 /
WORKPLAN P1-7 / HANDOVER 二·补五十一。
**2026-11-24 P1-8 完成**（阶段1 第八批，用户选定 P 道具剩段；纯离线，BSD-3 + DSL 三重核实；
**只改数据层标注 sim/ 零改动**）：**P 道具剩段 bounded batch**——日文好調の%分（天生的才能
pitem_01-3-346-0/1）：DSL 天性の才能 493/494 `score+=goodConditionTurns*0.3/0.5` +
`countCards[hand & baseId(23)]>=1`（眠気卡张数条件 B10 zone_count 已解析，baseId 23↔睡意
p_card-00-acc-0_002）；本批补 `CONVERSION_SOURCES_JA` 日文换算源标注（「Xの%分」），复用 P1-5
依赖换算渠道。**保持 no-op 如实记**：全力・强气效果卡打分（per-card g.score 成长 43 段，values 恒空
需逐卡证据表+新机制，超出 bounded）/塔 gimmick（29 段参考无字段）/ExamParameterBuffReduce
（3 段 produce/buff_consume 触发未支持）。implemented **1179→1181/1849**（+2）、依赖换算 76→78
（好调换算 11→13）；p_items.json 仅 2 条记录变化；**评测零 P 道具结算 + sim/ 零改动** →
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，expectimax 仍显著强于 rules Δ+372.2/+219.1）；
旧 B11 数据/模型旧规则口径全保留。新增 `tests/test_p18_ja_condition_conversion.py` 32 条，全量 pytest
**1644 passed / 1 skipped（1645 收集 / 99 文件）**，基线 ①③④⑤ 不变。细节见 RULES_REFERENCE §5.10 /
WORKPLAN P1-8 / HANDOVER 二·补五十二。
**2026-11-24 阶段2 r11 完成**（P2-0/P2-1/P2-1b，用户选定 A 顺序；**small+large 双过入库，首个双过学生**）：
前置 `sim_engine_ab` 重标定与 P1-8 **逐位一致**（0/32，Δ+372.2/+219.1）+ 参照臂 v6/v1/beam/r9/r10 新规则重评
（**small 规则零分移** v6 98.640/v1 98.062；**large 分移 ±2** v6 287.818/beam 301.612，门基线重定）。
**P2-0 重采**（v6 argmax 新 seed 块）：small 145565（1100000+）/large 128103（1200000+）/v1 示范 51985（1300000+）。
**P2-1** `train_ei_policy --upsample-small 2` 纯增量（13 条回归默认逐位不变）+ `--norm-by-scenario` →
467527 行（small 能量 **65.6%**，§6 候选② ~66% 吻合）；**500 局双门首次双过**：large r11 313.92 vs v6 287.82
**+26.10 CI[+23.06,+29.14] PASS**（vs beam +12.31，新鲜块 6000 +20.81）/ small r11 98.648 vs v6 98.640
**+0.008 CI[−0.253,+0.269] 不回退** / vs v1 **+0.586 CI[+0.245,+0.927] 保持** → **入库 ei_policy_v6.json=r11**
（参照臂逐位 6/6，旧 r6 保留 out/）。**P2-1b 新旧对比**：large headline r11 vs 旧 v6 +28.08 = **学生改进 +26.10（93%）
+ 规则分移 +1.98（7%）**；small 规则零分移；r11 small 显著优于 r9（+0.426，修复 r9 回退）、large 与 r9/r10 中性。
**F public-safe 入场券拿到**。新增 13 条测试 + wiring 入库断言更新，全量 pytest **1657 passed / 1 skipped
（1658 收集 / 100 文件）**，基线 ①③④⑤ 不变。细节见 EXPECTIMAX B11 r11 / R9_ANALYSIS §10 /
WORKPLAN P2 / HANDOVER 二·补五十三。
**2026-11-24 r12 降档 15→0 完成**（P2-2，用户选定 ② r12 续 → A；**单变量=去 v1 示范，零代码改动**）：
r11 配方 `--teacher-frac 0` 无 `--demos` 纯自对弈重训（同新规则数据 + `--norm-by-scenario --upsample-small 2`），
419233 行（small 能量 **69.4%**/large 30.6%/demos 0%），val 排序 0.817，训练 3226.5s。**500 局双门（参照臂逐位 6/6）**：
large r12 314.670 vs v6 287.818 **+26.852 CI[+23.834,+29.870] 主门 PASS**（vs beam +13.058，新鲜块 6000 +21.125）/
**small r12 98.656 vs v6 98.640 +0.016 CI[−0.286,+0.318] 中性（目的门「显著超 v6」下界<0 未达）**/ vs v1 +0.594
CI[+0.188,+1.000] 保持 / r12−r11 small +0.008、large +0.750 均中性 → **目的门未过 → 不入库，生产保持 r11**
（ei_policy_v6.json 未动，r12 留 out/）。**通道 3（v1 示范拉扯）正式关闭**：去教师对 small/large 均无显著影响
（与 §9 行为探针一致）；small 平台期非教师相关，是通道 2 修复后的「学生≈教师」蒸馏天花板。不硬凑显著；
剩候选③两段式微调/探索增量非必需。零代码改动 → 无新测试、wiring 入库断言不变（生产仍 r11），全量 pytest
**1657/1（1658 收集 / 100 文件）**，基线 ①③④⑤ 不变。细节见 EXPECTIMAX B11 r12 / R9_ANALYSIS §11 /
WORKPLAN P2 / HANDOVER 二·补五十四。
**2026-11-24 r13 完整渐退迭代完成（入库为生产）**（P2-3，用户追问「不应该逐渐调老师学生占比吗，让最新的当老师」后选定 A；
**教师←最新入库学生 r11，占比渐退 0.15→0.075，门基线换 r11**）：采 r11 argmax 新自对弈 small 145578（1400000+）/
large 135679（1500000+，**均分 317.8≫v6 288.9**）+ r11 示范 51912（1600000+），449639 行（能量 small 66.4%/large 31.0%/
demos 2.6%），val 排序 0.829，训练 3213.4s。**500 局复合门（参照臂 r11/beam/greedy 逐位 6/6）**：large r13 316.802 vs
r11 313.920 **+2.882 CI[+1.309,+4.455] 主门 PASS（显著超最新老师）**（vs v6 +28.984、vs beam +15.190，新鲜块 6000 +2.783
方向正）/ small r13 98.620 vs r11 98.648 **−0.028 CI[−0.265,+0.209] 不回退**（目的「显著超 r11」未达，蒸馏天花板）/
vs v1 +0.558 CI[+0.172,+0.944] 保持 → **复合门通过 → 入库 ei_policy_v6.json=r13**（1004426 字节，旧 r11 保留 out/）。
**「让最新当老师」对 large 有效**（r11 更优 large 数据→r13 再超，累计 vs v6 +28.984）；**small 维持蒸馏天花板**
（r3–r8 平台期 + r12 通道 3 关闭 + r13 换最新老师仍中性，三重佐证）。wiring 入库断言随 r13 更新（round13），全量 pytest
**1657/1（1658 收集 / 100 文件）**，基线 ①③④⑤ 不变。细节见 EXPECTIMAX B11 r13 / R9_ANALYSIS §12 /
WORKPLAN P2 / HANDOVER 二·补五十五。
**2026-11-24 阶段3 真机首跑（v3.6.1 更新适配 + F#45–47 修复 + T3 管道验通 + 期中第1/900）**（用户选定 T3→T1→T2；
突发游戏更新优先适配）：**v3.6.0→3.6.1** C 盘副本同步 334 文件 + **`gakumas.exe._` DRM 配对修复**（崩溃根因：
壳 exe 读旧解密体→AV；它是配对解密体非备份，同步不可跳过）；hook 45/45、AES key、汉化、登录全验通。
**F#45–47 新 UI 卡点修复**（开场二选一描述层/技能卡强化屏/授课三选一 >> 箭头确认/P饮料详情弹窗，14 条回归）；
`test_ocr_jp_model.py` 活帧改指稳定 fixture。**T3 实时管道✓**（期末 locked_turn=1/config_turns=12/verified=7），
**数据层差 v3.6.1 卡表刷新**（新卡查不到→mismatch，下一会话从新 master 重建卡表）。期中 expectimax **第1/900**
（氷渡香名江·感性）。**T1 待续**（drink-keep 屏 tap-lost 待修 + 期末窗口最小化中断）；**T2 未开始**（beam 臂依赖卡表刷新）。
C1 真机生效（tap 互验/提权/复盘）。全量 pytest **1671/1（1672 收集 / 102 文件）**，基线 ①③④⑤ 不变。
细节见 HANDOVER_NEXT §2/§8.0/§8 / FAILURES #45–47 / WORKPLAN 阶段 E。
**2026-11-25 ep-t31 C+ 调查 + F#48 日文别名修复 + F#49 drink-keep + PRO 难度 opt-in**（用户选定先调查后主线，纯离线不跑真机）：
调查结论——最终评价点 **5493=C+**（公式逐位命中；旧记 B/7404 的 7404 是另一字段，真实评价点字段 110043881.7，
11-20 手动 REGULAR=6750=B）；bot 打 **REGULAR 非 PRO**（期中恰好 900=REGULAR forceEnd 线）；A/10237 参照是 PRO 跨难度不可比；
同难度缺口 −1257=三维 −575（训练）+期末折算 −682（考试）。**修正「卡表过期→beam 停用」假设**：beam 从未启用（全程 expectimax）、
卡表已含新卡，真正根因=**新偶像卡「柔らかな光の中で」日文名查表落空**（汉化 overlay 9/16 滞后，F#48）→ score=0 盲打 + T8 全知停用。
修复：build_card_table 全量 ja_aliases 1765（cards 逐位不变）+ CardTable.get 别名 fallback；T3 离线 sweep **6/6**（期末 12/12）。
**剩期中 T5 重洗 ❌ = 新偶像卡考试内生成卡 grave 15 vs 模型 13（生成卡重洗模型缺口，留后续）**。F#49 drink-keep：OCR 漏读
「还可选择N」→ 点禁用态保留空转 → 改按勾选框扫描补勾。PRO opt-in（produce.difficulty="pro"，默认 regular，坐标待真机实测）。
基线工件恢复 B10 口径 4 场绿（6 场版留 *_v361.json）。全量 pytest **1681/1（1682 收集 / 103 文件）**。
细节见 RUNS「2026-11-25 ep-t31 C+ 疑问调查」/ FAILURES #48–49 / HANDOVER_NEXT §2/§8 / WORKPLAN E1–E3。
阶段 A 全部完成、B1/B2/B3/B4/B5/B6/B7/B8/B9/B10/C0/F0 完成、**B2-R 重训完成（负结果）+
高预算验证完成（仍 FAIL → 学习叶子路线关闭）**、**C1 执行层可靠性完成（代码+单测）**、
**B11 渐退式专家迭代第 1–2 轮 + r3–r8 续完成（r1 PASS / r2 平台期 / **v6 过门显著强于 v1**）+
v6 生产接线完成（engine=net opt-in，T2 第四臂）+ r9-large 完成（large 首超 beam，small 回退 →
复合门未过不入库）+ r10 完成（按场景归一化，small 收窄 39% 仍显著、large 保持 → 仍未入库）+
**r11 完成（阶段2 新规则重采 + small 上采样 ×2 → small+large 双过入库，首个双过学生，F 入场券拿到）**、
**r12 降档完成（去 v1 示范 small 中性 → 通道 3 关闭、不入库保持 r11）**、
**r13 完整渐退入库为生产（教师←r11、占比 0.075，large 显著超 r11 +2.882、small 维持天花板）**、
F 数据已下；
下一步 **按多会话路线图推进**（用户 2026-11-23 晚确认 A 顺序，详见 HANDOVER_NEXT §8.0）：
阶段1 离线补未知（~~全力/のんびり/r10 探针~~ ✅ P1-1；~~handDecrease + pride~~ ✅ P1-2；
~~hold 保留区 + lockStanceTurns~~ ✅ P1-3；~~nullifyDebuff 拦截 + ⑦ buff-cost/countDebuffs 评估~~ ✅ P1-4；
~~P 道具层数减少 + 好调回合 + 好调依赖换算~~ ✅ P1-5（1067→1164/1849）；
~~T7②③ 纯函数状态重放/自动复盘页~~ ✅ P1-6（不改规则/不作废 B11 数据）；
~~P 道具后续批次（好调增加量增加/元气增加无效/不安/通用延迟生效）~~ ✅ P1-7（1164→1179/1849）；
~~P 道具剩段 bounded batch（日文好調の%分 / 天生的才能）~~ ✅ P1-8（1179→1181/1849，sim/ 零改动）；
**阶段1 剩 P 道具后续批次**（塔 gimmick/全力・强气效果卡打分/ExamParameterBuffReduce
——证据充分需新机制/真机，留阶段3）；~~阶段2 重采+练学生 r11（small 上采样，双过入库）+ 新旧对比~~
✅ P2-0/P2-1/P2-1b（**旧学生/老师数据模型全保留不覆盖**；r11 large +26.10 PASS/small +0.008 不回退/vs v1 +0.586
保持 → 入库；新旧对比 large 学生改进占 93%/规则分移占 7%，small 规则零分移）；~~r12 降档 15→0~~
✅ P2-2（去 v1 示范，small +0.016 中性、目的门「显著超 v6」未达 → 不入库保持 r11；通道 3 正式关闭）；~~r13 完整渐退迭代~~
✅ P2-3（教师←r11、占比渐退 0.075、门基线换 r11；large +2.882 显著超 r11 主门 PASS / small −0.028 不回退 / vs v1 +0.558 保持
→ 入库 ei_policy_v6.json=r13；「让最新当老师」对 large 有效、small 维持蒸馏天花板）；**下一任务**：
阶段3 真机 T3→T1→T2（+T6/D1 补采 + E0 + C1 真机验收，net 第四臂用入库 r13）；可选 r14 教师←r13 继续渐退；如仍需 small 显著超老师剩候选③两段式微调/探索增量（非必需））
→ 阶段4 gkbench F1/F2 → 阶段5 收尾 G。**每会话 1–3 任务，开新对话做；旧路线图未完成项已全并入 §8.0**。
需真机数据的缺口（考试 RNG 流 / `ExamBuffConsumptionAdd` 保持 no-op / fresh buff /
附魔 / 真机 P 道具列表）留阶段3（hold 保留区 ✅ P1-3 离线建模；剩 target:held 成长 /
holdCard P 道具来源）→ F1/F2 gkbench 公开对比（ranked 禁 seed，只能交不看 seed 的算法；
B11 学生网只看可观测状态，是未来 public-safe 候选，**r11 双过拿 F 入场券、r13 完整渐退再进（large 显著超 r11）→ 仍须真机 T2 验证**）。
细节见 [HANDOVER.md](HANDOVER.md) 二·补七/二·补八/二·补九/二·补十/二·补十四/二·补十五/二·补十六/二·补十七/二·补十八/二·补十九/二·补二十/二·补二十一/二·补二十二/二·补二十三/二·补二十四/二·补二十五/二·补二十六/二·补二十七/二·补二十八/二·补二十九/二·补三十/二·补三十一/二·补三十二/二·补三十三/二·补三十四/二·补三十五/二·补三十六/二·补三十七/二·补三十九/二·补四十/二·补四十一/二·补四十二/二·补四十三/二·补五十三/二·补五十四/二·补五十五 与 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)。
