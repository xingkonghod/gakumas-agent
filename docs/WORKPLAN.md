# 总作战计划（2026-11-22 起，新会话照此执行）

> 用户定的顺序：**先把所有离线工作全部做完 → 再跑真机 → 最后去 gkbench 比算法**。
> 本文件是唯一的总清单；具体任务细节在 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)、
> [GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md)、[EXPECTIMAX.md](EXPECTIMAX.md) 等文档里。
> 新会话开场：`读 docs/INDEX.md → docs/WORKPLAN.md → docs/HANDOVER_NEXT.md §2 跑基线 → 按 WORKPLAN 顺序做`。

---

## 0. 已完成，不要重做（新会话先确认这些仍然成立）

| 能力 | 验证 |
|---|---|
| MITM 采集链路（本地副本+代理+traffic） | 采集服务 18443/18444，可随时重启 |
| 洗牌模型（xorshift32+Fisher-Yates+支援强化+重洗） | `verify_shuffle.py` 4/4 场、重洗 3/3 |
| 牌序全知数据链路 `ExamSetup/ExamDrawPlan/known_draw/discard_order/beam` | `verify_exam_wiring.py` 36/36、3/3、29/29 |
| 决策可观测性 + 引擎接线（`--engine`/`produce.engine`，禁静默回退 rules） | 日志 `[engine]` / `| eng=… fallback=…`；单测 |
| 用户规则：SKIP 只在真没体力；禁止规则回退 | 全量 pytest 全绿 |
| known_draw **事前检测**（额外 RNG 机制卡 → 不启用全知） | `exam_risk.py` + 单测；169/1829 机制卡、四场牌组 0 命中 |
| T4 平手项/beam 采样实验（+19.9，但 beam 仍低于 within 22%） | `EXPECTIMAX.md`；rollout 叶子负结果也记录在案 |
| T1 真机流程 10+ 类卡点 + F#41（日文剧情二选一）修复 | `FAILURES.md` #27-41；`584f742` |
| A1 OCR 换日文/多语言模型（官方 PP-OCRv6，Apache-2.0） | `tests/test_ocr_jp_model.py` 真图 4 条 + `test_ocr_config.py` 17 条；全量 pytest 926/1；`docs/HANDOVER` 二·补十四 |
| A2 课程硬打必须得分（F#42：HUD 语义 + 每回合 1 张 + 硬打保分） | `tests/test_lesson_play_f42.py` 真图回放 3 条 + `test_lesson.py` HUD 换算 4 条 + `test_hardplay_prefers_scoring_card_on_flat_tie`；全量 pytest 934/1（935 收集 / 66 文件）；`docs/HANDOVER` 二·补十五 |
| A3 F#43 结果页空转（真根因：日文饮料选择事件屏 + P 费标签命中飘字正则） | `tests/test_produce_ui_f43.py` 7 条（真机帧回放 3 + 合成 4）；全量 pytest 941/1（942 收集 / 67 文件）；`docs/HANDOVER` 二·补十六 |
| A4 离线回放素材（六类关键屏真机帧归档 + 回放测试 + 挑帧工具） | `tests/fixtures/` 8 张真机帧 + `README.md` 溯源表；`tests/test_frames_replay_a4.py` 9 条；`scripts/scan_frames.py`；顺带修 `_checkbox_bands` 真机 TypeError（F#44）；全量 pytest **950/1（951 收集 / 68 文件）**；`docs/HANDOVER` 二·补十七 |
| 私有存档/私有仓库（bundle+裸仓库+Gitee private） | `docs/ARCHIVE.md`，`scripts/archive_private.ps1 -Push` |
| 群情报归档（论文/2B run/GKMSMAA/手机实验版） | `GROUP_FILES_ANALYSIS.md`、`QQ_GROUP_NOTES.md` |

**明确先不做（低优先/不必要）**：手机 APK 的 gadget 协议逆向、Localify 反编译、公开任何工具细节、gkbench ranked 提交（规则禁 seed）。

---

## 阶段 A：离线收尾（P0，全部做完才碰真机）

### A1. OCR 换日文模型（最高优先，一次修好大量文本分支）✅ 2026-11-22 完成
- 根因证据/方案：见 [GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md) §1–2（我们默认中文字典无假名；
  魔改 MAA 的日文模型实测完整读出日文）。
- 做法：
  1. `OcrEngine` 支持 `config_path`/环境变量 `GKAGENT_OCR_CONFIG`；
  2. 先本地加载 `D:\GakumasAgentArchive\group_files\GKMSMAA\resource\base\model\ocr\*`（AGPL，仅本地验证）；
  3. 正式方案换 **PaddleOCR 日文模型（Apache-2.0）**，模型放 `data/models/`（`.gitignore` 里）或下载脚本；
  4. 加 `configs/ocr_jp.example.yaml`；**不得**把 AGPL 模型提交进仓库/Gitee。
- DoD：同一张 `step_025.png` 能读出 `ヨーグルトパフェ/つくねハンバーグ/ドリンクバー` 与完整对白；
  全量 pytest 绿；用日文文本重新跑一遍剧情/事件/课程的相关单测（可去掉布局兜底的强依赖，但兜底保留）。

**落地（2026-11-22）**
- `OcrEngine` 配置优先级：显式 `config_path=` > `GKAGENT_OCR_CONFIG` > 本地 `configs/ocr_jp.yaml`
  （下载脚本生成，gitignore；删掉即回内置中文模型）> 内置中文模型。配置/模型文件缺失**直接报错**，不静默回退。
  两阶段主引擎与单行 `_line_core` 引擎共用同一套模型配置；路径支持 `%VAR%`/`$VAR`、相对 YAML 目录解析。
- 正式模型 = 官方 **PP-OCRv6_small_det + PP-OCRv6_small_rec（Apache-2.0，多语言）**：
  `scripts/download_ocr_models.py` 下载（URL+sha256 锁定）、校验、导出 18,708 行字典到
  `data/models/ocr_jp/`（gitignore）、生成 `configs/ocr_jp.yaml`；模板 `configs/ocr_jp.example.yaml`；
  `scripts/ocr_probe.py` 单图验字。AGPL 的 MAA 模型只本地对照（输出逐行相同），未入库。
- 实测 `data/auto/step_025.png`（720x1280，全屏 ≈1.0s）：读出 `ヨーグルトパフェ / つくねハンバーグ /
  ドリンクバー / そこまで真剣だと慰労を超えますが…… / 倉本さんのお気に入りは……`，中文 UI
  （`外出/审查基准/快进`）同时可读；`ProduceDriver` 同帧决策 `event-choice/last-row` 点 (360,935) 选项，
  不再点「快进」（F#41 类剧情/事件原地循环的直接影响）。
- 测试：`tests/test_ocr_config.py`（17 条，配置/路径/报错/单行引擎接线）+ `tests/test_ocr_jp_model.py`
  （4 条真图回归，模型缺失自动 skip）；修复基线过期断言
  `test_read_fast_event_page_uses_option_rows`（事件快速路径补读对话区后应允许区域 OCR）；
  真机日志新增 `[ocr] 模型 = …` 一眼确认是否日文模型。
- 中文 UI/性能回归（`scripts/bench_ocr.py --after --verify --threads 8`）：关键词 **5/5**；
  行动页单步 ≈189ms、课程页读屏 ≈402ms、全屏 read ≈752ms（目标 ≤1500ms）。
- 全量 pytest：**926 passed, 1 skipped**（927 条收集 / 65 个测试文件；见 HANDOVER_NEXT §2）。

### A2. F#42 课程策略：硬打必须保证得分（用户现场发现）✅ 2026-11-22 完成
- 现象：舞蹈课程连续打 buff（表情的基础 2.0）→ `lesson_score=90` → FAILED。
- 修法：禁跳规则下"强制出牌"必须优先 `score>0` 且付得起的牌；buff 与打分按剩余回合/缺口平衡；
  连续 N 张 0 分牌降级为"直接补 CLEAR 的牌"；用真机课程截图做离线回放单测。
- DoD：用 ep-t3-4 课程截图回放不再选 buff；单测覆盖"buff 多/分数少"场景。

**落地（2026-11-22）**
- **真根因比初判更深**（两层，都是"模型以为"和"屏幕实际"不一致）：
  1. **课程 HUD 语义读错**：右上角是**培育属性值**（不是课程分）；正中圆环
     「CLEAR截止 / PERFECT截止 N」是**还差 N 分**（过了 CLEAR 换成 PERFECT）。旧读法把
     属性值当课程分、把还差分当过关线：真机帧「属性 90 / CLEAR截止 30」被当成
     "分数 90 ≥ 过关线 30 → 已经 PERFECT" → expectimax 档位效用封顶（全部动作 2.00
     平手）→ 每回合建议 SKIP → 禁跳规则按动作价值硬打 → 稳定挑 buff 牌。
  2. **每回合出牌上限写死 3**：游戏**默认每回合只能出 1 张牌**（一手 3 张是"选 1 张"；
     额外出牌次数来自卡效果/P 道具）。证据：四场采集考试共 39 个实战回合，32 回合正好
     1 张、7 回合 2 张（2 张的都是卡效果 `ExamPlayableValueAdd`）；课程实拍同样"打 1 张
     回合数 -1"；社区/维基口径一致。旧搜索写死 `play_limit=3`（"手牌 3 张"的误读），
     于是"buff + 两刀"在模型里永远划算 → 每回合先铺 buff，整节课 0 分。
- 修法：
  - `vision/lesson.py`：`LessonReader` 读圆环档位（`CLEAR截止` / `PERFECT截止`）+ 按
    "属性值 − 开课属性值"换算课程分；过关线 = 已得分 + 圆环还差分；满分线查档位表
    （普通/SP = 2× 过关线；追い込み 90→360、165→600）。`LessonState` 新增
    `perfect/goal/attr`，`score` 语义改为"本课已得分"；`reset_lesson()` 每课重置属性基线。
  - `policy/lesson.py`：`_search_state` 改 `play_limit=1`（额外出牌走 `extra_plays`），
    满分线用读屏换算值；**硬打保证得分**——搜索建议 SKIP 时，先筛"屏幕分数预览 > 0"的
    牌（buff 牌记 0）按（搜索价值, 屏幕分）排序硬打（搜索在"反正到不了 CLEAR"的回合会
    把动作打成平手，旧排序会挑中 buff）。
  - `auto_produce.py`：每节课开始 `lesson_reader.reset_lesson()`；`lesson_score` 现在记
    **真课程分**（0 分也记，不再把属性值 90 写成 `lesson_score=90`）。
- 测试：`tests/test_lesson_play_f42.py` 3 条（真机帧 HUD 换算 + DoD 回放"最后一回合必须
  选魅力的基础 29、不选 buff" + "buff 多/分数少"合成场景）+
  `test_policy_engine.py::test_hardplay_prefers_scoring_card_on_flat_tie` +
  `test_lesson.py` 4 条假 OCR HUD 换算（属性基线/新开课重置/档位读不到沿用/满分线档位表）。
- **遗留（不属于 A2，已记 FAILURES #42 与 T5/B3）**：`sim/lesson.py` 的
  `plays_per_turn` 默认 3 也要对齐真机规则（默认 1 张 + 额外出牌），模拟器整局 A/B
  数字要重新标定；考试侧同样受影响（不是只课程）。

### A3. F#43 静态结果页空转 ✅ 2026-11-22 完成
- 现象：`result-tap/gain` 连点 10 次被自保护停局。
- 修法：静态页第 3 次起找「下一步/继续/完成/领取」按钮，找不到再点中央；补回归测试。
- DoD：真机/离线截图回放能推进到下一屏。

**落地（2026-11-22）**
- **真根因和最初判断不同**（看 `data/auto/step_020..029.png` 才查清）：那 10 帧不是结果页，是
  **日文饮料选择事件屏**（ヨーグルトパフェ -100P / つくねハンバーグ -50P / ドリンクバー 免费）：
  1. 旧中文 OCR 字典无假名 → 三条选项行一条都读不出 → `option_rows=0`，事件屏识别不出来；
  2. 飘字正则 `[+\-]\s*\d+` 把右侧 P 费标签「-100 / -50」当成 +N 飘字 → 走 `result-tap/gain`
     点屏幕中央 (360,1000)（对话区）→ 连续 10 步空转停机。
- **修法**（F#43）：
  - `_GAIN_RE` 只认正收益（`+45`/`＋45`），负数是 P 费/体力消耗，绝不当飘字；
  - 事件屏退化兜底：`option_rows=0` 但读得到 P 费标签时，用「最后一个费用标签中心 +138px」
    点免费项；`_EVENT_ROW_COST_RE` 放宽到 3 位（`-100`）；
  - 静态结果页：第 3 次飘字起每帧找「下一步/继续/确定/完成/关闭/领取/了解」，找不到才继续点中央；
  - A1 日文 OCR 后该屏本身已能读出选项 → 走 `event-choice/last-row` 点第 3 行免费项。
- **测试**：`tests/test_produce_ui_f43.py` 7 条（3 条真机帧回放：`tests/fixtures/event_ep_t3_4_drink_choice.png`
  → `event-choice/last-row` 点 (360,935)、同帧第二次 = 确认、同屏连续 10 步无 `result-tap`；
  4 条合成单测：P 费不是飘字 / 无选项文字时用费用标签 / 静态页第 3 下点「下一步」/ 没按钮保持计数）。
- **基线复核**：全量 pytest **941 passed / 1 skipped**（942 收集 / 67 个测试文件；A3 当时口径，
  A4 后为 950/1、951 收集 / 68 文件，见下方 A4）；①②③④ 其余数字不变
  （④ 仍 36/36、3/3、29/29、beam 28）。
- **DoD（离线）**：真机帧回放从 `result-tap/gain` 空转变成 `event-choice/last-row` → `confirm`
  两步推进；真机整局验收留到阶段 E（T1）。细节见 [FAILURES #43](FAILURES.md) / HANDOVER 二·补十六。

### A4. 离线回归素材（为"全部离线做完再跑真机"服务）✅ 2026-11-22 完成
- 把本次真机截图（`data/auto/step_*.png`、`fail_*`）挑关键屏归档成 `tests/fixtures/*.png`（或 `data/replays/`，
  `.gitignore` 已有 `data/replays/*`），做**截图回放测试**：OCR→decide→期望动作；
- 挑帧工具（A3 已随手落地）：`scripts/scan_event_frames.py` 扫截图找事件选项屏；
  `scripts/probe_frame_decide.py <step>` 把单帧走一遍生产链路（read_fast→decide）看判定/点击；
- DoD：至少覆盖：日文剧情二选一、课程 buff 场景、结果页、外出事件、考试浮层、回合结束确认框。

**落地（2026-11-22）**
- **归档**：`tests/fixtures/` 新增 6 张真机帧（另沿用 A2/A3 已归档的 2 张），新增
  `tests/fixtures/README.md` 记录每张的屏型/episode/step/时间/测什么/怎么再挑帧：
  日文剧情二选一（ep-t3-3 step49）、课程 buff（ep-t3-4 step1）、结果页（ep-t3-4 step4）、
  外出三选一（ep-full1 step49）、考试浮层（11-15 实拍）、真机确认弹窗（ep-t3-4 step19）、
  持有上限保留饮料（11-14 实拍）、外出饮料事件（A3 ep-t3-4 step21）。
- **回放测试**：`tests/test_frames_replay_a4.py` 9 条，全部是「真像素 → 真 OCR（A1 日文模型）→ 生产
  `read_fast`/`decide`」：剧情二选一（读得出两条假名选项、点气泡不点快进 F#41）、课程 buff 全链路
  （`decide` 交给 `LessonPolicy` → 打「魅力的基础」29 分，F#42）、结果页（`result-tap` → 第 3 次
  `next`，A3 修法）、外出三选一（`event-choice/last-row` → `confirm`，负 P 费不是飘字）、考试浮层
  （`exam_mode` + `card_detail_open` + audition 手牌 + 考试永不禁跳 F#17/F#32）、真机确认弹窗
  （点 OCR 读到的「确定」）、**回合结束确认框**（真机课程帧 OCR 行 + F#36 真实弹窗文案）、
  **持有上限保留饮料**（`_checkbox_bands` 勾选框扫描 + 点勾选框）。
- **工具**：新增 `scripts/scan_frames.py`——目录/glob/单帧批量走 `read_fast→decide`，输出
  `screen/action/点击坐标/OCR 文本`，支持 `--screen/--contains/--json/--limit`（A4 挑帧真源；
  `scan_event_frames.py` 仍是廉价小框预扫）；`probe_frame_decide.py` 的假 device 补 `click/swipe`。
- **回放抓到并修掉的真机 bug（F#44）**：`ProduceDriver._checkbox_bands` 漏 `@staticmethod`，
  真机「持有上限/还可选择 N 个」弹窗带 image 进分支会 `TypeError`（合成单测不传 image 所以此前没红）；
  修后 `data/drink3.png` 回放 → `drink-keep/check-row` 点勾选框列 (632,897)。已记 [FAILURES #44](FAILURES.md)。
- **缺口（如实记录）**：**回合结束确认框的真机帧已不存在**——`step_NNN.png` 轮转覆盖，含该弹窗的
  旧局（ep-cplus11 / ep-finish3/4/5 / ep-exp4）截图被后续 ep-t3 跑局盖掉。`scan_frames.py` 扫了
  1352 张归档截图（data/auto step+fail 487、data/manual/arun/bench/video/ssr 511、data 根目录 354）
  + data/bench 26 张，**0 帧**命中「结束回合/尚可使用技能卡」。该分支用「真机课程帧 OCR 行 +
  FAILURES #36 真实弹窗文案」回放；**下次真机跑局出现该弹窗时补拍**
  `tests/fixtures/turn_end_confirm_<episode>_stepNNN.png`（挑帧命令已写进 fixtures README）。
- **DoD 对照**：六类屏全部有回放；5 类用真机帧，回合结束确认框用「真机课程帧文字 + 同 UI 组件的
  真机确认弹窗帧」兜底（原因见上，等真机补拍补成纯真机帧）。
- **基线复核**：全量 pytest **950 passed / 1 skipped**（951 收集 / 68 个测试文件，含 A4 新增 9 条）；
  ① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 24/24、④ wiring 36/36 + 3/3 + known_draw 29/29 +
  beam 28 全部不变（A4 只加素材/测试 + 一个漏装饰器修复，不动数据链路）。

### A5. T3 离线预演（不碰真机）
- 用新采集的 `traffic.jsonl` 跑 `build_exam_setup.py --current --allow-finished`，用 `ExamPlanSelector` 离线核对
  `locked_turn/verified`；把流程写成脚本（若需要）。
- DoD：候选收敛到 1、`locked_turn<=3`；结论写回 EXPECTIMAX/HANDOVER。

---

## 阶段 B：策略强度与机制（离线，可与 A 并行）

### B1. T4 受控 policy-evaluation 叶子
- 只对 beam 最深端点 rollout、用执行同策略（within）+ 缓存 + 小预算；决策门：真实牌组 beam ≥ within 的 90% 再谈生产。
- DoD：配对评测数字（60 局）+ `EXPECTIMAX.md` 更新 + 单测。

### B2. T4 数据驱动：用全知数据训练叶子/小模型（新增方向）
- 用采集的 exact（state, action, score, deck/seed）数据构造监督样本；teacher = 全知搜索/真值；
  student = V_leaf 或小 policy；离线配对评估；可行再接 `engine=`。
- 参考：群论文的 Bellman/在线搜索 + 2B 模型培育决策（只学思路）。
- DoD：离线配对显著优于解析式 leaf（或给出可复现负结果+结论），文档记录。

### B3. T5 机制建模（用群论文公开公式对照，先做核验表）
- 逐条对照 `RULES_REFERENCE`：好调 `1.5+0.1g`、好印象年金 `W(r,T)`、审查倍率分段/联动惩罚、
  单精度舍入、支援强化尝试/成功/层数分布、牌组/轨迹计数；
- P 道具/回忆/附魔/选牌/减益：按官方 AI 对比表挑性价比补；
- 额外 RNG 机制（panic/search/generate/move）：现在只做**事前检测停机**；能否建模取决于新采集数据。
- DoD：差异表 + 补丁 + 配对回归（模拟器 vs 实机逐分）。

---

## 阶段 C：可靠性（离线）

### C1. 执行层可靠性（参考 GKMSMAA 架构，**自写代码不拷贝**）
- tap 确认/重试（tap 丢失、对话未开、picker 选牌、同屏循环）；
- 提权检查（游戏 elevated / 本进程 non-elevated 的失败提示）；
- 动作前预算下一帧（hiro 原则）、每步可复盘（日志已有 `eng/fallback`，补动作理由）；
- DoD：对应失败场景单测；真机日志能复盘每一步。

---

## 阶段 D：数据（离线准备，真机时执行）

### D1. 采集扩展
- 目标：① 同卡组多局（T2 A/B 用）；② 牌组含额外 RNG 机制卡的考试（建 panic/search/generate/move 数据）；
- 产出：`traffic.jsonl` / `out/exam_setup*.json` 入私有存档（不入库）。

---

## 阶段 E：真机（A–D 全做完后再做）

### E1. T3 实战验收
- 开采集 → bot 起局 → 考试中 `build_exam_setup --current` → 验收：
  `[exam-plan] locked_turn=2~3`、`verified == 实战回合数`、无错误牌序；
- DoD：真机日志 + HANDOVER/RUNS 记录。

### E2. T1 整局验收
- 严格引擎（expectimax）、`--ignore-user`、`--max-minutes 30`、禁静默回退；
- DoD：≥ C+、≤20 分钟、无"有牌却 SKIP"、无 `[engine][BLOCKED]`；写 RUNS。

### E3. T2 三引擎真机 A/B
- 同卡组/同 setup：rules（仅对照）/ expectimax / beam+全知，各一局；
- 记录考试分/评价/时长/fallback；结论写 EXPECTIMAX.md。

---

## 阶段 F：gkbench 算法对比（最后）

> 先确认"那个网站"= gkbench（`hiro.matto.top/gkbench`）还是群内自建榜；两者规则可能不同。

- **规则红线**：gkbench ranked **禁止 seed/牌序**；我们能提交的是"只看 UIObs 的算法"（rules/expectimax/学习模型），
  **不能**带 MITM/known_draw；oracle/看牌序是单独类别，只作上限参照。
- 任务：
  1. 读 `data/bench_repo`（MIT 本地克隆）确认提交协议（动作 `p<i>/d<i>/e/s<i,j>`、UIObs 字段、裁判口径）；
  2. 写一个 **public-safe 适配器**（自包含、不用 seed、不读本公司私有数据），本地裁判跑分；
  3. 对齐公开数字：UIHorizon ≈631k（0.511×oracle）、UINet ≈579k（0.455×）、官方 AI ≈233k（0.213×），
     oracle 基准 ≠ 最优（1.45M 为多起点 best-known 分母）；
  4. 若能提交（需账号/token/规则确认）：提交并记录 host 返回；否则写本地对照报告并注明口径差异；
- DoD：本地/托管的同口径分数 + 一页对照表（我们 vs UIHorizon vs UINet vs 官方 AI；标注是否用 seed）。

---

## 阶段 G：收尾

- 更新 HANDOVER/EXPECTIMAX/RULES_REFERENCE/RUNS/PROVENANCE；`pytest` 全绿；提交 + 私有仓库 Push；
- 情报更新（群/论文/封堵动态）；对外继续不公开细节。

---

## 新会话开场白（复制）

```
工作目录 D:\Games\gakumas-agent。
读 docs/INDEX.md → docs/WORKPLAN.md（总计划）→ docs/HANDOVER_NEXT.md §2 跑四条基线，
然后按 WORKPLAN 的 阶段 A→B→C→D 离线推进；全部离线做完后再做 阶段 E 真机（T3→T1→T2），
最后 阶段 F 去 gkbench 比算法（ranked 禁 seed，只能交不看 seed 的算法）。
用户规则：SKIP 只在真没体力；禁止静默回退 rules；真机整局 --ignore-user。
A1（OCR 换日文模型）已于 2026-11-22 完成（官方 PP-OCRv6；见 WORKPLAN A1 / HANDOVER 二·补十四）。
A2（F#42 课程硬打必须得分）已于 2026-11-22 完成（HUD 语义 + 每回合 1 张 + 硬打保分；
见 WORKPLAN A2 / HANDOVER 二·补十五）。
A3（F#43 结果页空转）已于 2026-11-22 完成（真根因是日文饮料选择事件屏 + P 费标签被当飘字；
见 WORKPLAN A3 / HANDOVER 二·补十六）。
A4（离线回放素材）也已完成（8 张真机帧归档 + 9 条真机帧回放测试 + scan_frames 挑帧工具；
见 WORKPLAN A4 / HANDOVER 二·补十七）。今天做 A5（T3 离线预演：`build_exam_setup.py --current
--allow-finished` + `ExamPlanSelector` 离线核对 locked_turn/verified）。
```
