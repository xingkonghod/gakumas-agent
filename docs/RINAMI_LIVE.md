# 莉波 H.I.F 本战实机样本（扎易 Frida 采集，2026-11-25 群文件）

> 来源：QQ 群文件 `rinami-hif-w7-w9-live.zip`（16,793 B，sha256 b8d4030a…，用户 QQ UI 下载后提供）。
> 解包在 `data/_rinami_live/`（**不提交**，探针纪律；扎易将上传社区题集）。本文档跟踪。
> 群讨论上下文见 [QQ_GROUP_NOTES §11](QQ_GROUP_NOTES.md)（Frida 可行性文档 +24.9%/+20.8%）。

## 一、样本内容

Windows DMM 客户端 **3.6.1**，普通 H.I.F 本战，偶像卡 `i_card-hrnm-3-017`（姫崎莉波）。
W7/W9 同一次培育。分数为考试原始分。

| 场次 | 回合 | 实机动作 | 饮料使用 | 原始分 | 名次 |
|---|---:|---:|---:|---:|---:|
| W7 上半场 | 9 | 27 | 0 | 655,198 | 1 |
| W9 下半场 | 12 | 45 | 4 | 1,426,865 | 1 |

每场目录五件 + 根两件的 schema：

- `opening.json`：首次决策前 Frida 快照。`parameterScalars.values` 全考试标量（含 **Seed**、
  LimitTurn、体力、审查千分比、各累计计数）；`parameterScalars.currentRandom` =
  `{algorithm: "unity-xorshift32", state}`（**当前 RNG 状态**）；`zones` 有序手牌/牌库/弃牌/除外
  （逐卡 id/强化段/定制段/playCount/affectGrowEffectIds）；`phase`/`decisionReady`。
- `battle-log.json`：客户端结算请求提取的游戏数据——实际动作索引、逐回合日志、三属性分、最终结算
  （`result.examActions` 可读完整动作序列）。
- `execution.jsonl`：Frida 逐步观察。每决策行 `data.rng` = **实机观测 RNG state**、
  `plannedRng` = 当时 Campus 计划值、`action/card/score/good/delta`；时间相对毫秒。
- `result.json`：结算响应该场结果（per-mille 三属性/starBonus/rank/stamina/point/NPC 分）。
- `gkms-loadout.json`：实机开考数据转 GKMS 输入，配 battle-log 做固定牌序重放。
- `gkms-replay-check.json`：**GKMS rev318 / rules v55** 对原实机路线核对——W7/W9 均
  `turnAttributesMatch/rngAtOpeningMatches/orderedHandMatches/orderedDeckMatches=true`、
  `firstDifferentTurn=null`、`replay.diffs=[]`、终分逐位吻合（655,198 / 1,426,865）。
- `README.md`：扎易自述（已去设备标识/采集会话/绝对路径/UI 实例/卡实例 GUID；保留考试种子与主数据 ID）。

## 二、对我们的价值（⑧ 吸收）

1. **M1 考试 RNG 消费图的实机 oracle**：`execution.jsonl` 逐决策 rng state 序列 + opening 全标量/
   有序牌区 = 不依赖引擎源码的黄金夹具（与探针① `data/_engine_probe_rng_p1.*` 同方法论：
   xorshift32 正向迭代数消费）。W7 无饮料纯机制对照、**W9 含 4 饮料 = 饮料（青汁）RNG 消费入口
   线索**（QQ §11 C：扎易"青汁会动rng"、auto-gakumas 直接禁用青汁规避）。M1 阶段1 回归直接用它
   （见 m1-rng 子智能体任务 / [engine-gap M1](../out/_engine_gap_report.md)）。
2. **失锁/deck-modify 对照**：W7/W9 有序牌区逐回合真值可核对我们抽牌模型在牌堆被效果改动后的
   行为（5KZSXANK 同款失锁根因）；`affectGrowEffectIds`/定制段字段补强卡实例建模。
3. **版本漂移如实记**：扎易核对用 GKMS **rev318/rules v55**；我们编译的 oracle DLL 是 **rules=69**
   （`data/_f2sl_tools/kernel/gkmscore.dll`，不重编）。rng 原语已确认一致（xorshift32 13/17/5），
   序列匹配用纯 python 正向迭代；若用引擎核分出现分差，先查版本漂移再查模型，不猜。
4. **Frida 架构吸收**（扎易 22:07 澄清）：**Frida = 与游戏交互的采集层，simulator = 独立外部工具**——
   与我们 **MITM 采集 + 外部 sim/搜索** 同构；差异点：Frida 侵入式（客户端检测风险，QQ §4）vs
   MITM 非侵入；我们 exam_shuffle 13 消费入口建模深度 vs 扎易 nodejs sim 边界未覆盖（自述对账差 100/90 分
   = 浮点累积次序，印证我们 safeCeil + 同累积次序纪律）。**不拷其代码**（zip 仅数据样本）。
5. **搜索收益第三方实证**：同一实机开局 Oracle 新路线 vs Campus 原路线 +24.9%（W7）/+20.8%（W9）、
   规划耗时减半——全知+搜索路线收益的独立实机证据（与我们 v2 +31% ex-seed 同向）。

## 三、纪律

- 样本含考试种子：`data/_rinami_live/` 不提交（同 bench_local 口径）；文档与回归测试夹具
  （若提炼最小夹具进 tests/fixtures/ 需去种子或按现有种子夹具口径）另行决定。
- 不重编 DLL；AGPL 外部用不拷入 src；不碰 D:\Games\Gakumas；C:\GakumasLocal 只读。