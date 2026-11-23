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
| 3 | [QQ_GROUP_NOTES.md](QQ_GROUP_NOTES.md) | 社区怎么反推 seed 的（信息论口径）|
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
| [QQ_GROUP_NOTES.md](QQ_GROUP_NOTES.md) | 群里的技术讨论 |
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
| **RULES_REFERENCE.md** | **规则核验表**（回合规则/结算顺序/取整/buff/牌序，对照 gakumas-tools + 真机）|
| **RULES_FROM_BINARY.md** | 元数据解包结果（枚举/字段/方法签名）|
| **UNLOCK_REPORT.md** | GakumasUnlock 工具分析 |
| **UNLOCK_ADAPT.md** | hook 机制与版本适配 |
| **QQ_GROUP_NOTES.md** | 群讨论记录 |
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
known −11.5 / ensemble 0.75 中性**；σ×2/×4 更差（μ 排序本身有害）。**生产 leaf_model 保持关闭、
beam 默认解析式叶子、T2 候选去掉 learned leaf**；模型文件替换为新口径（旧版 git 历史保留）；
`test_b2_leaf.py` 12 条，全量 pytest **1155 passed / 1 skipped（1156 收集 / 79 文件）**，
基线 ①③④⑤ 不变。细节见 [EXPECTIMAX「B2 重训（B2-R）」](EXPECTIMAX.md) / HANDOVER 二·补三十四。
阶段 A 全部完成、B1/B2/B3/B4/B5/B6/B7/B8/B9/B10/C0/F0 完成、**B2-R 重训完成（负结果）**、F 数据已下；
下一步 **T5 剩余**（~~生成卡确定式/指定卡名映射~~ ✅ B10；剩随机生成卡 RNG / `ExamBuffConsumptionAdd`
保持 no-op / hold 保留区；**fresh buff 差一回合**需真机逐回合截图；均低价值或需真机/补采）
或 **C1 执行层可靠性** → 阶段 C1/D（T9 只剩 **E0** 需真机独立副本实验，先问用户）
→ 真机 T3→T1→T2 → F1/F2 gkbench 公开对比（ranked 禁 seed，只能交不看 seed 的算法）。
细节见 [HANDOVER.md](HANDOVER.md) 二·补七/二·补八/二·补九/二·补十/二·补十四/二·补十五/二·补十六/二·补十七/二·补十八/二·补十九/二·补二十/二·补二十一/二·补二十二/二·补二十三/二·补二十四/二·补二十五/二·补二十六/二·补二十七/二·补二十八/二·补二十九/二·补三十/二·补三十一/二·补三十二/二·补三十三/二·补三十四 与 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)。
