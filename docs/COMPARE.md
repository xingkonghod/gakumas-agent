# 我们 vs 别人的进度对照（口径 / 数字 / 唯一可比路径）

> **目的**：一页回答"我们现在跟 hiro / QQ 群 / 官方 AI 比，走到哪了"。
> 数字来自各文档记录（截至 **2026-11-22**，见文末来源）。**不同口径不能混着比**，
> 先看 §3 的"为什么不能直接比"，再看 §4 的两条可比路径。
>
> 维护：行情更新时只改本文 §1/§2 的数字和"来源"小节；不要把"培育评价 / 考试分 /
> gkbench 原始分 / oracle 比例"混进同一列。

---

## 1. 一句话结论

**信息维度我们领先**（唯一把 MITM `seed → 整段洗牌（含弃牌重洗）→ 生产接线` 打通并逐张验证的一家；
2026-11-22 **F0 又用官方 gkbench 384 组开发种子 `check.hand` 做了外部独立验证：精确 366/384=95.3%、
逐张 97.4%**，選抜 100%）；**真机全自动整局、机制覆盖、公开榜单成绩三块落后**。
2026-11-22 的 B1/B2 补的是"离线策略强度"（评测 bug 修正 + 全知数据学习叶子），
B3 补的是"模拟器回合规则与真机对齐"（每回合基础 1 张 + 跳过回体力 + 取整），
**都还没有转化成真机分数**，所以对外战绩与 11-21 相同。

---

## 2. 分维度对照

### 2.1 真机 / 执行层

| 谁 | 现状 | 关键数字 |
|---|---|---|
| **我们** | bot 能完整跑完一局，但 T1 未验收（目标 ≥C+、≤20 分钟、无 BLOCKED）；决策层修复到 A5/B2/B3 | bot 最好 **C+/5992**（11-15 旧版）；11-21 接管局 **C/4242**（期中 914/第 3）；用户手动 **A/10237**（追赶目标，11-19）、采集局 B/7404 |
| **hiro**（hiro-gakumas-hero，AGPL） | **Mac 成熟**：40+ 局稳定；Windows DMM 版仍在追赶；工程打磨强（纯函数状态、互验、自动复盘） | H.I.F 本战第 1、最高 **1,303,847**；初 REGULAR **A / 10,428**；120 模块 / 600+ 测试 |
| **auto-gakumas**（tactfullotto，无许可证，2026-11-22 新建） | **Android 模拟器（MuMu）ADB + WinRT OCR + MaaFramework**；H.I.F 本戦全自动完走（Home→W7/W9→停机）；零 LLM 主链路 | 实机 live7 **2回戦 +1,594,997**；smoke_v7 W9 T13 结算前 962,352 稳拿第 1；B 站标题宣称 **S4+**（待核）；298 测试（见 [AUTO_GAKUMAS_NOTES](AUTO_GAKUMAS_NOTES.md)） |
| **QQ 群**（群主 Muskot 等） | 微调 **~2B 决策模型** + 魔改 MaaGakumas/macOS 跑完整一局（B 站 demo，约 11-15）；执行层靠 MAA 打磨 | run12（2B，一次前向无搜索）：篠澤広【光景】期中 1st 33,265、期末 **1st 324,063 / SS+ 18,866**（23 选卡 3 reroll，21/22 与参照一致） |
| **官方 AI** | 不跑真机；gkbench 托管算法 | 见 2.2 |

### 2.2 策略强度 / 公开榜单

| 谁 | 路线 | 数字 |
|---|---|---|
| **我们** | 规则 → 回合内 expectimax → 全知 beam → （B2）全知数据 **MLP 叶子**；**生产默认仍 expectimax，学习叶子未上真机** | 离线 small 真实牌组（5 回合 CLEAR120/PERFECT170）：B1 后 within **143.1** / beam unknown **164.0** / known **165.5**；**B2 确认段 120 局（seed 3000–3119）beam 解析式 157.8 → learned 165.5（+7.7，CI [+4.2,+11.2]）/ ensemble 0.5 166.9（+9.0）**，known 同向；选择段 seed 2000–2079：166.8→173.7（+6.8）/ ensemble 174.4（+7.5）。**within 用 learned 变差 −3.3（负结果，只对 engine=beam 有益）**。⚠️ 以上都是 **B3 前旧回合口径**（模拟器每回合 3 张）：B3 后重测 within **89.1** → beam **95.7**（+6.6，CI [+2.2,+11.1]，决策门 107.4% PASS），B2 旧模型**显著变差**（确认段 beam −27.9）需按新规则重训 |
| **我们（本地判官复算别人）** | LessonSim 判官（**非官方 gkbench 判官**，口径见 REPORT*.md） | 48 题×3：expectimax(ensemble) **772.5 > greedy 699.7 > UINet 619.4**（UINet 0.885× 均值 / 0.756× 配对几何）；H.I.F 映射 409×3：UINet 0.9305× / 0.8445× greedy；核心 92×3：ensemble 31,466.9 > greedy 29,885.7 > UINet 27,605.2。**注意：这些是 11-19/20 判官结果，B2 学习叶子未跑此判官** |
| **UIHorizon**（群/公开） | 全知/搜索路线（UIHorizon） | gkbench **631,129（0.5113× oracle）** |
| **UINet**（群/公开） | 端到端策略网络 | gkbench **578,722（0.4551× oracle）**；群内已说"到头了，10× 训练量指标反而倒退" |
| **官方 AI** | 私有原生精确引擎 + 50+ 特征 + 计划重放 + 命令预算 | gkbench **232,710（0.2131× oracle）** |
| **群论文**（花吹雪また一年） | 体系建模 + Bellman/分支定界 + GNRPA（离线最优搜索） | 74 replays 全一致、704 exams 666 匹配；实例 C 141,225→194,962 |
| **auto-gakumas** | **每战在线训练** Maskable PPO（纯 NumPy 2000 eps ~60s，gamma=1.0）+ 每步 **64 次 SO-ISMCTS**（determinized PUCT，value_weight=0.35）；AST 执行 gakumas-data DSL；信息集安全特征（无 seed） | 离线 W9 真卡组 eval30 均值 **477,670**（bestVal 466,850）；PBRS 塑形负结果 **−26,884**（纯分最佳，与我们 B2 负结果同向）；真机数字见 §2.1（**口径不同，不可与 gkbench/我们离线分直接比**） |
| **gkbench 基准分母** | oracle（多起点 best-known） | 均值 **1,452,088**（n=960） |

**2026-11-25 live 榜单快照（`/api/leaderboard?set=hif&kind=template`，全量 960 局可比行）**：
best-known 1,452,088（分母）/ UIHorizon v2.1-Kummer **631,129（0.5113）** / v2.0-Freiheit 636,109（0.5017）/
**UINet Ver2.1-Kummer 578,722（0.4551，纯画面 public-safe 天花板）** / UIHorizon v2.2-Gratwanderung 571,828（0.4604）/
uinet Ver1.1 469,890（0.3740）/ official-ai 232,710（0.2131）/ hiro-rules 95,341 / greedy 87,571 / random 26,436。
⚠️ UIHorizon 系虽高但**从画面反推种子**（sees_seed=true，属「看牌序」类），与纯画面算法不同赛道。

**这几天的新进步（2026-11-25，用户关注「新未知算法」）**：
- **jayalbertzhao 的 PPO 强化学习**（最值得关注）：`uinet-ppo-r1-it19` **575,585**（n=120，rules **67**）、
  r2-it10 567,163、hif-uinet-s1 569,242（rules 65）——在 UINet 上做 RL 微调，已逼近 UINet 2.1（578k），用更新引擎。
- **kirinigh**：`UINet-2.1-fixed-model-TASK-280-Sense-v65` **vs oracle 0.6853**（n=3，rules 65，sense 子集）——
  用户说的「uinet 到上限 68.5%」即此（**口径：vs oracle + rules 65 + sense 子集 + n=3**，与全量 vs best-known 0.455 不同，不可直接比）。
- **shinosawabot 的 Maa 集成**：Maa-UINet-2.1-native-uiobs-v2 280,642（n=8）、maa-public-effects-v1 51,099（n=24）。
- **nvidiaowner 的 hiro-local** 规则（191,269 n=2）、**yzhouwang 的 GHL 启发式**（ghl-sense-buff-value 147,510 n=224）、
  **yuzeis 的 UIHorizon v2.2b**（411,014 n=95）。
- **引擎规则版本分裂**：老榜 rules 59，新提交 rules 65/67（我们 F0 标定 rules 55）——**口径差需要注意**。

**我们的动作（2026-11-25）**：用户选定**先投算法排行试水**（阶段4 F2 提前，纯离线/托管不碰真机）。
投「我们最强 public-safe」= **B11 学生网 r13**（离线 large 316.8 > beam 301.6；beam+全知更强但用种子不能上 ranked）。
托管评测 `needs_gkms=False` 纯画面算法只需 gkbench 包+令牌（引擎在服务器），Windows 可跑。
**F2 适配器**（UIObs→ExpectState→137 维特征→net→动作，自包含打包不 import gkagent）构建中。

### 2.3 信息 / 全知链路

| 谁 | 现状 |
|---|---|
| **我们** | **唯一完整链路**：MITM 采集 → seed → 洗牌模型 **4/4 场整段逐张复现**（18/18、26/26、15/15、27/27）+ **重洗 3/3**（45/29/46 次掷点后逐张）+ 生产接线 `ExamDrawPlan → ExpectState.known_draw/discard_order` **36/36 手牌、29/29 known_draw**；**外部独立验证（F0）：官方 gkbench 384 组开发种子 `check.hand` → 366/384=95.3% 精确、97.4% 逐张（選抜 100%；剩余 18 组全是考试开始加卡机制，非洗牌错误）**；差 T3 真机实时验收 |
| **hiro** | 无 seed/牌序途径（LLM + 规则/搜索） |
| **auto-gakumas** | 无 seed/牌序途径（**纯视觉扫库**： idol 选择长按 + 開始確認詳細滚动扫出牌组/P 道具/回忆词条）→ 特征对牌序置换不变 + ISMCTS determinization |
| **QQ 群** | seed 反推已做出（2^31 枚举+观测剪枝），但**自己定规矩实战不用**；MITM/RNG 讨论 11-21 深夜才刚起，尚未复现牌堆重建+洗牌+决策全链路 |
| **官方 AI** | 私有原生引擎能看真实局面/牌序，但**不可迁移**（gkbench 托管只能用公开信息） |

### 2.4 机制建模 / 工程可靠性

| 维度 | 我们 | 别人 |
|---|---|---|
| 机件覆盖 | B3 回合规则对齐真机；B4 审查倍率客户端公式；B5 熱意+温存解除；B7 P 道具 catalog 1115 件/gkbench 未知 id 清零；B8 条件/效果语义第一批；**B9 持久倍率/modifier（20 类 target/369 段）**；**B10 生成卡确定式 + 指定卡名/手牌张数映射**（card_meta idol_unique 参考交叉 340/342 零误报、play_filter 234 件/zone_count 27 件、触发未知 **103→3 件**、数据层 **1042/1849 段**、greedy A/B **+797.5（+20.76%，CI[+399.0,+1250.1]）**）；仍缺**回忆/附魔**、随机生成卡 RNG、hold 保留区、fresh buff（T5 剩余） | 官方 AI / 群论文最全（但私有/原生）；**auto-gakumas**：AST 执行 DSL 四区守恒 + 费用修正 + P 道具触发 + **回忆 Stage 级限 1**（我们缺的它有）；但无审查倍率分段/熱意独立资源的公开证据 |
| 工程可靠性 | **1154 条测试全绿（1154 passed / 1 skipped，1155 收集 / 79 文件）**、离线评测可复现；真机可靠性（C1：防卡/互验/自动复盘）未做 | hiro：120 模块 / 600+ 测试 / 互验 + 自动复盘页（比我们强）；auto-gakumas：298 测试 + Watchdog/防卡死/完走停机（H.I.F 实机多次完走） |
| 公开榜单 | **2026-11-25 已投稿上榜**：seed-lock+GNRPA（gkagent-seedlock）**hif 均分 944,850，模板榜第 3（仅次 best-known 上限），1.50× UIHorizon 631k**，锁定率 97.8%（sees_seed 看牌序类）；r13 网无seed 归一化 104k（public-safe）；ex 两版跑分中 | UIHorizon / UINet / 官方 AI 有公开排名 |

---

## 3. 为什么不能直接比（口径陷阱）

1. **模式不同**：hiro 的 H.I.F 本战 / 初 REGULAR-PRO 培育、群主 2B 的培育实跑、官方/UIHorizon/UINet 的 gkbench H.I.F 题——难度与评价都不同。
2. **账号/卡组/偶像不同**：hiro 的 A/10,428 换账号不能直接复现；我们追赶目标是用户手动 A/10,237（同账号同卡组）。
3. **是否允许 seed/牌序**：gkbench ranked **禁止**；我们的全知路线只能用于真机/离线研究，**不能**交榜单。
4. **评价公式不同**：游戏培育评价点（C+/B/A…）≠ gkbench 原始分（÷oracle）≠ run12 的考试分（33,265/324,063）≠ 我们的 LessonSim 分数。
5. **我们离线数字是模拟器**：B1/B2 全部在 `LessonSim` small 场景（14 张真实卡 / 5 回合），不是真机整局，也不是考试分。
6. **对手数字会过期**：hiro/群/官方都在动，文档里的数字是"某天的快照"。
7. **auto-gakumas 的 1.59M 是真机 H.I.F 本戦 2回戦原始分**（特定偶像/卡组/账号），与 gkbench 托管判官分（oracle 1.45M）、hiro 的 1.30M、我们的 LessonSim 离线分（B10 auto 4638）**四者互不可比**；其 simQ 1.55M vs 实机 T13 0.96M 也说明其模拟器偏乐观（同我们 B2 教师偏乐观负结果）。其算法只看 UI（无 seed），**理论上可交 gkbench ranked**——后续关注是否提交。

---

## 4. 唯一两条"可比"路径

1. **T2 同环境真机 A/B**（同账号、同卡组、同 setup，各跑一局）：rules / expectimax / beam+全知（+B2 learned leaf）——回答"我们的策略 vs 我们自己的规则/搜索"以及"真机收益是否成立"。
2. **Phase F gkbench public-safe 适配器**（不看 seed、自包含）：回答"我们的算法 vs UIHorizon / UINet / 官方 AI"的**同口径公开分**。

在此之前，任何"我们比 hiro 强/弱"的说法都只能算**分维度判断**，不能算成绩对比。

---

## 5. 我们的领先 / 落后清单

**领先（可复用资产）**
- 全知信息链路（seed→洗牌→重洗→生产接线，4/4 + 3/3 + 36/36 + 29/29；**F0 官方种子外部验证 366/384、逐张 97.4%**）；
- 零 token、纯 Python/Windows 原生；离线可复现评测体系（B1 修评测 bug、B2 配对 CI + 负结果记录）；
- 确定性 `LessonSim` + 286 表主数据，可做机制核验/学习数据生成（B2 的 26.5k 叶子样本就是这么来的）。

**落后（按差距排序）**
1. **真机自动化最后一公里（T1）**：没有稳定 ≥C+ 的整局，其他对外比较都缺前提；
2. **机制建模（B3/T5）**：P 道具已接入离线 loadout 数据并补到上游 1115 件、B8 做了条件/效果
   语义第一批（效果 **676/1849 段**、gkbench **59/153 段**；greedy 配对 A/B +225.2）、
   回忆/附魔/选牌/减益未建模，持续倍率/modifier 类效果与指定卡名/手牌映射待补，
   fresh buff 差一回合 → 学习叶子/搜索的真机收益不可保证；
3. **实时全知（T3）**：离线已通、真机考试验收未做；
4. **真机 A/B（T2）**：三引擎从没同环境比过；
5. **gkbench（Phase F）**：无 public-safe 适配器/公开分。

---

## 6. 下一步（与 WORKPLAN 一致）

```
F0 官方种子校准 ✅（洗牌模型 366/384=95.3%、逐张 97.4%、選抜 100%；起点 stamina/turn/rules 校准）
B3 机制建模 ✅（回合规则/取整已对齐真机 + RULES_REFERENCE 核验表）
B4 T5① 审查倍率 ✅（客户端真实公式 + 屏幕倍率进搜索）
B5 T5② 熱意 + 温存解除 ✅（独立熱意资源 + 出牌次数/固定元気；剩余 fresh buff/P 道具）
B6 T5③ P 道具数据接入 ✅（loadout produce_item_ids → PItemSpec；exam_start + extra_plays；
    离线 A/B hif 30 题×2 seed greedy +128.9）
B7 T9 P 道具 47 条补全 ✅（p_items.json 1068→1115，含 gkbench 11 个未知 id → 83 已知/0 未知；
    结构来自 gkumasu-diff yaml、中文描述缺失处日文+显式标记、条件未知段保守不触发；
    A/B greedy 仍 +128.9 [+9.5,+248.4]）
B8 T5④ 条件/效果语义第一批 ✅（数据层 676/1849；greedy A/B +225.2）
B9 T5④ 持久倍率/modifier 第二批 ✅（20 类 target/369 段；数据层 1025/1849；greedy A/B +110.3）
B10 T5 剩余①② 生成卡确定式 + 指定卡名/手牌张数映射 ✅（触发未知 103→3；数据层 1042/1849；
    greedy A/B +797.5（+20.76%，CI[+399.0,+1250.1]）；pytest 1154/1）
→ 阶段 C 可靠性 / D 数据
→ 阶段 E 真机：T3 实时全知 → T1 整局验收 → T2 三引擎 A/B
→ 阶段 F gkbench public-safe 适配器（ranked 禁 seed，只交不看牌序的算法）
```

> 本会话（2026-11-23）：基线全绿 + **B10 / T5 剩余①②**（生成卡确定式 + 指定卡名/手牌张数
> 映射；card_meta idol_unique 参考交叉 340/342 零误报；触发未知 103→3 件、条件未知 6→0；
> 数据层 **1042/1849 段**；greedy A/B **+797.5（+20.76%，CI[+399.0,+1250.1]）** / expectimax
> +801.1（CI[+66.3,+1697.9]）；38 条新测试，全量 pytest **1154/1（1155 收集 / 79 文件）**；
> 基线 ①③④⑤ 不变）+ **外部情报 auto-gakumas**（[AUTO_GAKUMAS_NOTES](AUTO_GAKUMAS_NOTES.md)：
> Android ADB + 每战在线 PPO + SO-ISMCTS，H.I.F 本戦实机 2回戦 1.59M；无许可证只参考；
> 回忆限 1/干劲守卫/饮料门控为可吸收候选）。见 [HANDOVER 二·补三十三/三十四](HANDOVER.md)。

> 本会话完成：基线全绿 + **T9-B7**（P 道具 catalog 1115 件 / 1849 段、gkbench 未知 id 清零）
> + **T9-C0**（采集/更新断链排障判据进 TROUBLESHOOTING §四 13 条 + CAPTURE_PIPELINE 自检 8 步）
> + **B8 / T5④ P 道具条件/效果语义第一批**（新语法 trigger id 解析、依赖换算「X 的 N% 数值
> 变为 Y」、固定/百分比体力、5 类新触发；数据层 **676/1849 段**、gkbench **59/153 段**；
> 离线 A/B hif 30 题×2 seed：greedy 3840.7→**4065.9（+225.2，+5.86%，CI[+86.7,+363.6]）**、
> expectimax 3726.4→3921.8（+195.4，CI 含 0，墙钟抖动）；新增 `test_p_items_b8.py` 19 条，
> 全量 pytest **1067/1（1068 收集 / 77 文件）**）。仍缺：真机培育侧 P 道具列表、
> 持续倍率/modifier 类效果、指定卡名/手牌映射、主道具附魔。
> 见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md)、[HANDOVER 二·补三十一](HANDOVER.md)。

> 上一会话：基线四条全绿 + **F0 收尾**（官方 gkbench 384 组开发种子核洗牌模型：286 → **366/384=95.3%**
> 精确 / 97.4% 逐张，選抜 100%；剩余 18 组全是考试开始加卡机制、无一洗牌错误；起点校准
> turn=1/score=0/stamina 96.1%=starting_stamina/rules=55 与 commit `f4d9e6e6148d`）。
> 见 [GKBENCH §4.5](GKBENCH.md)、[HANDOVER 二·补二十四](HANDOVER.md)。

> 上一会话：基线四条全绿 + **B2 全知数据 MLP 叶子**（确认段 beam +7.7，只对 engine=beam
> 有益；生产 `leaf_model` 默认关闭）+ **B3 T5 机制建模**（模拟器对齐真机「每回合 1 张 +
> 打完自动结束回合 + SKIP 回 2 体力 + 取整 safeCeil」；RULES_REFERENCE 重写为逐条核验表；
> 真机 39 回合配对回归；重标定后整局 A/B 里 expectimax 显著强于 rules（+342~+429 评价点），
> **B2 旧模型在 B3 规则下失效需重训**）。见 [HANDOVER 二·补二十一](HANDOVER.md)、
> [RULES_REFERENCE](RULES_REFERENCE.md)、[EXPECTIMAX「B3 规则修正与重标定」](EXPECTIMAX.md)、
> [WORKPLAN B3](WORKPLAN.md)。

---

## 7. 来源 / 快照日期

| 内容 | 来源 | 快照 |
|---|---|---|
| 我们的真机成绩 | [RUNS.md](RUNS.md) | 11-15 ~ 11-21 |
| 我们的离线 B1/B2/B3 数字 | [EXPECTIMAX.md](EXPECTIMAX.md)「T4 修正」「B2 学习叶子」「B3 规则修正与重标定」、[RULES_REFERENCE.md](RULES_REFERENCE.md)、`out/b2_eval_*.json`、`out/b3_eval_*.json` | 2026-11-22 |
| 本地判官复算 UINet / H.I.F | `data/bench_local/REPORT.md`、`REPORT_UINET.md`、`REPORT_HIF.md`（gitignore，不在仓库内） | 11-19/20（B1/B2 之前） |
| hiro | [HIRO_VIDEO_NOTES.md](HIRO_VIDEO_NOTES.md)、[HANDOVER §三](HANDOVER.md) | 11-21 |
| QQ 群 / 2B / 论文 | 群情报（已移除）、[GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md) | 11-22 |
| 官方 AI | [OFFICIAL_AI_NOTES.md](OFFICIAL_AI_NOTES.md)、[README §5](../README.md) | 11-19 ~ 11-21 |
| gkbench 公开口径 | [GKBENCH.md](GKBENCH.md)（API/参考分/批量下载）、群情报（已移除）、`data/bench_repo`（MIT 本地克隆） | 11-22（API 抓取） |
| gkbench 官方种子核对（F0） | `scripts/verify_gkbench_shuffle.py`（384 组 check.hand）、[GKBENCH.md §4.5](GKBENCH.md) | 2026-11-22 |
| auto-gakumas | [AUTO_GAKUMAS_NOTES.md](AUTO_GAKUMAS_NOTES.md)（GitHub API 公开 README/交接/manifest/树/扫库样例；未运行未拷贝） | 2026-11-23（仓库 11-22 创建） |
