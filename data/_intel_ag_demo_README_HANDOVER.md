# Gakumas H.I.F 本戦 全本地自动培育与打牌决策系统 — 交接说明文档 (`README_HANDOVER.md`)

> 根目录原有的 `README.md`、`manifest.json`、`gakumas_library.db`、`reference/`、`cards/`、`drinks/` 保持**完全只读**；本文档专用于项目交接，汇总了模拟器、卡牌饮料库、强化学习/树搜索算法、实机视觉扫库与自动化编排的完整结构、运行命令及最新验证基线。

---

## 1. 项目概览

本项目实现了一套**零 LLM、全本地运行**的《学园偶像大师》（学園アイドルマスター）**H.I.F 本戦**自动培育与打牌决策系统（重点面向 `[ガラクタロード] 秦谷 美鈴` `p_idol_id=163` / `logic` 好印象流派，同时兼顾三大职业知识库、`mock` 合成帧、`win32` 窗口、`adb` 实机与 Web 控制台）：

- **离线卡牌与饮料效果库**：从 `gakumas-tools` 解析导出的 `926` 张技能卡、`28` 种 P 饮料、`15` 位偶像、`165` 张 P 偶像、`111` 项自定义改造，提供 SQLite（`gakumas_library.db`）+ 结构化 JSON + PNG 图鉴双重存储。
- **高保真无头战斗模拟器 (`HeadlessBattleSimulator`)**：直接执行 `gakumas-data` 导出的结构化 JSON AST（`parsedEffects` / `dsl`），还原护盾/绿血/红血、好印象/干劲/好调/集中、抽/弃/除外区四区守恒、P 道具触发以及メモリー（回忆）全场限 1 次词条。
- **纯 NumPy Maskable PPO + 在线 SO-ISMCTS 规划器**：进入每场战斗（W7 1回戦 `9` 回合、W9 2回戦 `12` 回合）时，根据实机扫描出的真实牌库、P 道具、三维属性与实时开局 Buff 现场训练 2000 局 Maskable PPO，再在每一步决策结合 64 次单观察者信息集蒙特卡洛树搜索（`ISMCTSAgent`）出牌与饮用 P 饮料。
- **Windows 原生 OCR + Android ADB / MaaFramework 闭环**：通过 Windows Runtime（`WinRT OCR`）长驻 PowerShell Worker + 图像 ROI 识别主页、编成/扫库、日程、事件、奖励加卡/换牌（`チェンジ`）、商店（`相談` / `インターバル`、饮料购入、刷新与 `カスタマイズ` 自定义改造）、战斗 HUD，驱动 `GakumasRunner` 实现从 Home 进本 → 培育完走自动停止。

---

## 2. 打包目录与核心模块清单

```text
gakumas/
├── README_HANDOVER.md                  # 本交接说明文档（归档根目录副本，原件同步位于 demo/README_HANDOVER.md）
├── README.md                           # 原始卡牌与饮料效果库说明（只读）
├── manifest.json                       # 资产清单与版本信息（commit a82c3a3a5de41d2bd6130ad08bb88136dfa1977e）
├── gakumas_library.db                  # 只读 SQLite 效果数据库（4.41 MB；不含 -wal/-shm 临时文件）
├── reference/                          # ids / p_idols / customizations 与 Effects.md DSL 规范（4 files, 0.19 MB）
├── cards/                              # sense / logic / anomaly 三职业技能卡 JSON 与图片（5212 files, 170.27 MB）
├── drinks/                             # 三职业与通用 P 饮料 JSON 与图片（105 files, 1.84 MB）
└── demo/
    ├── README_HANDOVER.md              # 交接说明文档原件
    ├── README.md                       # Demo 基础模式说明
    ├── requirements.txt                # Python 依赖清单
    ├── run_hif_local.py                # 零 LLM H.I.F 本戦 ADB 全自动主入口（含 --initial-library 续跑）
    ├── app.py                          # CLI（mock / adb / win32）与 Web UI 启动入口
    ├── schemas.py                      # 跨模块数据契约（ScreenObservation / LegalAction / DecisionResult）
    │
    ├── sim/                            # 战斗模拟器与 RL/MCTS 算法核心
    │   ├── battle_simulator.py         #   HeadlessBattleSimulator（AST 执行、四区守恒、干劲/免费再动安全守卫）
    │   ├── rl_env.py                   #   GakumasBattleEnv / GakumasActionCodec / GakumasFeatureEncoder (68维标量+区计数)
    │   ├── maskable_ppo.py             #   纯 NumPy MaskablePPOTrainer / PolicyValueNet (gamma=1.0, hidden_dim=128)
    │   ├── ismcts.py                   #   ISMCTSAgent（64 次 determinized PUCT 搜索 + 安全免费/除外先验下界）
    │   ├── live_battle_planner.py      #   实机观测 <-> 模拟器状态对齐、每战在线训练与动作决策（含策略缓存）
    │   └── run_hybrid_demo.py          #   离线对照评测 CLI（Random / Pure ISMCTS / PPO Greedy / Hybrid PPO+ISMCTS）
    │
    ├── agent/                          # 培育期规则智能体与可选 LLM 适配
    │   ├── local_agent.py              #   LocalHybridDecisionAgent（Home→Setup→日程/选卡/换牌/商店→Battle→停止）
    │   ├── client.py / prompts.py / fallback.py  # 可选 OpenAI 兼容 LLM 决策链路与兜底启发式
    │
    ├── core/                           # 知识库、规则、状态追踪与剧本
    │   ├── db.py                       #   GakumasDB（只读查询 gakumas_library.db）
    │   ├── tracker.py                  #   GameStateTracker（卡组/P道具/记忆词条/导出 produce_library.json/存档检查点）
    │   ├── rules.py / scenarios.py / idol_guides.py / prompt.py
    │
    ├── vision/                         # 实机画面识别、初期扫库与 WinRT OCR
    │   ├── live_adb_recognizer.py      #   LiveScreenRecognizer（全场景分类、动态卡牌网格扫描、三维/Buff/饮料识别）
    │   ├── loadout_scanner.py          #   HifLoadoutScanner（1.アイドル選択 长按 & 2.開始確認 詳細按钮滚动扫库 + 回忆词条提取）
    │   ├── win_ocr.py                  #   Windows 原生 WinRT OCR 常驻子进程封装（ja / en / zh）
    │   └── roi.py / recognizer.py / mock_generator.py
    │
    ├── maa_bridge/                     # 控制器抽象与主循环调度
    │   ├── adb_controller.py           #   AdbController（MaaAdbController + CLI fallback）
    │   ├── runner.py                   #   GakumasRunner（loading 防抖、初期扫库预算隔离、防卡死、自动停机、Watchdog）
    │   └── base_controller.py / win32_controller.py / mock_controller.py / custom_*.py / simulator.py / pipeline.json
    │
    ├── web/                            # MFAAvalonia 风格 Web 控制台前后端（FastAPI / HTTP+SSE + 静态页面）
    └── tests/                          # 全套单元测试与回归测试
```

---

## 3. 核心算法与关键工程机制

1. **战斗模拟器 (`demo/sim/battle_simulator.py`)**：
   - `HeadlessBattleSimulator` 读取 `gakumas_library.db` 的 `parsed_effects_json` 执行条件、费用（体力/元气盾、红血直扣、`costReduction`/`halfCostTurns`/`doubleCostTurns`、Buff 消耗）及延时/被动触发器（`@trigger`、`ttl`、`limit`）。
   - **回忆词条Stage级唯一限制**：`memory_extra_used_base_ids` 与 `memory_exile_used_base_ids` 按 `base_id` 跨重复卡强制全场仅触发一次。
   - **安全免费再动守卫 (`is_safe_dominating_free_card`)** 与 **干劲经济感知 (`has_motivation_engine` / `active_motivation_economy`)**：
     - 非消耗稀有跨回合资源的免费再动卡（如 `#159 アイドル魂+`、`#171 私がスター+`、`#297 止められない想い+`、`#137 やる気は満点+` 回忆再动）在安全前提下严格优先；
     - 消耗 `motivation` 的 `+1 使用数` 卡（`#299 オトメゴコロ+`、`#305 輝くキミへ+`、`#97 みんな大好き+`、`#173 星屑センセーション+`）在 `turns_remaining > 2` 时，**仅当 `#128/#129 ワクワクが止まらない` 干劲引擎已在场生效且剩余干劲高于安全保留阈值**时才视为占优，其余情况交由 PPO/ISMCTS 自主权衡「先开产干劲引擎还是即刻消费」，避免前中期把干劲抽空导致后期断档。

2. **RL 环境与算法 (`demo/sim/rl_env.py`, `maskable_ppo.py`, `ismcts.py`, `live_battle_planner.py`)**：
   - `GakumasFeatureEncoder`（`SCALAR_DIMS = 68`）：严格遵守**信息集安全性（对抽牌堆顺序置换不变）**，除回合/场地倍率预期、Buff/区统计外，包含 4 维干劲经济特征与 3 维手牌即时可执行指示。
   - `GakumasBattleEnv`：支持可选零偏置势能奖励塑形（`_motivation_potential`，终端必为 `0`），默认 `motivation_cost_weight=0.0`（对照实验证明关闭强制耗干劲剪枝 + 结构特征后，`0.0` 纯分表现最佳）。
   - `MaskablePPOTrainer`：`gamma=1.0`（有限视野不折现总分优化）、`gae_lambda=0.95`、`hidden_dim=128`、每战 `2000` episodes、`best_val_mean` 权重落盘缓存。
   - `ISMCTSAgent`：`num_simulations=64`、`value_weight=0.35`，在 `is_safe_dominating_free_card` 与 `has_unused_memory_exile`（存在 `眠気` 且 `turns_remaining >= 3`）施加先验下界引导，同时保留 `GakumasBattleEnv` 对 Active 双动饮料 `#25` 的合法性/根动作过滤。
   - `build_live_battle_config()`：对 `#436 花ロボ(黄)` 的开局 `GI/Mot` 按对称实机规则做截断补正（仅 `<3` 的 OCR 截断回填到 `3`，或单侧 `>=6` 另一侧 `<3` 对称补齐到 `6`，保留实机真实的 `3/3` 或 `6/6`）；`_sync_sim_to_observation()` 不对灰卡（`visual_playable is not True`）或显式低干劲 HUD 虚增模拟器 `motivation`。

3. **实机扫库、培育策略与防卡死 (`demo/vision/`, `demo/agent/local_agent.py`, `demo/maa_bridge/runner.py`)**：
   - **双段初始扫库**：`1.アイドル選択`（长按，预算 1 次）与 `2.開始確認`（点击 `詳細` 按钮，预算 2 次），期间暂停 Idle Watchdog，并用界面互斥标记防止仍在选人页时误判弹窗已打开；`2.開始確認` 使用右对齐三维坐标框并禁止污染 `_last_stats`。
   - **动态卡牌网格与核心卡保护 (`チェンジ` / `削除`)**：`H.I.F` 无 N 基本卡时默认停在卡库顶部扫描（需要时仅翻页 1 次），按固定空间顺序扫描避免选中框移动破坏索引；对核心乘法/延长/P 道具联动卡（如 `#520/#521 夢色リップ`、`#617 対象、ロックオン`、`#171 私がスター`、`#920`、`#922`）施加强力负删除分保护。
   - **W8 `インターバル` 中场商店与停机**：全自动完成买饮料、刷新（`リフレッシュ`）、强化与 `カスタマイズ` 多轮自定义改造；培育完走回到 `home` 或 `produce_setup` 后自动停机，严禁开启第二局，全程严禁花费 `ジュエル` 与点击 `リタイア`。

---

## 4. 环境配置与常用运行命令

### 4.1 依赖与运行环境
- **操作系统**：Windows 10 / 11（实机视觉依赖系统内置 `WinRT OCR` 日语 `ja` 与英语 `en` 语言识别包，无需安装 PaddleOCR / Tesseract）。
- **Python**：3.11+，在解压后的项目根目录安装依赖：
  ```bash
  pip install -r demo/requirements.txt
  ```
- **Android 模拟器 / ADB**：确保 `adb.exe` 可用（默认优先探测 PATH、环境变量 `ADB_PATH` 及常见 SDK/模拟器路径如 `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`）并已启用 TCP/IP ADB。

### 4.2 常用命令（请在解压后的仓库根目录执行）

1. **全本地零 LLM 启动 H.I.F 本戦实机自动化**（从 Home 一路走到育成完走停止）：
   ```powershell
   $env:PYTHONIOENCODING = "utf-8"
   python -u -m demo.run_hif_local --adb 192.168.5.124:5555 --plan logic --scenario hif_honsen --library-out produce_library.json --debug-dir debug_frames --max-steps 400 --delay 0.5
   ```
   - 中途断点续跑可追加：`--initial-library produce_library.json`。
   - 默认参数：`--ppo-episodes 2000 --ismcts-sims 64`；如需不自动停机可加 `--no-stop-home`。

2. **运行离线战斗算法对比基准 (`HeadlessBattleSimulator` + `PPO` + `ISMCTS`)**：
   ```bash
   python -m demo.sim.run_hybrid_demo --episodes 2000 --eval-episodes 30 --sims 64
   ```

3. **启动 Web 控制台前端或离线 Mock 演示**：
   ```bash
   python demo/app.py --mode ui --ui-port 8765 --open-browser
   python demo/app.py --mode mock --plan logic --steps 5
   ```

4. **运行本地测试集**（排除需外部 LLM API 的在线用例）：
   ```bash
   python -m pytest demo/tests/ -k "not test_live_xai_llm_decision_e2e" -q
   ```

---

## 5. 最新验证基线与交接注意事项

### 5.1 离线训练基准（W9 真卡组 24 卡，`GI=3 / Mot=3` 开局，2000 eps / 30 局未见评估）
- **结构化干劲守卫 + 4 维经济特征（默认 `motivation_cost_weight=0.0`）**：`bestVal=466,850`、`eval30 均值=477,670`（中位数 `482,942`、最高 `687,855`），**`100.0%` 在 T2 前打出 `ワクワクが止まらない+`**，后期（T8–T12）平均干劲 **`21.16`**，**干劲卡手数 `0.0`/局**。
- **对比叠加 PBRS 塑形（`weight=0.035`）**：同样 `100%` 早期启动与 `0.0` 卡手，但额外权重方差使 `eval30 均值` 降至 `450,786`（`-26,884`）。

### 5.2 实机全流程验证（`smoke_v7`，从 Home 零干预启动）
- **Day 1 扫库**：首轮识别 `p_idol_id=163`、`Vo=2393 / Da=1108 / Vi=1644`、完整 22 卡 + 全 7 件 P 道具，无误标词条。
- **W7 1回戦**：训练 `bestVal=477,554`，T1 打出 `アイドル魂+` → `ワクワクが止まらない+` 并免费除外 `眠気`，T9 末回合好印象 `110`、干劲余量保持 **`22`**。
- **W8 `インターバル` 商店**：自动购买 `ブーストエキス`、`ルイボスティー`、`特製ハツボシエキス`，刷新并执行 4 轮 `カスタマイズ` 自定义改造。
- **W9 2回戦**：训练 `bestVal=734,656`，T1 开 `ワクワクが止まらない+`，T9/T11/T12 干劲分别保持 **`26 / 21 / 20`**（全程 **0 次**干劲不足弹窗），T11 即以 `620,331` 反超至第 1，T13 结算前已达 **`962,352`**（`simQ=1,554,892`）一把稳拿第 1 名。（注：W9 结算后因设备 IP 从 `192.168.0.115` 变更为 `192.168.5.124`，原 `192.168.0.115` 进程按 `Step 294` 断连退出。）

### 5.3 交接红线与已知可继续优化项
1. **只读红线**：切勿修改 `cards/`、`drinks/`、`reference/`、`gakumas_library.db`、`manifest.json`、`README.md`；切勿生成无用的 `demo/state` 运行时目录；所有实机自动化均禁止消耗 `ジュエル` 与主动点击 `リタイア`。
2. **已知微项（后续接手可优先处理）**：
   - `demo/tests/test_local_hif_pipeline.py` 中 `test_round2_drink_gating_empty_hand_score_outlier_pitem429_and_hud_ocr` 末尾调用未传 mock controller 的 `build_local_hif_runner()`，当本机默认 ADB IP `192.168.0.115:5555` 不在线时会连接超时（其余 `278` 项本地单测全通过，全量运行结果为 `278 passed, 1 failed, 1 deselected`）。
   - W7 战中动画过渡偶发短暂判为 `skip` 触发 `reset_battle`（可在 `runner.py` 提高战中离场连续帧确认数）。
   - 训练 2000 局 PPO（约 60–65 秒）期间可像扫库一样暂停 60s Idle Watchdog 空白点按。
   - `GameStateTracker` 可补充 `is_unique_in_deck` 重复领取保护，并在模拟器中映射 W8 `カスタマイズ`（`++` 降费/加数值）的数值补丁。
