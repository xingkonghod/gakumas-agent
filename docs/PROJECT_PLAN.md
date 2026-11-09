# Gakumas Decision Engine（GDE）项目规划 v0.2

> 定位：**MAA 的决策外挂**，不是另一个 MAA。
> 一句话：MAA 负责看和点，GDE 负责“这手牌该怎么打、这条路该怎么走、为什么”。

---

## 1. 为什么不是“又一个 MAA”

MaaGakumasu 已经把“手和眼”做得很完整：截屏、模板/YOLO 识别、点击、日常、商店、工作、社团、启动游戏、DMM/汉化适配。再做一个同样的东西，只是重复劳动，而且维护不过它。

GDE 只做 MAA 做不了/做不深的部分：

| 能力 | MaaGakumasu | GDE |
|---|---|---|
| 截屏/点击/日常 | ✅ 完整 | ❌ 不做，直接复用 |
| 手牌识别 | 只分 `suggestions/cards/useless` | ✅ 识别到**卡 ID、费用、效果** |
| 出牌决策 | 启发式：有推荐打推荐，否则打一张 | ✅ 模拟搜索 + 价值网 + 学习 |
| 长程规划 | 弱（事件/道具/饮料多为规则） | ✅ 培育路线、道具时机、考试策略 |
| 竞赛 | 选一个对手打 | ✅ 对手/卡组/分数期望建模 |
| 复盘 | 日志 | ✅ 每步回放、反事实“如果打 X 会怎样” |
| 学习 | 无 | ✅ BC → 自对弈 → 蒸馏 → ONNX |
| 低 token | 不涉及 | ✅ 规则/搜索 0 token，LLM 只兜底 |
| 汉化/日常/更新 | ✅ | ❌ 不碰 |

**结论**：GDE 是插件/外挂/教练，不是替代品。

---

## 2. 三种共存模式

### 模式 A：教练模式（最安全，先做）

```
MaaGakumasu 正常跑
        │  同一窗口
        ▼
GDE 只读：截屏 → 识别 → 推荐动作 → 写日志/悬浮提示
        │
        └─ 不点击、不改 MAA、不抢焦点
```

- 用途：收集数据、对比“GDE 推荐 vs MAA 实际动作”、验证识别。
- 风险：最低；不影响现有自动化。
- 交付：`scripts/run_coach.py` + 每日对比报告。

### 模式 B：插件模式（核心）

在 MaaGakumasu 的 `agent/custom/action/` 里加一个自定义动作：

```python
@AgentServer.custom_action("GkAgentCardsAuto")
class GkAgentCardsAuto(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        image = context.tasker.controller.post_screencap().wait().get()
        reco = context.run_recognition("ProduceRecognitionCards", image)
        obs = build_observation(reco, context)       # GDE 适配层
        action = gde.act(obs)                         # 本地策略服务
        context.tasker.controller.post_click(*action.point).wait()
        return True
```

- 复用 MAA 的截屏、识别节点、点击、任务调度。
- 只替换 `ProduceCardsAuto` 的决策部分。
- 通过配置开关：`cards_policy: maa | gde`，可随时回退。
- 许可证：MaaGakumasu 是 AGPL-3.0，插件一起分发需 AGPL；个人使用不受影响。

### 模式 C：独立竞赛（可选）

MAA 不跑的时候，GDE 自己截屏/点击，只打竞赛。
不作为主路径，避免和 MAA 抢输入。

---

## 3. “深入”的路线：从出牌到策略

| 层级 | 能力 | 依赖 | 产出 |
|---|---|---|---|
| L1 | 出牌建议（shadow） | MAA 识别结果 | 推荐日志、准确率 |
| L2 | 卡 ID/费用/效果识别 | 卡图模板 + OCR | 真正的 hand state |
| L3 | 模拟搜索出牌 | 竞赛模拟器 | 期望分最高的牌序 |
| L4 | 价值网 + 蒸馏 | 搜索数据 | <5ms 的 policy/value |
| L5 | 培育路线规划 | 培育模拟器 | 事件/道具/饮料/考试策略 |
| L6 | 竞赛对手/卡组建模 | 对战日志 | 选对手、调卡组 |
| L7 | 持续学习 | 回放库 | 每周灰度更新 |

> 先 L1–L3，能打；再 L4，变快；L5–L7 是护城河。

---

## 4. 架构

```
┌──────────────────────────────┐
│ MaaGakumasu（手和眼）         │
│  截屏 / 识别 / 点击 / 日常    │
└──────────────┬───────────────┘
               │ custom_action / custom_recognition
               ▼
┌──────────────────────────────┐
│ GDE（脑子）                   │
│  adapter → contract → policy  │
│  rules → search → value → LLM │
│  replay / metrics / safety    │
└──────────────┬───────────────┘
               │ 离线
               ▼
┌──────────────────────────────┐
│ sim / training               │
│  竞赛/培育模拟器 → BC/RL/蒸馏 │
└──────────────────────────────┘
```

### 4.1 GDE 内部模块

- `integration/maa.py`：把 MAA 的 recognition 结果转成 `Observation`；把 `Action` 转成点击坐标。
- `contract/`：Observation/Action/Replay（已有）。
- `policy/`：规则、搜索、价值网、LLM 兜底、路由。
- `sim/`：竞赛/培育环境（自研 clean-room）。
- `training/`：BC、PPO/AlphaZero、蒸馏、ONNX。
- `eval/`：模拟器基准 + 教练对比报告。
- `runtime/`：回放、指标、熔断。

### 4.2 决策路由

```
Observation
 ├─ 规则/宏命中 → 动作（0 token, <1ms）
 ├─ 战斗/考试 → 模拟搜索（0 token, 5–20ms）
 ├─ 未知界面/文本 → 本地 3B LLM（50–200 token, 缓存）
 └─ 都不匹配 → 停住，交给 MAA/人工
```

---

## 5. 里程碑（8–10 周）

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 ✅ | 契约、Env/Policy 接口、Loop、回放、测试 | 5 passed |
| P1 | MAA 适配层 + 教练模式（只读） | 100 局推荐日志；状态字段准确率 >95% |
| P2 | 卡 ID 识别 + 竞赛模拟器 + 规则基线 | 模拟器胜率 > 随机；单步 <5ms |
| P3 | 搜索策略（expectimax/MCTS） | 比规则 +10%；p95 <20ms |
| P4 | 插件模式 `GkAgentCardsAuto` | 可开关；与 MAA 原逻辑 A/B |
| P5 | 价值网 + 蒸馏 + ONNX | 学生达教师 90%；<5ms |
| P6 | 培育路线规划 | 完整一局；token <2 万 |

**先做 P1**：不改 MAA 一行代码，只读、只记录、只推荐。

---

## 6. 指标

| 类别 | 指标 | 目标 |
|---|---|---|
| 决策 | 模拟器期望分/胜率 | 逐阶段提升 |
| 教练 | 与 MAA 动作一致率 | 先观测，不设目标 |
| 识别 | 卡 ID/费用准确率 | >98% |
| 延迟 | 策略 p95 | <10ms |
| 成本 | 日常 token | 0 |
| 成本 | 单次培育 token | <2 万 |
| 稳定 | 插件异常率 | <1% |

---

## 7. 风险

- **封号**：点击仍违反 ToS；先教练模式，插件模式限速、可随时关。
- **和 MAA 抢输入**：插件模式必须走 MAA 的 controller，不自己点。
- **许可证**：MaaGakumasu AGPL；插件分发需 AGPL，个人使用不受限。
- **模拟器偏差**：gakumasu-diff 同步； nightly 回归。
- **识别错误**：置信度阈值；低置信度交给 MAA 原逻辑/停住。

---

## 8. 关键决策（ADR）

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-001 | 不做日常/商店/点击层 | MAA 已做好，重复无价值 |
| ADR-002 | 以 MAA custom_action 为第一集成点 | 复用识别/点击，改动最小 |
| ADR-003 | 先教练模式 | 零风险验证识别与推荐 |
| ADR-004 | 先竞赛后培育 | 回合短、模拟成熟 |
| ADR-005 | 规则+搜索优先，RL 后置 | 确定性方案已被 STS 项目验证 |
| ADR-006 | LLM 只兜底 | 每步 LLM 成本/延迟不可接受 |
| ADR-007 | 自研 clean-room 模拟器 | 参考项目无许可证/GPL/AGPL |

---

## 9. 本周

1. 写 `integration/maa.py` 适配层（吃 MAA recognition 结果）。
2. `scripts/run_coach.py`：只读截屏 + 推荐 + 日志。
3. 用 MaaGakumasu 的 `ProduceRecognitionCards` 跑 10 局，统计卡牌框/标签。
4. 定卡 ID 识别方案（模板 vs 分类器）。

---

## 10. 参考

- MaaGakumasu: <https://github.com/SuperWaterGod/MaaGakumasu>
- MaaFramework: <https://github.com/MaaXYZ/MaaFramework>
- bottled_ai（规则+模拟）: <https://github.com/xaved88/bottled_ai>
- spire-agent（deterministic first）: <https://github.com/AttemorySystem/spire-agent>
- spire-mentor（Rust 模拟 + MCTS/PPO）: <https://github.com/tfriedel/spire-mentor>
- STS-AI-Master（headless + ONNX）: <https://github.com/XlousMao/STS-AI-Master>
