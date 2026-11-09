# gkagent

《学园偶像大师》低 token、低延迟、可自学习的打牌 agent。

**当前阶段：P0 规划与骨架**（还没有可运行的策略）。

## 设计原则

1. 先确定性，后学习：规则 → 模拟搜索 → 小模型，LLM 只兜底。
2. 先模拟器，后真机：竞赛先跑通，再碰培育。
3. 先 shadow，后点击：感知准确率达标前不碰鼠标。
4. 每局可回放：帧、状态、动作、延迟、结果全部落库。

## 文档

- [项目规划](docs/PROJECT_PLAN.md)
- [架构与 ADR](docs/ARCHITECTURE.md)

## 快速开始（P0）

```powershell
uv venv --python 3.11
uv pip install -e ".[dev]"
uv run pytest -q
```

## 目录

```
src/gkagent/
  contract/    Observation / Action 契约
  perception/  截屏、OCR、模板、状态还原
  policy/      规则、搜索、价值网、LLM 兜底
  action/      Win32 / ADB / 安全守卫
  runtime/     主循环、回放、指标
  sim/         竞赛/培育模拟器
  training/    BC / PPO / 蒸馏 / ONNX
  eval/        基准与报告
```

## 免责声明

仅供个人学习研究。点击模拟违反游戏利用规约，存在封号风险；默认 shadow 模式，异常即停。
