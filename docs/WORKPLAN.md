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
| T4 平手项/beam 采样实验（+19.9 旧数字已作废；B1 修正后 beam 已超 within；B2 学习叶子再 +7.7） | `EXPECTIMAX.md`；rollout 叶子负结果也记录在案 |
| T1 真机流程 10+ 类卡点 + F#41（日文剧情二选一）修复 | `FAILURES.md` #27-41；`584f742` |
| A1 OCR 换日文/多语言模型（官方 PP-OCRv6，Apache-2.0） | `tests/test_ocr_jp_model.py` 真图 4 条 + `test_ocr_config.py` 17 条；全量 pytest 926/1；`docs/HANDOVER` 二·补十四 |
| A2 课程硬打必须得分（F#42：HUD 语义 + 每回合 1 张 + 硬打保分） | `tests/test_lesson_play_f42.py` 真图回放 3 条 + `test_lesson.py` HUD 换算 4 条 + `test_hardplay_prefers_scoring_card_on_flat_tie`；全量 pytest 934/1（935 收集 / 66 文件）；`docs/HANDOVER` 二·补十五 |
| A3 F#43 结果页空转（真根因：日文饮料选择事件屏 + P 费标签命中飘字正则） | `tests/test_produce_ui_f43.py` 7 条（真机帧回放 3 + 合成 4）；全量 pytest 941/1（942 收集 / 67 文件）；`docs/HANDOVER` 二·补十六 |
| A4 离线回放素材（六类关键屏真机帧归档 + 回放测试 + 挑帧工具） | `tests/fixtures/` 8 张真机帧 + `README.md` 溯源表；`tests/test_frames_replay_a4.py` 9 条；`scripts/scan_frames.py`；顺带修 `_checkbox_bands` 真机 TypeError（F#44）；全量 pytest **950/1（951 收集 / 68 文件）**；`docs/HANDOVER` 二·补十七 |
| A5 T3 离线预演（`--current` 候选 + `ExamPlanSelector` 逐回合锁定） | `scripts/verify_exam_plan_offline.py`：最新场 3 候选第 2 回合锁定 `config_turns=12`（真值 12），四场 sweep 全部 T1–T2 锁定且选对真值；候选收敛到 1、`locked_turn<=3`；`tests/test_exam_plan_offline.py` 8 条；全量 pytest **958/1（959 收集 / 69 文件）**；`docs/HANDOVER` 二·补十八 |
| B1 T4 修正（评测执行器 bug + 受控 frontier 叶子） | `tests/test_beam_frontier.py` 6 条；`scripts/eval_t4_b1.py` 60 局配对：beam unknown **164.0** / known **165.5** vs within **143.1**（+20.9 / +22.4，CI 全正；决策门 114.6%/115.7% PASS）；frontier 叶子中性；全量 pytest **964/1（965 收集 / 70 文件）**；`docs/EXPECTIMAX` T4 修正 |
| B2 全知数据训练 MLP 叶子 | `scripts/build_b2_dataset.py` + `train_b2_leaf.py` + `eval_b2.py`；beam 全知自对弈 26.5k 叶子样本 → MLP 104→96→48（val r²=0.943）；**确认段 120 局配对：beam 157.8 → 165.5（learned，+7.7 CI[+4.2,+11.2]）/ 166.9（ensemble 0.5，+9.0 CI[+5.8,+12.2]）**；CLEAR 95→98.3%、PERFECT 33.3→50%；within 用 learned 变差 −3.3（负结果记录）；`tests/test_b2_leaf.py` 11 条；全量 pytest **975/1（976 收集 / 71 文件）**；`docs/EXPECTIMAX` B2 学习叶子（**B3 后旧模型失效，待重训**） |
| B3 T5 机制建模（回合规则 + 核验表） | 模拟器对齐真机：每回合基础 **1 张** + 打完自动结束回合 + SKIP 回 2 体力 + 取整 `safeCeil`（`sim/lesson`、`sim/expectimax`、`sim/uiobs` 等）；真机 39 回合配对回归（`tests/fixtures/t5_exam_turn_rules.json` + `scripts/export_t5_turn_rules.py`）；`RULES_REFERENCE.md` 重写逐条核验表；实机回放黄金值 12 条；重标定：`sim_engine_ab` expectimax 显著强于 rules（+342~+429 评价点）、B1 60 局 within 89.1→beam 95.7（+6.6，门 107.4% PASS）、B2 旧模型 FAIL 待重训；全量 pytest **985/1（986 收集 / 72 文件）**；`docs/HANDOVER` 二·补二十一 |
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

### A5. T3 离线预演（不碰真机）✅ 2026-11-22 完成
- 用新采集的 `traffic.jsonl` 跑 `build_exam_setup.py --current --allow-finished`，用 `ExamPlanSelector` 离线核对
  `locked_turn/verified`；把流程写成脚本（若需要）。
- DoD：候选收敛到 1、`locked_turn<=3`；结论写回 EXPECTIMAX/HANDOVER。

**落地（2026-11-22）**
- **脚本** `scripts/verify_exam_plan_offline.py`：一条命令跑两条路径——① `--current --allow-finished`
  候选（`--refresh` 时现场重建，等价 CLI）用最近一场考试 truth 驱动 selector；② 四场已结束考试
  各造 9/11/12 候选的 sweep。输出 `locked_turn` / 选中 `config_turns` / 锁定后逐回合核对 /
  `known_draw` 覆盖下一手；退出码 = DoD 是否通过，`--json` 给明细。
- **结果**（最新场 = 11-21 17:38 期末 seed=0x1E1A740D、牌堆 27 张）：
  - `--current` 3 候选（9/11/12）**第 2 回合锁定 `config_turns=12`（真值 12）**，锁定后手牌核对
    11/11（T2–T12），`known_draw` 覆盖下一手 9/9；T12 打出考试内生成卡 → 按数据限制提前停下
    （不算失败，与 `verify_exam_wiring` 同口径）。
  - 四场 sweep：考试0/1/2 第 1 回合锁定、考试3 第 2 回合锁定；选中 `config_turns` = 9/11/9/12，
    全部等于真值；候选 3→1；`locked_turn` 最大 2（DoD ≤3）。第 1 回合分不出的场是 isInitial 卡
    相同，第 2 回合收敛，与 QQ 群「2–3 回合锁定 seed」口径一致。
- **DoD 对照**：候选收敛到 1 ✅、`locked_turn<=3` ✅；结论写回
  [EXPECTIMAX §④](EXPECTIMAX.md) 与 [HANDOVER 二·补十八](HANDOVER.md)。
- **测试**：`tests/test_exam_plan_offline.py` 8 条（候选复制 / truth 驱动统计 / 真实与错误候选 /
  生成卡提前停止 / DoD 判定 / CLI 全链路）；ruff 通过；全量 pytest **958 passed / 1 skipped**
  （959 收集 / 69 文件）。
- 真机 T3 验收（考试进行中跑 `--current` + bot 运行时重载 + `[exam-plan] summary`）留到阶段 E。

---

## 阶段 B：策略强度与机制（离线，可与 A 并行）

### B1. T4 受控 policy-evaluation 叶子 ✅ 2026-11-22 完成
- 只对 beam 最深端点 rollout、用执行同策略（within）+ 缓存 + 小预算；决策门：真实牌组 beam ≥ within 的 90% 再谈生产。
- DoD：配对评测数字（60 局）+ `EXPECTIMAX.md` 更新 + 单测。

**落地（2026-11-22）**
- **先查出并修掉真正的瓶颈：评测执行器 bug**。`LessonSim.step` 在「手牌打空」时自动结束
  本回合；旧 `eval_known_draw._execute_plan` 在按 beam 计划打光 3 张后又补了一个 SKIP，
  把**下一整个回合**白丢 → 旧 beam 数字（111.2）被系统性低估；within 不走该执行器所以
  一直是真实的 143.1。修法：记 `start_turns_left`，同回合才补 SKIP（回归测试 2 条）。
- **受控 policy-evaluation 叶子**：`search_beam(frontier_value=...)` 只对预算截断后的最深
  端点用 `within` rollout（每回合 5ms、`canonical` 缓存）重排，终局端点用精确档位效用、
  不 rollout；默认 `None` 行为逐位不变（测试 4 条）。
- **60 局配对**（small，同牌组同 seed；`scripts/eval_t4_b1.py --games 60`）：
  within 143.1；beam **unknown 164.0**（+20.9，CI [+14.4,+27.3]）、
  **known 165.5**（+22.4，CI [+16.5,+28.4]）；决策门 **114.6% / 115.7% → PASS**（≥90%）。
  `beam+frontier` 与普通 beam 逐位相同（前沿收敛到同状态，叶子中性）。
- **消融**：起作用的是 `score_tiebreak=1e-3`（+15.4 / +11.8），branching=10 修正后无显著
  收益（旧 +19.9 是 bug 副产物）。生产默认（expectimax / tiebreak=0）本任务不改，T2 真机
  A/B 时再把 `beam + tiebreak` 作为候选。
- 测试 `tests/test_beam_frontier.py` 6 条；全量 pytest **964 passed / 1 skipped**
  （965 收集 / 70 文件）；`EXPECTIMAX.md` 新增「T4 修正」并给旧 beam 表加作废标注。
- 下一步：**B2**（rollout/全知数据训练叶子，必须用修正后的 harness 重测）。

### B2. T4 数据驱动：用全知数据训练叶子/小模型（新增方向）✅ 2026-11-22 完成
- 用采集的 exact（state, action, score, deck/seed）数据构造监督样本；teacher = 全知搜索/真值；
  student = V_leaf 或小 policy；离线配对评估；可行再接 `engine=`。
- 参考：群论文的 Bellman/在线搜索 + 2B 模型培育决策（只学思路）。
- DoD：离线配对显著优于解析式 leaf（或给出可复现负结果+结论），文档记录。

**落地（2026-11-22）**
- **数据**：`scripts/build_b2_dataset.py` + `RecordingLessonSim`（`src/gkagent/sim/leaf_data.py`）：
  beam **全知**自对弈，在 `_draw_hand` 入口记录**叶子状态**（与 `_Search.leaf` 的
  `end_turn_state` 同形态：手牌进弃牌堆、好印象 -1、buff 倒计时、回合 -1），标签 = 最终分 −
  叶子分。三批 teacher（width4/100ms 1500+3000 局、width8/300ms 800 局）→ **26,500 样本**。
- **模型**：`src/gkagent/sim/leaf_mlp.py`：104 维结构化特征（状态/分数缺口/体力、buff、指針、
  饮料/P 道具、**牌库 vs 弃牌堆拆分**、效果聚合、交互项）+ MLP 104→96→48（μ MSE + σ 残差头
  NLL），实现 `LeafValue` 协议；`scripts/train_b2_leaf.py` 按 seed 分组 9:1 切分；
  held-out r²=0.943 / MAE 8.8。模型 `data/knowledge/b2_leaf_mlp_small.json`（335KB，tracked）。
- **评测**：`scripts/eval_b2.py` 复用 B1 修正 harness（同牌组同 seed 配对 + 95% CI）：
  - 选择段 seed 2000–2079（80 局 unknown）：beam 解析式 166.8 → **learned 173.7（+6.8
    CI[+3.2,+10.4]）/ ensemble 0.25 174.4（+7.5 CI[+3.7,+11.4]）**；
  - **确认段 seed 3000–3119（120 局，未参与选择）unknown**：157.8 → **165.5（+7.7
    CI[+4.2,+11.2]）/ ensemble 0.5 166.9（+9.0 CI[+5.8,+12.2]）**；known：159.9 → **167.1
    （+7.2）/ ensemble 0.25 167.7（+7.8）**；CLEAR 95.0→98.3%、PERFECT 33.3→50.0%。
  - **DoD 达成**（beam 离线配对显著优于解析式叶子）；B1 基线逐位复现（within 143.1 /
    beam 164.0/165.5，seed 0–59）。
- **负结果**（写进 EXPECTIMAX）：within 用 learned 叶子显著变差（−3.3，教师策略收益偏乐观）；
  within 自对弈叶子 ≈ 中性（+0.9 n.s.）；档位概率头在 beam 上灾难性变差（P(CLEAR) 饱和）；
  第二轮专家迭代未超过第一轮。**结论：B2 叶子只对 `engine=beam` 有益**。
- **生产接线**：`LessonPolicy` 新增可选 `leaf_model`/`leaf_model_weight`（默认 None = 行为不变，
  `_leaf_value` 加缓存）；**不默认打开**，T2 真机 A/B 候选（仅 beam 引擎）。
- **测试/基线**：`tests/test_b2_leaf.py` 11 条；全量 pytest **975/1（976 收集 / 71 文件）**；
  ①③④ 基线全部不变。细节见 [EXPECTIMAX](EXPECTIMAX.md)「B2 学习叶子」与 HANDOVER 二·补二十。

### B3. T5 机制建模（真机回合规则对齐 + RULES_REFERENCE 核验表）✅ 2026-11-22 完成
- 逐条对照 `RULES_REFERENCE`：好调 `1.5+0.1g`、好印象年金 `W(r,T)`、审查倍率分段/联动惩罚、
  单精度舍入、支援强化尝试/成功/层数分布、牌组/轨迹计数；
- P 道具/回忆/附魔/选牌/减益：按官方 AI 对比表挑性价比补；
- 额外 RNG 机制（panic/search/generate/move）：现在只做**事前检测停机**；能否建模取决于新采集数据。
- DoD：差异表 + 补丁 + 配对回归（模拟器 vs 实机逐分）。

**落地（2026-11-22）**
- **真机回合规则核实**：每回合基础 **1 张**（gakumas-tools `TurnManager.startTurn`
  的 `cardUsesRemaining=1` + 真机 4 场考试 39 回合日志：32 回合 1 张、7 回合 2 张，
  每回合手牌都 3 张）；打完最后一张**自动结束回合**（`CardManager.useCard` 末尾）；
  回合末还有剩余次数（SKIP）**回 2 体力封顶**（`TurnManager.endTurn`）。
- **补丁（4 项）**：① `plays_per_turn`/`play_limit`/`DEFAULT_PLAY_LIMIT` 默认 3→1
  （`sim/lesson`、`sim/expectimax`、`sim/play_choice`、`sim/uiobs`、`sim/v_leaf`、
  `scripts/local_bench.py`）；② 出牌次数用尽/手牌空自动结束回合；③ SKIP 回 2 体力
  （`_end_turn` / `end_turn_state`）；④ 取整对齐 `safeCeil`（buff 段一次 + 回合倍率一次；
  旧课程 floor / 考试 round 一次）。实机回放黄金值：考试 250% 9→23、好调→35、愛嬌 13→50、
  情熱ターン 11 集中 0/3/6→28/35/43；课程好调 10→15、5→8、2→3；温存 9→5、2→1、15→8。
- **配对回归**：`scripts/export_t5_turn_rules.py` → `tests/fixtures/t5_exam_turn_rules.json`
  （真机 39 回合摘要 + 溯源）；`tests/test_t5_turn_rules.py` 9 条；`test_sim_lesson.py`
  实机黄金值 2 条（课程 6 值 + 考试 6 值）。
- **核验表**：`RULES_REFERENCE.md` 重写为逐条核验（回合规则 / `resolveScore` 顺序与取整 /
  buff 生命周期与好印象年金 / 牌序 4/4+3/3 ✅ / 审查倍率 ❌ 仍常量 4.11 / 熱意、温存解除
  额外次数、P 道具、fresh buff 差一回合等差距及证据）。
- **重标定**（旧数字全部不可混比）：`sim_engine_ab` 76 局 0 blocked/0 异常/C+ 100%，
  expectimax 从噪声内变**显著更强**（rules vs expectimax P50 5170→5566 / 5176→5505 /
  5152→5513，配对 Δmean +372/+342/+429）；B1 60 局 within 89.1 → beam 95.7（+6.6，
  CI [+2.2,+11.1]，决策门 107.4% PASS）；**B2 旧模型重测 FAIL**（确认段 beam 94.9→learned
  67.1，−27.9，ensemble 0.75 −5.3）→ 必须按 B3 规则重采数据重训；400 局培育标定带
  650–1100→950–1450。
- **测试/基线**：全量 pytest **985 passed / 1 skipped**（986 收集 / 72 文件）；
  ① 洗牌 4/4+3/3、③ 4/4 场 86/86+24/24、④ 36/36+3/3+29/29+beam 28 全部不变。
- **下一步（T5 剩余）**：审查倍率分段+联动惩罚、熱意（独立资源）、温存解除 +1 出牌/元气、
  fresh buff 差一回合（真机截图核实）、P 道具数据接入；然后阶段 C/D。

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

> 已确认：就是 **gkbench（`hiro.matto.top/gkbench`）**；本地克隆 `data/bench_repo`（MIT）。
> **2026-11-22 用户已登录 gkbench，可以下载公开的「固定种子题」（开发集种子，含 `loadout.seed`
> 和起点核对 `check`）——这改变了 F 的做法**：以前只能拿题模板（无种子）本地跑，现在可以
> 用官方种子做**独立交叉验证 + 理论上限分母**。

- **规则红线**：gkbench ranked **禁止 seed/牌序**（ranked 用保密种子，只托管跑、算法只看画面）；
  我们能提交的是"只看 UIObs 的算法"（rules/expectimax/学习模型），**不能**带 MITM/known_draw；
  下载到的固定种子题（开发集）**只用于本地跑/理论上限当分母**，官方页面也不把它单列排行
  （`privileged` = 看种子的理论上限，只作分母）。
- **F0（新，先做）：官方种子交叉验证 + 口径校准**
  1. 下载固定种子题（`GET /api/sets/<set>/saves?fixed=1` 的 NDJSON，或题集页「下载存档/固定种子」
     按钮；每个存档 = `gkms.audition_save.v2`，`loadout.seed` + `check{turn,score,stamina,hand,rules}`）；
     公开 API / 批量下载工具 / 参考分见 [GKBENCH.md](GKBENCH.md)（`scripts/bench_download.py`）；
  2. **用我们的洗牌模型从 `seed`+牌组预测开局手牌/回合属性，和 `check.hand` 逐张对照**——
     这是对「MITM seed→洗牌」最核心资产的外部独立校验（几百道 H.I.F 题的免费回归集）；
  3. 用 `check` 的 `turn/score/stamina/rules` 校准我们的考试起点状态与规则版本；
  4. 对照榜上参考分/理论上限（oracle 分母），分清"裁判口径差异"和"算法差距"；
  - DoD：洗牌预测命中率（逐题逐张）+ 不一致样本根因 + 报告写进 [GKBENCH.md](GKBENCH.md) / [COMPARE.md](COMPARE.md)。
- 任务：
  1. 读 `data/bench_repo`（MIT 本地克隆）确认提交协议（动作 `p<i>/d<i>/e/s<i,j>`、UIObs 字段、裁判口径）；
  2. 写一个 **public-safe 适配器**（自包含、不用 seed、不读本公司私有数据），本地裁判跑分；
  3. 对齐公开数字：UIHorizon ≈631k（0.511×oracle）、UINet ≈579k（0.455×）、官方 AI ≈233k（0.213×），
     oracle 基准 ≠ 最优（1.45M 为多起点 best-known 分母）；
  4. 若托管提交（需账号/token/规则确认）：提交并记录 host 返回；否则写本地对照报告并注明口径差异；
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
然后按 WORKPLAN 的 阶段 B→C→D 离线推进；全部离线做完后再做 阶段 E 真机（T3→T1→T2），
最后 阶段 F 去 gkbench 比算法（ranked 禁 seed，只能交不看 seed 的算法）。
用户规则：SKIP 只在真没体力；禁止静默回退 rules；真机整局 --ignore-user。
A1（OCR 换日文模型）已于 2026-11-22 完成（官方 PP-OCRv6；见 WORKPLAN A1 / HANDOVER 二·补十四）。
A2（F#42 课程硬打必须得分）已于 2026-11-22 完成（HUD 语义 + 每回合 1 张 + 硬打保分；
见 WORKPLAN A2 / HANDOVER 二·补十五）。
A3（F#43 结果页空转）已于 2026-11-22 完成（真根因是日文饮料选择事件屏 + P 费标签被当飘字；
见 WORKPLAN A3 / HANDOVER 二·补十六）。
A4（离线回放素材）也已完成（8 张真机帧归档 + 9 条真机帧回放测试 + scan_frames 挑帧工具；
见 WORKPLAN A4 / HANDOVER 二·补十七）。
A5（T3 离线预演）也已完成：`scripts/verify_exam_plan_offline.py`——最新场 3 候选第 2 回合锁定
config_turns=12（真值 12），四场 sweep 全部 T1–T2 锁定且选对真值，候选收敛到 1、locked_turn≤3；
见 WORKPLAN A5 / HANDOVER 二·补十八。
B1（T4 修正）已于 2026-11-22 完成：查出评测执行器 `_execute_plan` 白丢回合 bug；
修正后 60 局配对 beam unknown 164.0 / known 165.5 vs within 143.1（+20.9/+22.4，CI 全正；
决策门 114.6%/115.7% PASS），受控 frontier 叶子中性；见 WORKPLAN B1 / HANDOVER 二·补十九。
B2（全知数据训练 MLP 叶子）已于 2026-11-22 完成：B1 修正 harness 上，beam 全知自对弈 26.5k
叶子样本训练 104 维 MLP（val r²=0.943）；确认段 120 局配对 beam 157.8 → 165.5（learned，
+7.7 CI[+4.2,+11.2]）/ 166.9（ensemble 0.5，+9.0），CLEAR 95→98.3%、PERFECT 33.3→50%；
within 用 learned 变差为已记录负结果（只对 engine=beam 有益）；见 WORKPLAN B2 /
HANDOVER 二·补二十 / EXPECTIMAX「B2 学习叶子」。
B3（T5 机制建模）已于 2026-11-22 完成：模拟器对齐真机「每回合基础 1 张 + 打完自动结束回合
+ SKIP 回 2 体力 + 取整 safeCeil」，`RULES_REFERENCE.md` 重写为逐条核验表，真机 39 回合
回合规则配对回归；重标定后 sim_engine_ab 里 expectimax 显著强于 rules（+342~+429 评价点，
B3 前是噪声内），B1 60 局 within 89.1→beam 95.7（+6.6，决策门 PASS），**B2 旧模型失效
（重测显著负）需按新规则重训**；全量 pytest 985/1（986 收集 / 72 文件）；见 WORKPLAN B3 /
HANDOVER 二·补二十一 / RULES_REFERENCE / SIMULATOR §11。
下一步从 **T5 剩余机制**开始（审查倍率分段+联动惩罚、熱意、温存解除额外次数、fresh buff
差一回合、P 道具数据接入）→ 阶段 C（执行层可靠性）/ D（补采集）离线做完 → 真机 T3→T1→T2
→ gkbench（ranked 禁 seed，只能交不看 seed 的算法）。
```
