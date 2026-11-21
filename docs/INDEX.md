# 📖 新对话从这里开始

> **第一句话这样说**：
> 「读 `docs/INDEX.md`，然后按里面的清单继续做」
>
> 本文件只做**导航**，不写内容。具体内容在各专题文档里。

---

## 一、按任务查文档

### 想继续做「拿 seed / 完全信息」

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 1 | [HANDOVER.md](HANDOVER.md) | 现状 + 下一步（**先读这个**）|
| 2 | [MASTER_DATA.md](MASTER_DATA.md) | 主数据库怎么建的、seed 字段在哪 |
| 3 | [QQ_GROUP_NOTES.md](QQ_GROUP_NOTES.md) | 社区怎么反推 seed 的（信息论口径）|
| 4 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 采集链路的坑（改之前必看）|

### 想修 bot（出牌/点击/卡死）

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 1 | [HANDOVER.md](HANDOVER.md) | 当前 bot 状态 |
| 2 | [FAILURES.md](FAILURES.md) | **真机失败记录**（现象→根因→修复→教训）|
| 3 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 屏幕识别/点击类的坑 |
| 4 | [LIVE_CHECK.md](LIVE_CHECK.md) | 真机检查清单 |

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
| **HANDOVER.md** | 项目现状 + 下一步 + 路径速查 + 坑 |
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
确定性重洗钩子）+ **`lesson.engine="beam"` 跨回合规划选项**。下一步：采集进程 ↔ 决策进程实时打通
（traffic.jsonl → policy 进程）+ 真机 A/B。** 细节见 [HANDOVER.md](HANDOVER.md) 二·补五。
