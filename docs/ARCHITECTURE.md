# 架构与 ADR

## 定位

GDE 是 MaaGakumasu 的**决策层插件**，不是替代品。

```
MaaGakumasu（手和眼）──custom_action──▶ GDE（脑子）
   截屏 / 识别 / 点击 / 日常              规则 / 搜索 / 价值网 / LLM
```

- MAA 负责：截屏、识别、点击、日常、商店、启动、更新、DMM/汉化。
- GDE 负责：卡级状态、出牌策略、培育路线、竞赛建模、复盘、学习。
- 两者通过 `CustomAction` / `CustomRecognition` 和 `Observation/Action` 契约连接。

## 分层

```
perception (MAA 或独立) → contract → policy → action (MAA controller)
                              ↑          ↑
                           replay     model/rule version
```

- **contract**：Pydantic 模型，`schema_version` 控制兼容性。
- **integration/maa**：MAA recognition 结果 ↔ `Observation`；`Action` ↔ 点击坐标。
- **policy**：`rules → search → value → llm` 路由；实现 `act(obs, legal)`。
- **runtime**：跑局、延迟、回放、熔断。
- **sim**：`Env` 接口；竞赛/培育各自实现。
- **training**：BC → PPO/AlphaZero → distill → ONNX。

## 决策路由

1. 规则/宏命中 → 直接动作（0 token）。
2. 战斗/考试 → 模拟器搜索（0 token）。
3. 未知界面/文本 → 本地 3B LLM（50–200 token，缓存）。
4. 都不匹配 → 返回 `None`，回退 MAA 原逻辑/停住。

## ADR

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-001 | 不做日常/商店/点击层 | MAA 已做好，重复无价值 |
| ADR-002 | 以 MAA custom_action 为第一集成点 | 复用识别/点击，改动最小 |
| ADR-003 | 先教练模式 | 零风险验证识别与推荐 |
| ADR-004 | 先竞赛后培育 | 回合短、模拟成熟 |
| ADR-005 | 规则+搜索优先，RL 后置 | 确定性方案在 STS 上已被验证 |
| ADR-006 | LLM 只兜底 | 每步 LLM 成本/延迟不可接受 |
| ADR-007 | 自研 clean-room 模拟器 | 参考项目无许可证/GPL/AGPL |

## 当前状态（P0）

- 已实现：契约、Env/Policy 接口、随机/脚本基线、Loop、回放模型、MAA 识别结果适配、7 个测试。
- 未实现：MAA custom_action 实机注册、卡 ID 识别、搜索、价值网、LLM、模拟器规则。
- 下一步：P1 教练模式（`GkAgentCoach`，只读）。
