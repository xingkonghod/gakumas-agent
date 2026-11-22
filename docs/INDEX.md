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
| 2 | [RULES_REFERENCE.md](RULES_REFERENCE.md) | 结算公式（对照 gakumas-tools）|
| 3 | [MASTER_DATA.md](MASTER_DATA.md) | 真实主数据在哪、字段含义 |
| 4 | [EXPECTIMAX.md](EXPECTIMAX.md) | 搜索与叶子评估 |

### 想继续做真机采集

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 1 | [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) | 结构、配置、四个坑 |
| 2 | [UNLOCK_REPORT.md](UNLOCK_REPORT.md) | 解锁工具怎么工作（端点/加密）|
| 3 | [UNLOCK_ADAPT.md](UNLOCK_ADAPT.md) | hook 机制、版本适配 |
| 4 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 踩过的坑 |

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

### 想了解社区在做什么

| 文档 | 内容 |
|---|---|
| [HIRO_VIDEO_NOTES.md](HIRO_VIDEO_NOTES.md) | hiro-gakumas-hero 的架构（视频 + 仓库）|
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
| **TROUBLESHOOTING.md** | 踩坑记录（采集 9 项 / bot 7 项 / 方法论 4 项）|
| **FAILURES.md** | 真机失败记录（现象→根因→修复→教训）|
| **CAPTURE_PIPELINE.md** | 采集链路：结构、配置、四个坑、已采数据 |
| **MASTER_DATA.md** | 主数据库（286 表）+ seed 发现 |
| **SIMULATOR.md** | 模拟器设计与实现 |
| **EXPECTIMAX.md** | 回合内搜索引擎 |
| **RULES_REFERENCE.md** | 结算公式对照（gakumas-tools）|
| **RULES_FROM_BINARY.md** | 元数据解包结果（枚举/字段/方法签名）|
| **UNLOCK_REPORT.md** | GakumasUnlock 工具分析 |
| **UNLOCK_ADAPT.md** | hook 机制与版本适配 |
| **QQ_GROUP_NOTES.md** | 群讨论记录 |
| **HIRO_VIDEO_NOTES.md** | hiro 项目视频要点 |
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
| **LOCAL_DEPLOY_VIDEO.md** | 本地化部署视频分析 |

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
按用户要求暂不跑真机、先补「我们 vs 别人的差距」：**T4 策略强度**已起步——诊断出档位效用封顶
导致的 beam 平手/存体力偏置，配对评测 beam +14.3/+19.9（CI 均为正），但仍比回合内 expectimax
低 22.3%，T4 决策门未达成（生产 leaf 默认不变；下一步 rollout 叶子估值，详见 [EXPECTIMAX](EXPECTIMAX.md)）。
**2026-11-22 A1 已完成**：OCR 换官方 **PP-OCRv6 small 多语言模型（Apache-2.0）**——日文剧情/选项
完整可读（`ヨーグルトパフェ`/`つくねハンバーグ`/`ドリンクバー` + 整句对白），中文 UI 不受影响；
`scripts/download_ocr_models.py` 下载+sha256 校验，`OcrEngine` 自动加载 `configs/ocr_jp.yaml`
（缺失直接报错，不静默回退中文模型），真机日志 `[ocr] 模型=` 可确认。全量 pytest 926 passed / 1 skipped。
下一步按 [WORKPLAN](WORKPLAN.md)：**离线阶段 A 收尾**（A2 F#42 / A3 F#43 / A4 回放素材 / A5 T3 离线预演）
→ 阶段 B/C/D → 真机 T3→T1→T2 → gkbench 比算法（ranked 禁 seed，只能交不看 seed 的算法）。
细节见 [HANDOVER.md](HANDOVER.md) 二·补七/二·补八/二·补九/二·补十四 与 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)。
