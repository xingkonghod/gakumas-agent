# Gakumas Agent 项目规划

> 版本：v0.1（规划稿）
> 日期：2026-11-09
> 目标：给《学园偶像大师》做一个**低 token、低延迟、可自学习**的打牌 agent。
> 原则：先确定性，后学习；先模拟器，后真机；先竞赛，后培育。

---

## 1. 目标与非目标

### 1.1 目标

1. **会打牌**：竞赛/考试能稳定做出接近强玩家的决策。
2. **低 token**：日常流程 0 token；单次培育 < 2 万 token；不把截图当 prompt。
3. **低延迟**：策略单步 < 10ms，端到端（截屏→点击）p95 < 80ms。
4. **可自学习**：每局可回放，离线训练，灰度替换，不在线改权重。
5. **可回滚**：任何一局都能复现；策略/模型/规则都有版本号。

### 1.2 非目标（明确不做）

- 不改游戏数据、不注入内存、不伪造请求。
- 不做排行榜刷分、不多账号、不 24×7 无人值守（至少前两个阶段）。
- 不追求“全自动过所有内容”；先做竞赛，再评估培育。
- 不为了绕过检测做对抗性设计。

### 1.3 风险声明

点击模拟仍违反游戏利用规约，存在账号限制/封禁风险。本项目按“个人研究、可随时停”设计：默认 shadow 模式、动作白名单、人工接管、限速。

---

## 2. 硬件与约束

| 项 | 值 | 影响 |
|---|---|---|
| GPU | RTX 5060 Laptop 8 GB | 策略网 5–20M 参数；本地 3B Q4 LLM；不能跑大模型全参 |
| CPU | Ultra 9 275HX 24 核 | 模拟器并行 6–8 worker |
| RAM | 15.4 GB | 控制 worker 数，回放用 SQLite 不驻留 |
| 磁盘 | D: 215 GB 空闲 | 回放/模型/截图够用 |
| Python | 3.10.11 + uv 0.13.5 | 用 uv 建 3.11 venv |

**结论**：走“小模型 + 模拟器搜索 + 蒸馏”，不走大规模端到端 RL。

---

## 3. 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│ runtime/loop                                                 │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐            │
│  │ perception │ → │  contract  │ → │   policy   │ → action   │
│  │ 截屏/OCR/  │   │ Observation│   │ 规则→搜索→ │   Win32/   │
│  │ YOLO/模板  │   │  /Action   │   │ 价值网→LLM │   ADB      │
│  └────────────┘   └────────────┘   └────────────┘            │
│         ↑                ↑                ↑                  │
│     replay/DB       schema 校验       模型/规则版本            │
└──────────────────────────────────────────────────────────────┘
        │                                        │
        ▼                                        ▼
┌──────────────────┐                  ┌──────────────────┐
│ sim/             │                  │ training/        │
│ 竞赛/培育模拟器   │ ←── self-play ── │ BC→PPO/AlphaZero │
│ 动作掩码/状态编码 │ ── 数据/评估 ──→ │ 蒸馏→ONNX        │
└──────────────────┘                  └──────────────────┘
```

### 3.1 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| perception | 截屏、识别、状态还原 | 不做决策 |
| contract | 定义 Observation/Action、版本、校验 | 不含业务逻辑 |
| policy | 规则、搜索、价值网、LLM 兜底 | 不碰鼠标键盘 |
| action | 点击/拖拽/等待、白名单、限速 | 不决定点哪 |
| runtime | 主循环、回放、指标、熔断 | 不实现策略 |
| sim | 规则模拟、动作掩码、奖励 | 不依赖真机 |
| training | 数据集、训练、蒸馏、导出 | 不直接控制游戏 |

### 3.2 决策路由（核心）

```
Observation
   │
   ├─ 命中规则/宏？ ──是──→ 直接动作（0 token, <1ms）
   │
   ├─ 是战斗/考试局面？ ──是──→ 模拟器搜索（0 token, 5–20ms）
   │                              └─ 叶子用 value net 评估
   │
   ├─ 是未知界面/活动文本？ ──是──→ 本地 3B LLM（50–200 token, 缓存）
   │
   └─ 都不匹配 ──→ 安全停住，等人接管（不猜）
```

---

## 4. 目录结构

```
gakumas-agent/
├── README.md
├── pyproject.toml
├── .gitignore
├── configs/
│   └── default.yaml
├── docs/
│   ├── PROJECT_PLAN.md        # 本文
│   ├── ARCHITECTURE.md        # 架构与 ADR
│   ├── STATE_CONTRACT.md      # Observation/Action 规范
│   └── ROADMAP.md             # 里程碑与验收
├── src/gkagent/
│   ├── __init__.py
│   ├── contract/
│   │   ├── __init__.py
│   │   └── models.py          # Pydantic 模型
│   ├── perception/
│   │   ├── __init__.py
│   │   ├── capture.py         # Win32/DXGI 截屏
│   │   ├── ocr.py             # RapidOCR/PaddleOCR
│   │   ├── templates.py       # 模板匹配
│   │   └── state_builder.py   # 帧 → Observation
│   ├── policy/
│   │   ├── __init__.py
│   │   ├── base.py            # Policy 接口
│   │   ├── rules.py           # 规则/宏
│   │   ├── search.py          # expectimax/MCTS
│   │   ├── value.py           # 价值网/启发式
│   │   ├── llm.py             # 本地 LLM 兜底
│   │   └── router.py          # 决策路由
│   ├── action/
│   │   ├── __init__.py
│   │   ├── win32.py           # SendMessage/PostMessage
│   │   ├── adb.py             # 模拟器备用
│   │   └── guard.py           # 白名单/限速/熔断
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── loop.py            # 主循环
│   │   ├── replay.py          # SQLite 回放
│   │   ├── metrics.py         # 延迟/成功率/token
│   │   └── safety.py          # 异常停住/人工接管
│   ├── sim/
│   │   ├── __init__.py
│   │   ├── env.py             # Gym 风格接口
│   │   ├── contest.py         # 竞赛环境
│   │   ├── produce.py         # 培育环境（P6）
│   │   └── adapters.py        # 外部模拟器桥接
│   ├── training/
│   │   ├── __init__.py
│   │   ├── dataset.py         # 轨迹 → 样本
│   │   ├── bc.py              # 行为克隆
│   │   ├── ppo.py             # 自对弈 RL
│   │   ├── distill.py         # 教师→学生
│   │   └── export_onnx.py     # 量化/导出
│   └── eval/
│       ├── __init__.py
│       ├── bench.py           # 模拟器基准
│       └── report.py          # 报告
├── scripts/
│   ├── run_shadow.py          # 只看不点
│   ├── run_agent.py           # 闭环
│   ├── train.sh
│   └── export.sh
├── tests/
│   ├── test_contract.py
│   └── test_sim_env.py
└── data/                      # gitignore
    ├── replays/
    ├── models/
    └── cache/
```

---

## 5. 阶段计划（8–10 周，单人 + AI）

### P0 基础设施（第 1 周）

- 建仓、uv 环境、pyproject、config、日志。
- 定义 Observation/Action 契约（Pydantic + JSON Schema），版本号。
- SQLite 回放格式：每步 `frame_hash, obs, action, latency, result`。
- 模拟器接口 `sim/env.py`，随机策略基线。
- **验收**：`pytest` 通过；回放可重放；随机基线能跑 100 局不崩。

### P1 竞赛模拟器 + 规则基线（第 2 周）

- 竞赛环境（动作掩码、状态编码、奖励）。
- 规则策略：按分数差/属性/体力做启发式。
- 评估脚本：胜率、平均分、p95 延迟。
- **验收**：规则策略胜率显著高于随机；单步 <5ms；1 万局无异常。

### P2 搜索策略（第 3 周）

- expectimax / MCTS（深度 2–4），带动作掩码和启发式价值。
- 搜索预算自适应：普通局面浅搜，关键局面深搜。
- **验收**：对比规则基线胜率 +10%；p95 <20ms；可复现（固定种子）。

### P3 感知 + 执行（第 4–5 周）

- Win32 截屏（客户区），模板匹配 + OCR + 轻量 YOLO。
- `state_builder` 输出契约；置信度低于阈值 → 停住。
- Shadow 模式：只识别、只决策、不点击，对比日志。
- **验收**：500 帧状态准确率 >98%；动作 dry-run 与人工一致 >95%。

### P4 闭环竞赛（第 6 周）

- 动作白名单、限速、异常恢复、人工接管。
- 真机跑 20 局，记录崩溃/卡住/误点。
- **验收**：20 局完成率 >90%；无卡死 >30s；误点 0 次。

### P5 学习与蒸馏（第 7–8 周）

- 从搜索结果生成数据集；BC 预训练；value net。
- 自对弈 PPO/AlphaZero 微调；蒸馏到小网。
- ONNX INT8 导出，延迟 benchmark。
- **验收**：学生达到教师 90% 胜率；策略 <5ms；模型 <50MB。

### P6 培育（第 9–10 周，可选）

- 培育环境（长程、事件、道具、饮料）。
- LLM 兜底只处理未知事件；缓存。
- **验收**：完整跑完一局培育；token <2 万；失败可重试。

---

## 6. 关键设计决策（ADR）

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-001 | 先竞赛，后培育 | 回合短、模拟器成熟、奖励清晰 |
| ADR-002 | 自研 clean-room 模拟器 | gakumastrain 无许可证，不能直接 fork；只参考思路 |
| ADR-003 | 规则 + 搜索优先，RL 后置 | bottled_ai/spire-agent 证明确定性更强；RL 需要数据和调参 |
| ADR-004 | LLM 只做兜底 | 每步 LLM 2 万 token 的反面教材；延迟不可接受 |
| ADR-005 | 先 shadow 再点击 | 感知错误比策略错误更致命 |
| ADR-006 | 契约版本化 + 可回放 | 出问题能定位是感知、策略还是执行 |

### 许可证注意

- `MaaGakumasu`：AGPL-3.0；复用其模板/代码需同样开源。
- `hiro-gakumas-hero`：GPL-3.0；参考架构可以，复制代码需 GPL。
- `gakumastrain`：**无许可证**（默认保留所有权利），只能读思路，不能复制。
- 本项目默认 MIT；若引入 GPL/AGPL 代码，整体改为对应许可证。

---

## 7. 指标体系

| 类别 | 指标 | 目标 |
|---|---|---|
| 策略 | 模拟器胜率/平均分 | 逐阶段提升 |
| 感知 | 状态字段准确率 | >98% |
| 延迟 | 策略单步 p95 | <10ms |
| 延迟 | 端到端 p95 | <80ms |
| 成本 | 日常 token/天 | ≈0 |
| 成本 | 单次培育 token | <2 万 |
| 稳定 | 完成率/卡死率 | >90% / 0 |
| 安全 | 白名单外点击 | 0 |

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 封号 | 账号损失 | 个人研究、限速、不刷榜、异常即停 |
| 模拟器与真机偏差 | 策略失真 | gakumasu-diff 同步； nightly 回归 |
| 感知错误 | 误点 | 置信度阈值 + 人工接管 + 白名单 |
| 数据不足 | RL 不收敛 | 模拟器自对弈 + shadow 日志 + BC |
| 8GB 显存 | 训练受限 | 小模型、梯度累积、CPU 模拟 |
| 规则更新 | 脚本失效 | 版本化 + 快速回滚 |

---

## 9. 本周要做的 5 件事

1. 建仓 + uv 环境 + CI（pytest）。
2. 落 Observation/Action 契约（先竞赛）。
3. 竞赛模拟器最小闭环 + 随机基线。
4. 回放格式 + SQLite。
5. Shadow 截屏原型（只截一张图，验证 Win32 capture）。

---

## 10. 验收方式

每个阶段结束跑一次固定基准：

```bash
uv run python -m gkagent.eval.bench --env contest --episodes 1000 --seed 42
uv run pytest -q
```

输出：胜率、平均分、p95 延迟、异常数、token 估算。基准结果入库，回退可见。
