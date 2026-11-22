# 无画面模拟器（快速训练用）

> 目标：不依赖截图/OCR/3D，只用**卡牌与偶像的数值**跑课程/试镜，
> 用成千上万局的自对弈把「出牌规则参数」调出来，再让真机照这套参数打。
> 一句话：**训练在模拟器，执行在真机。**

## 1. 为什么需要它

真机一局 20 分钟、还要消耗游戏资源；参数（休息阈值、跳过门槛、buff 先铺条件）
换来换去根本没法比较。模拟器一局 <1 秒，可以做参数扫描/自对弈。

## 2. 已有数据（足够起步）

| 数据 | 来源 | 内容 |
|---|---|---|
| `data/knowledge/card_table.json` | gakumasu-diff | 1817 张卡：体力费用、稀有度、方案、效果类型 |
| `data/knowledge/buffs.json` | 学マスwiki | buff 倍率/叠层/出牌顺序 |
| `data/knowledge/mechanics.md` | wiki + B站/NGA | 分数公式：`(卡面值+集中)×好调倍率×(1+上升量)`，再 × スコアボーナス |
| `data/master/produce_cards.json` | 游戏 master | 中文卡名 ↔ ID ↔ 效果文本 |

还缺的：**卡面数值**（打分/元气/好调 的具体数）。`card_table.json` 里
`effects[].values` 目前解析为空，需要补 `ProduceExamEffect.yaml`（同仓库）把
`effectValue1/2` 对上——这是模拟器的第一块砖。

## 3. 模拟器模型（够用就停）

```
LessonState = {turns_left, stamina, score, attribute, hand[], deck[], buffs{condition, focus, impression}}
Action      = play(card_index) | skip
Step        = 应用卡牌效果 → 扣体力 → 更新 buff → 回合结束抽牌/减 buff
Terminal    = 回合用尽 或 体力不足 → 总分 vs 审查基准 → CLEAR/PERFECT/FAILED
```

- 卡效果只建模：打分、元气、好调、集中、干劲、好印象、体力回复、抽牌。
- 其它效果先按"未知=0"处理（不建模也不会比现在真机的启发式更差）。
- 随机性：只保留洗牌；先不做暴击/对手干扰。

## 4. 跨局学习怎么做（不用神经网络）

模拟器跑得快，最划算的是**参数搜索 + 自对弈**：

1. 规则参数化：`policy.json`（跳过门槛、buff 先铺的回合条件、体力预算系数、
   保留体力量、最后回合是否梭哈）。
2. 模拟器里随机/网格采样参数组合，每个组合跑 200 局（同一套卡组）。
3. 指标：`平均分`、`CLEAR 率`、`PERFECT 率`、`平均剩余体力`。
4. 取前几名做**交叉验证**（换一组种子/卡组），胜出的写回 `data/knowledge/policy.json`。
5. 真机的 `LessonPolicy` 读取 `policy.json` 里的参数 → 立即生效。

这就是"越练越强"：**每跑一轮模拟器，参数就更好一点**，而且完全离线。

## 5. 分步交付

| 步骤 | 产出 | 验收 |
|---|---|---|
| S1 | `scripts/sim_core.py`：卡效果解析 + 课程模拟（单局可跑） | 用 `魅力的基础(4费/打分+9)` 能算出单回合分数，单测覆盖 |
| S2 | `scripts/sim_eval.py`：固定卡组跑 N 局，输出均值/方差 | 与真机同一套卡的分数在同一量级 |
| S3 | 参数化 `LessonPolicy`（读 `policy.json`） | 真机行为不变（参数取默认值） |
| S4 | 参数扫描 + 交叉验证，写回 `policy.json` | 模拟器分数提升，且真机一局验证不退化 |
| S5 | 考试/试镜模拟（6 人排名、属性回合、合格线） | 能预测"这把能不能过 3 名" |

## 6. 风险

- 模拟器和真机有偏差（隐藏效果、对手行为）→ 每次参数更新都要真机抽验一局。
- 卡效果数值不全 → 先用"只建模已知效果"，不要凑数。
- 不要把模拟器分数当绝对真理，只用来**比较参数优劣**。


## 7. 2026-11-15 夜间补齐（当前实现状态）

| 机制 | 状态 | 说明 |
|---|---|---|
| 卡面数值 | ✅ | gakumasu-diff 1817 张，94.1% 直接数值 |
| 课程（课程内出牌/好调/集中/好印象/元气） | ✅ | `sim/lesson.py`，11 条单测 |
| 课程目标随进度递增 | ✅ | 前半 100-200，后半 250-300 |
| 课程奖励（每节三选一） | ✅ | 按 打分/体力 选最强，牌组 14→22 张 |
| 支援卡 | ✅ 近似 | 训练倍率 1.35（按真机 Lv40/37/29 折算） |
| 外出事件 | ✅ 近似 | 回体力 + 给一张卡 |
| 删卡 | ✅ 默认关 | 占一整周删 1 张，模型里是负收益（1415→927） |
| 考试（6 人排名+合格线） | ✅ | 第 3 名基准 205，对手 2.9/2.0/1.0/0.99/0.95 |
| 策略参数搜索 | ✅ | `sim_search.py`，7.2 万局 / 3 秒 |
| 单局回放前端 | ✅ | `docs/sim_viewer.html`，选局/单步/播放 |

**当前已知偏差（不要当真理）**
1. 训练增益 75/周、课程成长 0.6×得分、支援倍率 1.35 都是**按少量真机数据拍的**，绝对评价（B/B+）偏乐观；
   模型只适合**比较策略优劣**，不是预测真机分数。
2. 未建模：绝好调、好印象强化、抽牌/再动/追加使用、饮料、P 道具、对手干扰、期中/期末的分数公式细节。
3. 真机属性标定仍是缺口：需要每局记录三维（训练确认界面 `X/1000`），跑 3-5 局拟合。

**下一步（等真机）**：把 `policy.json` 的 produce 参数（lesson_every=1 / rest 8 / outing 16）在真机跑一局，
对比属性三维与评价是否比上一局（632 / 不合格）明显提升。


## 8. 敏感性分析（2026-11-15）：结论坐在刀刃上

`scripts/sim_sensitivity.py` 把 `lesson_gain_ratio` 从 0.20 扫到 0.80，两条曲线：

| ratio | 纯训练 | 能上课就上课 |
|---:|---:|---:|
| 0.20 | 807 | 393 |
| 0.30 | 807 | 590 |
| **0.40（标定值）** | **807** | **788** |
| 0.50 | 807 | 986 |
| 0.60 | 807 | 1184 |
| 0.80 | 807 | 1578 |

**交叉点 ≈ 0.41，而我们标定的值正好是 0.40** —— 也就是说"训练 vs 上课"这个结论
完全取决于那 0.01。原因：现在只有两个真机数据点（W5=361、W12=632），不足以同时定住
"训练增益"和"课程成长系数"。

**要解决**：真机每局记录三维（训练确认界面 `X/1000`），至少再拿 3 个中间点（W3/W8/W10），
才能把两个系数同时定住；或者直接测量"一节课前后属性差 / 这节课得分"得到 ratio。


## 9. 2026-11-15 校准修正：成长系数应为 1.0（三个假设）

真机那局（美铃，三维 632，6 名，终试 180 → 评价点 1507 = E）可以同时被三种模型解释：

| 假设 | 课程成长系数 | 牌组 | 课程均分 | 12 周总和 | 评价点 | 评价 |
|---|---|---:|---:|---:|---:|---|
| A | 1.0 | 弱（不拿奖励） | 89 | 745 | 3060 | C |
| B（旧默认） | 0.4 | 强（拿最强） | 245 | 820 | 3274 | C |
| **C（机制正确）** | **1.0** | **强（拿最强）** | **245** | **2056** | **6861** | **B** |

- 游戏机制里「课程中的パラメータ上昇」就是属性增长，所以系数应当是 **1:1**；
- 真机那局只有 632，是因为它**课程均分只有 60-180**（奖励选牌差、牌组弱），不是系数小；
- 结论：**默认改成 1.0**，把"牌组强弱"作为变量——我们的奖励选牌已经从"按文本估"改成"按卡表选最强"，所以下一局课程均分有机会接近 245，评价点 ~6900 → **B**。
- 敏感性图（`sim_sensitivity.py`）在 1.0 处：上课流 2083 vs 纯训练 806 —— 课程是绝对主力。


## 10. 2026-11-15 可信度审计（外部评审意见吸收）

外部评审指出："LLM 写的模拟器看起来对、算起来错"。审计结果——**这个批评成立**：

| 项 | 结果 |
|---|---|
| 卡表有数值的卡 | 1723 张 |
| 模拟器**真正建模**的卡 | **988 张（57%）** |
| 未建模 | 735 张（好印象 ExamReview 264、抽牌 ExamCardDraw 200、全力 ExamFullPowerPoint 201、温存 ExamPreservation 147、状态附魔 285、计时 282…）|
| 奖励池（限制后） | **125 张**（只留效果类型全在 MODELED_EFFECTS 里的卡）|

**处置**：`build_pool()` 现在只收"效果类型 ⊆ {ExamLesson, ExamBlock, ExamLessonBuff, ExamConcentration}"的卡，
未建模的卡不再被当成 0 分卡混进来（之前 249 张池子里有一半是错的）。修正后总和 1841（原 2068），
评价 B/C+，仍然同量级。

**还缺的（按评审优先级）**
1. **每卡单测**：拿高频卡写"给定状态→断言分数"，没有单测的卡标记不可信（现在是靠效果类型白名单替代）。
2. **Replay 校验**：录真机一局，逐步比对 sim-real 分数曲线，目标误差中位数 <3%（需要开真机）。
3. **分数分布直方图 / 失败归因柱状图**：看 P50/P90 与死因，而不是只看均值。
4. 抽牌/好印象/全力/温存 四类效果建模（能再覆盖 700+ 张卡）。


## 11. 2026-11-15 覆盖率审计 v2（抽牌/好印象已建模）

| 口径 | 开工前 | 现在 |
|---|---:|---:|
| 至少含一种已建模效果（宽松） | 988 / 57.3% | **1283 / 74.4%** |
| 所有效果类型都被建模（严格） | 246 / 14.3% | **355 / 20.6%** |
| 奖励池 | 125 张 | **137 张** |

新建模：抽牌 ExamCardDraw(188)、好印象 ExamReview(253)、好印象依赖分 ExamLessonDependExamReview(85)；
非凡指針（ExamFullPowerPoint 201 / ExamPreservation 147）由 `sim/stance.py` 提供倍率模块，接入 lesson.py 后计入。

**离 90% 还差的元效果**（都是"改变出牌次数/附加状态/延迟触发"这类，建模成本高一档）：
ExamPlayableValueAdd(357)、ExamStatusEnchant(285)、ExamEffectTimer(282)、ExamCardPlayAggressive(204)。

**诊断结论（sim_diag.png）**：输局死因排序——课程没打出分 62%、牌组没成长 51%、四类都没命中 37%、
考试名次不够 0%、体力断档 1%。即**问题是课程产出和牌组成长，不是考试**。


## 12. 2026-11-15 覆盖率审计 v3（指針已接入）

`sim/stance.py` 接入 `lesson.py` 后，`MODELED_EFFECTS` 从 7 类扩到 9 类
（新增 `ExamFullPowerPoint` 全力、`ExamPreservation` 温存）：

| 口径 | 开工前 | v2（抽牌好印象） | v3（+指針） |
|---|---:|---:|---:|
| 宽松（至少一种效果被建模） | 57.3% | 74.4% | **81.8%**（1409/1723） |
| 严格（所有效果都被建模） | 14.3% | 20.6% | **25.0%**（431/1723） |
| 奖励池（rich） | 125 | 137 | **157** |

温存 ×0.5/×0.25、強気 ×2.0/×2.5、全力 ×3.0 的倍率现在在课程模拟里生效，
且本牌不吃自己刚切指針的倍率。

**离 90% 还差**：`ExamPlayableValueAdd`(357)、`ExamStatusEnchant`(285)、
`ExamEffectTimer`(282)、`ExamCardPlayAggressive`(204)——这四类是元效果
（改动出牌次数/附加状态/延迟触发），需要状态机级改动，不是加字段能解决。


## 13. 2026-11-16 卡池更新（1724 → 1817）

**数据源**：`vertesan/gakumasu-diff` main HEAD `a307052d8c8c`（2026-11-16 经本地代理拉取）：

| 文件 | 新大小 | 旧缓存 |
|---|---:|---:|
| `ProduceCard.yaml` | 49,015,507 | 41,274,874 |
| `ProduceExamEffect.yaml` | 34,406,008 | 29,087,391 |
| `ProduceExamStatusEnchant.yaml` | 30,837,327 | 25,874,738 |

本地 `masterTrans` 仍是 v2.3.44 / 2026-09-16，没有新卡中文名；中文名改用
`chinosk6/GakumasTranslationData` v2.3.66（2026-11-15T20:37:16Z）的
`local-files/masterTrans/ProduceCard.json`，据此把 `data/master/produce_cards.json`
从 1724 行更新到 1817 行，再跑 `build_card_table.py` + `fetch_card_values.py`。

**2026-11-16 19:51 复核**：上游最新 release 仍为 **v2.3.66**（asset
2026-11-15T20:37:16Z；`ProduceCard.json` 21,963,119 B，SHA-256
`154c28a7ca6a26987d746d36653775ebbd40a79de82c477362d0903a32b1c36a`），与本节
已用数据逐字节一致；重新下载并重建后仍 **1817** 行，卡名/文本 0 变更，
`card_table.json` 哈希不变，故无需改动卡表。

**差异（逐 (id, upgrade) 对比旧表）**

| 项 | 数值 |
|---|---:|
| 卡数 | 1724 → **1817** |
| 新增 | **93 个变体 = 24 张卡**（23 张 ×4 变体 + Legend「回报恩情的启明星」仅基础） |
| 改动 | **0**（旧 1724 张的 cost/rarity/plan/category/effects/trigger 全部一致） |
| 删除 | **0** |

**24 张新卡**（打分 = 表内直接 `ExamLesson` 值；0 表示得分走全力值/好印象依赖等未建模效果）

| # | 卡名 | 费用 | 打分 | 稀有度 | 方案 | 类型 |
|---:|---|---:|---:|---|---|---|
| 1 | 再出发 | 5 | 10 | Sr | 1 | 主动 |
| 2 | 冲动 | 5 | 10 | Sr | 1 | 主动 |
| 3 | 不自觉的魅力 | 2 | 0 | Ssr | 1 | 精神 |
| 4 | 我的猎物是你哦 | 3 | 10 | Ssr | 1 | 主动 |
| 5 | 竞争原理 | 3 | 0 | R | 1 | 精神 |
| 6 | 安定感 | 4 | 0 | R | 1 | 精神 |
| 7 | 化身为恶魔 | 0 | 0 | Ssr | 1 | 精神 |
| 8 | 天使的微笑 | 5 | 0 | Sr | 2 | 主动 |
| 9 | 雀跃步伐 | 3 | 0 | Sr | 2 | 主动 |
| 10 | 真实的自己 | 7 | 0 | Ssr | 2 | 精神 |
| 11 | 认可我的人 | 6 | 0 | Ssr | 2 | 主动 |
| 12 | 甜蜜陷阱♡ | 5 | 0 | Ssr | 2 | 精神 |
| 13 | 焕彩妆容 | 4 | 0 | R | 2 | 精神 |
| 14 | 罗曼蒂克 | 4 | 0 | R | 2 | 精神 |
| 15 | 全力冲刺 | 5 | 0 | Sr | 3 | 主动 |
| 16 | 干劲全开 | 4 | 0 | Sr | 3 | 主动 |
| 17 | 回报恩情的启明星 | 0 | 0 | Legend | 3 | 精神 |
| 18 | 坚持一件事的可贵 | 7 | 0 | Ssr | 3 | 精神 |
| 19 | 作为结果的现在 | 0 | 0 | Ssr | 3 | 主动 |
| 20 | 一点一滴的进步 | 8 | 0 | Ssr | 3 | 精神 |
| 21 | 粉丝所期望的事 | 7 | 0 | Ssr | 3 | 精神 |
| 22 | 我就是、风！ | 0 | 0 | Ssr | 3 | 主动 |
| 23 | 恶作剧偷心贼 | 5 | 4 | Ssr | 3 | 主动 |
| 24 | 午睡报告 | 4 | 0 | Ssr | 3 | 精神 |

上游 YAML 有 1829 个 `(id, upgrade)` key，比官方 master 多 12 个（3 张卡 ×4 变体）：
`一途な従者` / `忠義を胸に` / `柔らかな光の中で`。这 3 张在 v2.3.66 master 中不存在
（未上线/未本地化），`build_card_table.py` 按官方 master 名匹配时会跳过，故未计入 1817。

**模拟器反馈**

| 口径 | 更新前 | 更新后 |
|---|---:|---:|
| rich 奖励池（max_score=60，排除 SSR） | 204 | **212** |
| legacy 奖励池 | 100 | **104** |
| 800 局 lesson_heavy 三维（歌唱/舞蹈/表现） | 321 / 364 / 305 | 321 / 364 / 305 |
| 三维总和均值 | 990 | 990 |
| 评价点均值 | 4574.4 | 4574.4 |
| P50 / P90 / C+ 率 | 4612 / 4858 / 68% | 4612 / 4858 / 68% |

rich 池 +8 全部来自「再出发」×4 +「冲动」×4；legacy 池 +4 只有「冲动」×4。
两张都是低分/辅助卡，`--rewards best` 从未选中它们，所以 800 局结果逐位相同（不是没读到新表：
池子确实变了）。

**新增卡的未建模效果（覆盖率缺口，对照 `MODELED_EFFECTS`）**

新卡共出现 28 种 effect type，12 种已建模，16 种未建模：

| 未建模类型 | 出现变体数 | 机制 |
|---|---:|---|
| `ExamStaminaRecoverFix` | 12 | 固定体力回复 |
| `ExamStatusEnchantEncore` | 12 | 再演附魔（满足条件自动再用） |
| `ExamForcePlayCardSearch` | 12 | 检索并强制打出卡牌 |
| `ExamLessonFullPowerPoint` | 12 | 累计全力值折算打分 |
| `ExamStatusEnchant` | 9 | 状态附魔外层 |
| `ExamCardMove` | 8 | 手牌/保留/弃牌移动 |
| `ExamEffectTimer` | 8 | 延迟触发 |
| `ExamAddGrowEffect` | 5 | 成长：本卡性能变化 |
| `ExamCardCreateId` | 4 | 生成卡牌（如「睡意」） |
| `ExamEffectTimerEndTurn` | 4 | 回合结束时延迟触发 |
| `ExamEnthusiasticTurnAdd` | 4 | 热意延长 |
| `ExamParameterBuffAdditiveFix` | 4 | 好调增加量追加 |
| `ExamFullPowerLessonMultipleAdditive` | 4 | 全力强化 |
| `ExamAntiDebuff` | 4 | 低下状态无效 |
| `ExamReviewMultiple` | 4 | 好印象强化 |
| `ExamCardPlayAggressive` | 4 | 出牌追加干劲 |

**buffs.json**：并入现有条目「热意」（`zeal`，加 cn「热意」「热意延长」）与「再演」
（`revival`，加 cn「再演」）；新增「全力强化」「好调增加量追加」「成长」3 条，32 → 35 条。


## 14. 2026-11-16 建模 16 种新效果（MODELED_EFFECTS 13 → 29）

16 种全部接进 `sim/lesson.py` + `scripts/sim_produce.py::_effect_fields`，口径逐条写在
`lesson.py` 模块 docstring 与 `_effect_fields` docstring 里。

**精确建模（8）**：`ExamStaminaRecoverFix`（固定回体力、封顶 stamina_max）、
`ExamLessonFullPowerPoint`（出牌前全力值 × 千分比/1000 加进本牌分）、
`ExamStatusEnchantEncore`（本牌直接效果两次）、`ExamReviewMultiple`（回合末好印象分 ×(1000+值)/1000）、
`ExamParameterBuffAdditiveFix`（获得好调时额外 +N 回合）、
`ExamFullPowerLessonMultipleAdditive`（放大全力值折算段）、
`ExamEnthusiasticTurnAdd`（并进好调回合数）、`ExamAddGrowEffect`（第 k 次使用按 1+(k-1)×值/100 计分）。

**保守近似（8，误差方向见 docstring）**：`ExamForcePlayCardSearch` / `ExamCardCreateId` /
`ExamCardMove` → +1 抽牌（有 `ExamPlayableValueAdd` 时不再加，避免 0 费循环）；
`ExamStatusEnchant` → 内层立刻结算；`ExamEffectTimer` / `ExamEffectTimerEndTurn` → 延迟效果立刻生效；
`ExamAntiDebuff` → 课程内 no-op；`ExamCardPlayAggressive` → 干劲（永久近似）。

| 口径（分母 1817） | 改前 | 改后 |
|---|---:|---:|
| 宽松（至少一种效果被建模） | 92.24%（1676） | **97.03%（1763）** |
| 严格（所有效果都被建模） | 34.89%（634） | **74.57%（1355）** |
| rich 奖励池（max_score=60、排除 SSR） | 212 | **260（+48）** |

**单位口径（按卡表 effectValue 实测，不用卡面文字直接当百分数）**

- `ExamLessonFullPowerPoint`：卡面「累计全力值的 100%」对应 `effectValue2=1000`，所以按
  `/1000` 折算。任务文字里的 `/100` 会把 100% 读成 1000%（实测「锻炼的成果」单卡 5 回合
  从 231 → 1631 分；改 `/1000` 后 371 分），故未采用。
- `ExamReviewMultiple` / `ExamFullPowerLessonMultipleAdditive`：`2000` = 卡面 +200%、
  `100` = +10%，按 `(1000+值)/1000` 放大。
- `ExamAddGrowEffect` 的成长量不在已下载的卡表里（`values` 为空，值在
  `ProduceCardGrowEffect` 表），所以真实卡现在 `grow_score=0` 不涨分——机制已实现，等数据。

**800 局 `lesson_heavy` 改前/改后（实测）**

| | 三维总和均值 | 评价点均值 | P50 | P90 | C+ 率 |
|---|---:|---:|---:|---:|---:|
| 改前 | 990 | 4574.4 | 4612 | 4858 | 68% |
| 改后 | 990 | 4574.4 | 4612 | 4858 | 68% |

完全相同的原因：模拟器的 `pick_reward` 按「卡面分/费用」选卡，池里 0 费 60 分的
「汗水与成长+++」本来就是最优且仍在池中；新进池的 48 张最高只有 35/0，挤不掉它，所以
这 800 局的牌组没有变化（不是建模没生效）。受控牌组（势如破竹+++ / 即兴发挥的基础+++ /
决不停歇+++ / 锻炼的成果+++ 各 3 张）用旧解析课程 0 分、新解析课程均分 1345——这批卡
以前在 LessonSim 里效果恒 0，现在能打分了；1345 偏高是因为附魔内层按"立刻结算"近似。
真实奖励选卡走 `CardTable.value`（auto_produce 侧），不在本次改动范围。

## 10. 2026-11-21 深夜：整局引擎 A/B 接线（考试也能注入真 LessonPolicy）

背景：用户规则「**bot 不许回退 rules**」上线后，上真机前先用模拟器验证搜索引擎在
**完整培育局（训练 + 考试）** 里不卡、不回退、分数不崩。

**新增**
- `ProduceSim.exam_policy_fn`（[sim/produce.py](../src/gkagent/sim/produce.py)）：考试内出牌策略
  可注入，默认仍是 `greedy_policy`（历史校准口径不变）。之前考试写死 greedy，导致
  `LessonPolicy` 的考试决策没法在整局里 A/B。
- [scripts/sim_engine_ab.py](../scripts/sim_engine_ab.py)：同一批种子、同一卡组/培育策略，
  逐引擎跑 16 周完整培育局；训练走 `training_policy_fn`、考试走 `exam_policy_fn`，两边都是
  真 `LessonPolicy.decide`。统计：总属性、评价点 P50/P90、C+ 率、考试通过、决策数/SKIP 率、
  `RuleFallbackBlocked` 数、单局耗时。
  ```powershell
  .venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --out out\sim_engine_ab.json
  ```
- 回归：`tests/test_strict_engine_sim.py`（8 周 + 1 场考试，rules/expectimax 都必须
  0 blocked、0 异常、决策数 >10）、`tests/test_sim_produce.py::test_exam_policy_can_be_injected_for_offline_ab`。

**2026-11-22 B3 规则修正后重新标定（16+30+30=76 局）**

B3 把模拟器改成真机规则（每回合基础 **1 张**、打完最后一张自动结束回合、跳过回 2 体力、
取整对齐 `safeCeil`）之后，整局 A/B 的结论**从"噪声内"变成 expectimax 显著更强**：
每回合只出 1 张 → 单张牌的选择价值变大，搜索优势才显现。

| 种子组 | 引擎 | 局数 | 评价点 P50 | 评价点均值 | C+ 率 | 考试过 |
|---|---|---:|---:|---:|---:|---:|
| 9000 | rules | 16 | 5170 | 5134.8 | 100% | 2.00 |
| 9000 | expectimax | 16 | **5566** | **5506.9** | 100% | 2.00 |
| 21000 | rules | 30 | 5176 | 5148.5 | 100% | 2.00 |
| 21000 | expectimax | 30 | **5505** | **5490.3** | 100% | 2.00 |
| 30000 | rules | 30 | 5152 | 5125.2 | 100% | 2.00 |
| 30000 | expectimax | 30 | **5513** | **5554.2** | 100% | 2.00 |

- 76 局：**0 RuleFallbackBlocked / 0 异常 / C+ 率 100% / 0% SKIP**；单局均 0.03–0.05s。
- 配对（同种子，rules 为基线）：expectimax 评价点 Δmean **+372.2 / +341.8 / +428.9**
  （三组，B3 前是 −15.2 / −4.9，属噪声），胜/平/负 15/0/1、26/0/4、29/0/1。
- 非法/局 ≈0.2（引擎选的牌在 `LessonSim` 里偶尔付不起 → 用模拟器合法动作兜底），
  与 B3 前的 G5 机制缺口一致（指針体力修正/元气抵扣口径），不影响"有无回退 rules"结论。
- B3 前的旧数字（rules 5049/expectimax 5063 等）是 **3 张/回合旧口径**，不要再引用。

**已知边界**
- 模拟器没有 UI/OCR/点击，只能证明**决策层**不卡不回退；真机卡屏仍要靠 20 分钟整局验收 +
  `auto_produce --max-minutes 30` 墙钟上限兜底。
- 引擎的牌费模型没建模「指針体力修正/元气抵扣」：引擎选中的牌在 `LessonSim` 里偶尔"
  实际付不起"，A/B harness 记为 `非法/局` 并用模拟器合法动作兜底（属 G5 机制缺口，
  两引擎计数接近，不影响"有没有回退 rules"的结论）。
- B3 后 400 局培育标定带从 650–1100 升到 950–1450（≈1198）：1 张/回合 + 跳过回体力让
  16 周能打更多训练；这是规则口径变化，不代表模拟器与真机属性更吻合
  （起始属性/评价点口径的已知偏差见 [WIKI_DUAL_SOURCE.md](WIKI_DUAL_SOURCE.md)）。

## 11. 2026-11-22 B3：回合规则对齐真机（每回合 1 张 + 追加次数 + 跳过回体力）

**为什么改**：旧模拟器把「一手 3 张」误读成「一回合能出 3 张」（真机是**选 1 张**）。
A2（F#42）已把生产搜索改成 1 张；B3 把模拟器/评测/整局 A/B 全部对齐，否则离线数字
与真机不是一个规则。

**改了什么**（详见 [RULES_REFERENCE.md](RULES_REFERENCE.md) §1/§5）：
1. `LessonConfig.plays_per_turn` / `ExpectState.play_limit` / `UIObs.DEFAULT_PLAY_LIMIT`
   默认 **3 → 1**（`sim.lesson` / `sim.expectimax` / `sim.play_choice` / `sim.uiobs` /
   `sim.v_leaf` / `scripts/local_bench.py`）；
2. **打完最后一张自动结束回合**（参考引擎 `CardManager.useCard` 末尾）；
3. **回合结束还有剩余次数（SKIP）→ 体力 +2 封顶**（参考引擎 `TurnManager.endTurn`）；
4. **取整对齐** `safeCeil`：buff 段 ceil 一次、回合属性倍率再 ceil 一次
   （旧：课程 floor / 考试结尾 round 一次；实机回放黄金值 9→23、5→8、2→3 等）。
5. `scripts/export_t5_turn_rules.py` + `tests/fixtures/t5_exam_turn_rules.json`：
   真机 4 场考试 39 回合的回合规则配对回归素材；`tests/test_t5_turn_rules.py` 9 条。

**影响**：
- 所有离线评测/自对弈/A/B 的**绝对分数与旧文档不可比**（同 scenario 每局出牌数从 15 → 5 左右）；
- `sim_engine_ab` 结论质变（expectimax 从噪声内变成显著更强，见 §10）；
- B2 学习叶子是在旧口径数据上训练的，B3 后重测显著变差 → **必须重采数据重训**
  （见 [EXPECTIMAX.md](EXPECTIMAX.md)「B3 规则修正与重标定」）；
- 400 局培育标定带 650–1100 → 950–1450（口径变化，见上）。



## 15. 2026-11-22 B5：熱意（enthusiasm）+ 温存解除（MODELED_EFFECTS 29 → 32）

**机制**（参考引擎 gakumas-tools BSD-3 `constants.js`/`resolvers.js`/`TurnManager.js` + 官方 wiki）：

- **熱意 = 独立整数分数资源**：出牌分在集中加算之后、好调/指針倍率之前
  `score += 熱意 × 本牌熱意適用倍数`；获得量 `(熱意追加 + N) × (1 + 熱意増加‰)`，
  获得时向上取整（`WHOLE_FIELDS` ceil）；回合末归 0，有「熱意延長」则保留并 -1；
- **温存解除**：1 段階 → 熱意 +5、出牌次数 +1；2 段階 → 熱意 +8、固定元気 +5（不吃やる気）、
  出牌次数 +1；同回合重复解除可叠加；温存→温存2 升级不触发；温存→全力的回合边界切换也触发；
- **来源**：`ExamEnthusiasticAdditive`（熱意追加 buff）/ `ExamEnthusiasticMultiple`（熱意増加‰ buff）/
  `ExamEnthusiasticTurnAdd`（熱意延長）/ `ExamMultipleEnthusiasticLesson`（本牌熱意適用倍数 ×2）。

**改动**：`sim/enthusiasm.py` 纯规则；`LessonSim`/`ExpectState` 熱意字段与算分、卡牌 buff、
回合末清零/延長、回合边界解除（旧「温存解除≈好调回合」`_save_cards_used` 删除）；
`CardSpec` 新增 6 个熱意字段；`sim_produce._effect_fields`（MODELED_EFFECTS 29→32）与
`play_choice._effect_fields` 生产卡表映射。

**回归**：`tests/test_t5_enthusiasm.py` 16 条；全量 pytest **1023 passed / 1 skipped
（1024 收集 / 74 文件）**。未建模：のんびり指針、全力回合额外出牌/保留牌、P 道具/附魔来源、
生产读屏未读熱意（每步按回合开始 0 估）。细节见 [RULES_REFERENCE §5.2](RULES_REFERENCE.md) /
HANDOVER 二·补二十六。

### 11.4 T5③ 2026-11-22：P 道具数据接入（exam_start + extra_plays）

- **数据层**：`src/gkagent/data/p_items_db.py`——对局 loadout 的 `produce_item_ids`
  精确匹配 `data/knowledge/p_items.json`（1068 件，2026-09-16 快照）；未知/重复 id
  显式上报、缺数据抛 `PItemDataUnavailable`；真实来源 = gkbench 505 题模板（83 唯一 id /
  72 已知 / 11 未知），离线 A/B 用 `scripts/local_bench.py --p-items auto/off`。
- **新触发时机 `exam_start`**：`LessonSim.__init__` 在抽第 1 手牌**之前**结算一次
  （`_fire_p_items(EXAM_START)`），随后 `_draw_hand(keep_extra_plays=True)` 触发 turn_start
  ——顺序「训练/考试开始 → 回合开始」；exam_start 给的额外出牌次数属于第 1 回合。
- **新效果 `ExamPlayableValueAdd → extra_plays`**：`PItemDelta.extra_plays`，
  `LessonSim._fire_p_items` / `ExpectState.fire_p_items` 都加到当回合额外次数
  （卡效果同口径，见 §11 的 B3 回合规则）。
- **覆盖率（如实）**：catalog 1764 段 spec 已实现 421 段；gkbench 已知道具 131 段 spec
  实现 31 段。未实现 `effect_type` 仍是 no-op（不抛异常、报告里统计）。
- **回归**：`tests/test_p_items_db.py`（10）/ `test_p_items_integration.py`（+4）/
  `test_local_bench.py`（+4）；离线 A/B hif 30 题×2 seed 配对：greedy +128.9（+3.36%）、
  expectimax +149.6（+3.98%）。细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) /
  HANDOVER 二·补二十七。
