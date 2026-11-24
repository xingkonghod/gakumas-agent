# tests/fixtures —— 真机截图回放素材（WORKPLAN A4）

这些 PNG 都是**真机截图**（720x1280），不是合成图；回放测试走生产链路
`ProduceDriver.read_fast`/`read` → `decide`（真 OCR 模型），见
[`tests/test_frames_replay_a4.py`](../test_frames_replay_a4.py)。
模型/配置缺失时测试自动 skip（干净 checkout 不会红）。

| 文件 | 屏幕类型 | 真机来源（episode / step / 时间） | 说明 |
|---|---|---|---|
| `story_choice_ep_t3_3_step049.png` | 日文剧情二选一（F#41） | ep-t3-3 step49，2026-11-22 02:14 | 培育开场剧情两气泡「飲み物を持ってきました / 慣れてきましたか?」+ 快进；旧中文 OCR 只读碎片→只点快进原地循环 |
| `story_choice_v361_ep_t31_a.png` | 开场二选一·v3.6.1 描述层（F#45） | ep-t31-a step44，2026-11-24 21:19 | 三气泡：白描述「选择并获得特定的P饮料」y690 / 橙选中「飲み物を持ってきました>」y790 / 灰「慣れてきましたか?」y890；旧逻辑点最上=描述层→同屏 10 次停机 |
| `enhance_state2_ep_t31_b.png` | 技能卡强化·状态2（F#46） | ep-t31-b 探针，2026-11-24 21:36 | 选中「魅力的基础」+「强化确认」预览 + 底部大「强化」执行按钮；旧逻辑无分支→story/tap 空转 |
| `focus_choice_v361_ep_t31_d.png` | 重点练习三选一（F#45/46） | ep-t31-d step123，2026-11-24 21:51 | 粉选中「重点练习歌唱」+ 灰舞蹈/视觉 + 描述「开始歌唱冲刺训练」；>> 未被 OCR 读出，靠 vivid 填充色判选中、点右侧箭头 |
| `drink_detail_v361_ep_t31_f.png` | P饮料详情模态弹窗（F#47） | ep-t31-f step72，2026-11-24 22:03 | 乌龙茶 元气+7 + 说明 + 底部「关闭」；旧 4.56 点中央空白→tap-lost 止损 |
| `lesson_ep_t3_4_step001.png` | 课程 buff 场景（F#42） | ep-t3-4 step1，2026-11-22 02:22 | 舞蹈课最后一回合 0 分：手牌 魅力的基础(29)/表情的基础(buff)/轻快步伐(23)；旧搜索连打 buff → 0 分 FAILED |
| `result_ep_t3_4_step004.png` | 结果页（F#43 同类屏） | ep-t3-4 step4，2026-11-22 02:22 | 课程结果页：三维属性条 + 「Da.上升了0!」浮字；日志写 `result-tap/gain` |
| `outing_choice_ep_full1_step049.png` | 外出事件（三选一） | ep-full1 step49，2026-11-19 18:41 | 「悠闲懒散 -8 / 彻底运动 / 去购物怎么样 -4」+ 快进；负 P 费不能被当 +N 飘字 |
| `exam_card_overlay_20261115.png` | 考试浮层（F#17/F#32） | 2026-11-15 17:17（考试实拍） | 考试页 1st..6th 排名条 + 卡片详情浮层「考试·舞台中仅限1次」+ SELECT + SKIP |
| `confirm_dialog_ep_t3_4_step019.png` | 确认弹窗（真机单帧） | ep-t3-4 step19，2026-11-22 02:23 | 「快进确认 / 未读的交流 / 是否快进? / 取消 / 确定」；和 F#8 回合结束确认框同 UI 组件 |
| `drink_limit_20261114.png` | 持有上限保留饮料（回放抓 bug） | 2026-11-14 01:03 | 「P饮料持有数量已达上限 / 请选择保留的3瓶饮料 / 还可选择2个」；暴露 `_checkbox_bands` 缺 `@staticmethod` 的 `TypeError` |
| `event_ep_t3_4_drink_choice.png` | 外出饮料选择事件屏（F#43） | ep-t3-4 step21，2026-11-22 02:23 | A3 归档：ヨーグルトパフェ -100P / つくねハンバーグ -50P / ドリンクバー 免费；P 费不是 +N 飘字 |

## 非图片素材：真机回合规则回归（WORKPLAN B3 / T5）

`t5_exam_turn_rules.json` 不是截图，是 **4 场考试 39 个回合的真值摘要**（每回合出牌数、
回合开始手牌数、首张牌、首张牌是否带 `ExamPlayableValueAdd`），用于
[`tests/test_t5_turn_rules.py`](../test_t5_turn_rules.py) 的「每回合基础 1 张 +
额外出牌次数」配对回归。

- 来源：`C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl` 的
  `StepAuditionEndExamBattle` 请求（`decode_exam_actions.py` 解出
  `exam_truth.json`）+ `data/knowledge/card_table.json` 的卡牌效果。
- 生成：`.venv\Scripts\python.exe scripts\export_t5_turn_rules.py`（可重跑；
  采集文件不在时脚本报错退出，不影响 pytest —— fixture 已随仓库提交）。
- 事实：39 回合里 **32 回合正好 1 张、7 回合 2 张**；每回合开始手牌都是 **3 张**
  （证明「1 张」不是手牌不够）；2 张的 7 个回合里 **3 个**首张牌带额外出牌效果，
  其余 4 个按 **P 道具追加**（采集不含 P 道具数据，只能说明不超过 2 张）。

## 非图片素材：考试属性倍率（审查倍率）回归（WORKPLAN B4 / T5①）

`t5_exam_multipliers.json` 不是截图，是 **2026-11-20 采集局期中/期末两场的属性倍率快照**：
每场记录偶像卡 id / 剧本 id / 考试开始三维、主数据考试配置（回合数、审查基准
`vocal/dance/visual`、分数表分段节点 `[parameter, vocalPermil, dancePermil, visualPermil]`）、
以及用客户端公式算出的三项倍率与中间量（components / penalties / common）。用于
[`tests/test_exam_multiplier.py`](../test_exam_multiplier.py) 的「分段折线 + 联动惩罚」回归。

- 来源：`C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl`（`Produce/Start` 的偶像卡、
  `StepAuditionStart` 响应的培育三维 `UserProduceProgress.vocal/dance/visual`）+
  主数据 `catalog.sqlite`（gakumasu-diff 快照：`ProduceStepAuditionDifficulty` →
  `ProduceExamBattleConfig` → `ProduceExamBattleScoreConfig` + `Setting` 惩罚上下限 100/250）。
- 生成：`.venv\Scripts\python.exe scripts\export_exam_multipliers.py`
  （`--check` 只校验不落盘；主数据/采集不在时脚本报错退出，不影响 pytest —— fixture 已提交）。
- 事实：期中三维 373/218/187 → Vo/Da/Vi **4.09 / 2.20 / 2.60×**（Vi 187 < 审查基准 192 →
  罚 103‰，`common=897` 把三项一起压低＝联动惩罚）；期末 842/350/629 →
  **6.97 / 2.85 / 4.96×**（Vo/Da 两项不达标）。
- 跳过的两场：2026-11-21 的 `i_card-hkne-3-000` 不在主数据快照里（新卡），夹具显式记录
  `skipped` —— 生产侧不依赖主数据，直接读屏幕倍率（真机帧「舞蹈 207%」→ 搜索 2.07）。
- 注意：这是**主数据计算结果**的回归快照，不是官方逐分真值；真机逐分回放还差 P 道具附魔/
  考试内生成卡等未建模机制（见 RULES_REFERENCE §5.1 的「剩余差距」）。

## 非图片素材：人工标注回归夹具（WORKPLAN P1-6 / T7③）

`review_regressions.json` 不是截图，是**复盘页人工标注转成的回归用例**（schema
`gkagent-review-regressions/1`）：每条用例带 `kind`（replay=观测序列重放整态冻结 /
trace=逐步轨迹分类结论冻结）、`events`/`rows`、转换时冻结的 `expect`、`provenance`。
[`tests/test_review_regressions.py`](../test_review_regressions.py) 逐条重算比对——
以后重放语义/复盘口径变了（同观测不再同状态），这里立刻红。

- 来源：复盘页（`scripts/review_page.py` / auto_produce 局末 `[review]`）行内标注
  （verdict=bad + expected 修正值）→ 导出 `annotations_<ep>.json` →
  `scripts/annotations_to_regression.py` 转换合并（按 id 去重、幂等、原子写）。
- **当前 2 条都是 `provenance=synthetic-demo`**：演示闭环用的合成样例
  （ep-demo-review，记录/轨迹均合成），**不是真机 ground truth**。真机跑局标注后
  追加真实案例（provenance=human-annotation），测试自动逐条覆盖。
- 样例页：[docs/review_sample.html](../../docs/review_sample.html)（记录 = 真机 ep-rule1
  C+/5992；轨迹 = 合成演示 6 步，页面显著标注 synthetic-demo）。

## 缺的真机帧：回合结束确认框（F#8/F#36）

`step_NNN.png` 是**轮转覆盖**的，含「回合结束 / 尚可使用技能卡 / 确定要结束回合吗？」的
旧局截图（ep-cplus11 / ep-finish3/4/5 / ep-exp4）已经被后续 ep-t3 跑局覆盖。
2026-11-22 A4 用 `scripts/scan_frames.py` 扫了 1352 张归档截图（data/auto step+fail 487、
data/manual/arun/bench/video/ssr 511、data 根目录 354）+ data/bench 26，**0 帧**命中该文案。
→ 该分支用「真机课程帧 OCR 行 + FAILURES #36 的真实弹窗文案」回放；下次真机跑局出现该弹窗时，
把帧存成 `turn_end_confirm_<episode>_stepNNN.png` 补进本目录（挑帧用
`python scripts/scan_frames.py data/auto --contains 尚可使用 回合结束`）。

## 怎么再挑帧

```powershell
# 批量扫（生产 read_fast→decide，输出 screen/action/点击坐标/OCR 文本）
python scripts/scan_frames.py data/auto --screen story,event-choice,result-tap,drink-keep
python scripts/scan_frames.py "data/auto/step_*.png" --json out/scan_frames.json

# 单帧细看（每行 OCR 框 + decide 结果）
python scripts/probe_frame_decide.py 49 --repeat 2
```

归档新 fixture：直接把真机帧拷进本目录，并更新上表（屏型 + episode/step + 时间 + 测什么）。
