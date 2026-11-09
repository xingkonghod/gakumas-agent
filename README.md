# gkagent（GDE）

**MAA 的决策外挂，不是另一个 MAA。**

MaaGakumasu 负责看和点（截屏、识别、点击、日常、商店、启动、更新）；
GDE 负责“这手牌怎么打、这条路怎么走、为什么”，并把决策过程变成可回放、可训练的数据。

## 分工

| 能力 | MaaGakumasu | GDE |
|---|---|---|
| 截屏/识别/点击/日常 | ✅ | ❌ 复用 |
| 卡 ID/费用/效果识别 | 只分三类框 | ✅ |
| 出牌决策 | 启发式 | ✅ 搜索 + 价值网 + 学习 |
| 培育路线/事件/道具 | 规则 | ✅ 规划 |
| 竞赛策略 | 选对手 | ✅ 建模 |
| 复盘/反事实 | 日志 | ✅ 回放 + 分析 |
| 学习闭环 | 无 | ✅ BC/RL/蒸馏/ONNX |

## 三种共存模式

1. **教练模式**：挂 MAA 里只读、只记录、只推荐，不点击。先做这个。
2. **插件模式**：用 MAA 的 `CustomAction` 替换 `ProduceCardsAuto` 的决策，点击仍走 MAA controller。
3. **独立竞赛**（可选）：MAA 不跑时自己打竞赛。

## 文档

- [项目规划](docs/PROJECT_PLAN.md)
- [架构与 ADR](docs/ARCHITECTURE.md)
- [MAA 集成](docs/MAA_INTEGRATION.md)

## 快速开始

```powershell
uv venv --python 3.11
uv pip install -e ".[dev]"
uv run pytest -q
```

## 目录

```
src/gkagent/
  integration/ MAA 适配层（识别结果 ↔ 契约）
  contract/    Observation / Action / Replay
  perception/  独立截屏/OCR（教练模式备用）
  policy/      规则、搜索、价值网、LLM 兜底
  action/      Win32 / ADB / 安全守卫（插件模式下不用）
  runtime/     主循环、回放、指标
  sim/         竞赛/培育模拟器
  training/    BC / PPO / 蒸馏 / ONNX
  eval/        基准与报告
```

## 免责声明

仅供个人学习研究。点击模拟违反游戏利用规约，存在封号风险；默认教练模式，插件模式可随时回退。
