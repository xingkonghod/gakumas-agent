# 架构与 ADR

## 分层

```
perception → contract → policy → action
                ↑          ↑
             replay      model/rule version
```

- **perception**：Win32/DXGI 截屏、模板匹配、OCR、YOLO。输出 `Observation`。
- **contract**：Pydantic 模型，`schema_version` 控制兼容性。
- **policy**：`rules → search → value → llm` 路由；每个策略实现 `act(obs, legal)`。
- **action**：白名单 + 限速 + 熔断；只执行 `ActionKind` 允许的动作。
- **runtime/loop**：跑局、记延迟、写回放、统计。
- **sim**：`Env` 接口；竞赛/培育各自实现；训练和评估共用。
- **training**：BC → PPO/AlphaZero → distill → ONNX。

## 决策路由

1. 规则/宏命中 → 直接动作（0 token）。
2. 战斗/考试 → 模拟器搜索（0 token）。
3. 未知界面/文本 → 本地 3B LLM（50–200 token，缓存）。
4. 都不匹配 → 停住，等人接管。

## ADR

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-001 | 先竞赛后培育 | 回合短、模拟成熟、奖励清晰 |
| ADR-002 | 自研 clean-room 模拟器 | 参考项目无许可证或 GPL/AGPL，不能直接复制 |
| ADR-003 | 规则 + 搜索优先 | 确定性方案在 STS 上已被验证强于端到端 |
| ADR-004 | LLM 只兜底 | 每步 LLM 延迟/成本不可接受 |
| ADR-005 | 先 shadow 后点击 | 感知错误比策略错误更致命 |
| ADR-006 | 契约版本化 + 回放 | 可定位感知/策略/执行问题 |

## 当前状态（P0）

- 已实现：契约模型、Env 接口、Policy 接口、随机基线、Loop 骨架、回放模型。
- 未实现：真实截屏、感知、搜索、价值网、LLM、点击、模拟器规则。
- 下一步：P1 竞赛模拟器 + 规则基线（见 `PROJECT_PLAN.md`）。
