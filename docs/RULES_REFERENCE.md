# 参考引擎的规则（对照我们的模拟器）

来源：`surisuririsu/gakumas-tools`（**BSD-3**，本地在 `data/dl/gt/gakumas-tools-master`）
文件：`packages/gakumas-engine/engine/Executor/resolvers.js` 的 `resolveScore()`

这是公开可参考的**权威结算实现**（GameVika 的计算器直接移植它，25/25 黄金用例）。

## 打分结算顺序（原文逻辑）

```
resolveScore(state, score, growth, rhs, getTurnMultiplier)

① growth 加成（考试中成长）
   - 若效果引用 goodImpressionTurns → score += 好印象层数 × growth[scoreByGoodImpressionTurns]
   - 否则若引用 motivation       → score += やる気 × growth[scoreByMotivation]
   - 否则若引用 genki            → score += 元气 × growth[scoreByGenki]
   - 否则有 growth[score]         → score += growth[score]

② if score > 0:
   a. score += 集中 × 集中倍率 × 集中效果加成之和            ← 集中是「加」
   b. score += 热情 × 热情倍率
   c. score = ceil(score)                                   ← 第一次取整
   d. 好调：score *= 1 + (0.5 + (绝好调 ? 好调回合数×0.1 : 0)) × 好调倍率
   e. 指針：
        強気1段 ×2 · 強気2段 ×2.5
        温存1段 ×0.5 · 温存2段 ×0.25
        全力   ×3
        余裕   ×0
   f. score *= 1 + 分数增益之和（含 自尊 min(好印象,やる気)×0.02 上限0.5）
        メタモルフォーゼ「披露」额外 +0.25
   g. score *= max(分数减益之和, 0)（メタモルフォーゼ「支度」基础 0.75）
   h. 不调：score *= 0.67
   i. 取整

③ × 回合属性系数（turnMultiplier，考试里就是 Vo/Da/Vi 倍率）
```

## 和我们模拟器的差异（实测对照）

| 项 | 参考引擎 | 我们的 `LessonSim` | 影响 |
|---|---|---|---|
| **集中** | `score += 集中 × 集中倍率 × 加成`，**加在乘之前** | 同（加在乘前）| ✅ 一致 |
| **好调倍率** | `1 + (0.5 + 绝好调? 回合数×0.1 : 0) × 倍率` | 固定 ×1.5 | ❌ **我们少了回合数增长项** |
| **やる気** | 加在基础分上 | 未建模 | ❌ 缺 |
| **取整时机** | 加算后取整 → 乘完再取整 → 乘回合系数 | 只在最后取整一次 | ⚠️ 有 1-2 分误差 |
| **不调** | ×0.67 | 未建模 | ❌ 缺 |
| **メタモルフォーゼ** | 披露 +25% / 支度 ×0.75 | 未建模 | ❌ 缺（氷渡香名江就是这个偶像！）|
| **指針倍率** | 1段/2段都建模（0.5/0.25、2/2.5）| 之前只建 0.5/2/3 | ⚠️ 2 段缺 |
| **自尊（pride）** | `min(好印象,やる気)×0.02` 上限 +0.5 | 未建模 | ❌ 缺 |
| **回合属性系数** | 每次乘 | 只在考试用 4.11 | ⚠️ 课程里应为 1.0 |

## 最该补的三条（对真机影响最大）

1. **好调倍率随回合数增长**：我们固定 1.5，实际是 `1 + (0.5 + 0.1×好调回合数)×倍率`（绝好调时）。
   这解释了为什么我们模拟的课程分数偏低。
2. **メタモルフォーゼ（披露/支度）**：氷渡香名江的核心机制，+25% / ×0.75，我们完全没建模。
3. **不调 ×0.67**：部分卡会给不调，我们当没有。

## 其他可参考的文件

| 文件 | 内容 |
|---|---|
| `engine/BuffManager.js` | buff 层数管理与回合衰减 |
| `engine/CardManager/index.js`（50KB）| 出牌可用性、费用修正、卡效果 |
| `engine/TurnManager.js` | 回合推进、抽牌、弃牌、洗牌 |
| `engine/Executor/resolvers.js` | **所有效果的结算函数**（元气/集中/好印象/费用…）|
| `strategies/HeuristicStrategy.js`（15KB）| 他们的启发式策略（可对照我们的规则引擎）|

## 许可

`gakumas-tools` 是 **BSD-3-Clause**，可以引用/改写，需要保留版权声明。
