# tests/fixtures —— 真机截图回放素材（WORKPLAN A4）

这些 PNG 都是**真机截图**（720x1280），不是合成图；回放测试走生产链路
`ProduceDriver.read_fast`/`read` → `decide`（真 OCR 模型），见
[`tests/test_frames_replay_a4.py`](../test_frames_replay_a4.py)。
模型/配置缺失时测试自动 skip（干净 checkout 不会红）。

| 文件 | 屏幕类型 | 真机来源（episode / step / 时间） | 说明 |
|---|---|---|---|
| `story_choice_ep_t3_3_step049.png` | 日文剧情二选一（F#41） | ep-t3-3 step49，2026-11-22 02:14 | 培育开场剧情两气泡「飲み物を持ってきました / 慣れてきましたか?」+ 快进；旧中文 OCR 只读碎片→只点快进原地循环 |
| `lesson_ep_t3_4_step001.png` | 课程 buff 场景（F#42） | ep-t3-4 step1，2026-11-22 02:22 | 舞蹈课最后一回合 0 分：手牌 魅力的基础(29)/表情的基础(buff)/轻快步伐(23)；旧搜索连打 buff → 0 分 FAILED |
| `result_ep_t3_4_step004.png` | 结果页（F#43 同类屏） | ep-t3-4 step4，2026-11-22 02:22 | 课程结果页：三维属性条 + 「Da.上升了0!」浮字；日志写 `result-tap/gain` |
| `outing_choice_ep_full1_step049.png` | 外出事件（三选一） | ep-full1 step49，2026-11-19 18:41 | 「悠闲懒散 -8 / 彻底运动 / 去购物怎么样 -4」+ 快进；负 P 费不能被当 +N 飘字 |
| `exam_card_overlay_20261115.png` | 考试浮层（F#17/F#32） | 2026-11-15 17:17（考试实拍） | 考试页 1st..6th 排名条 + 卡片详情浮层「考试·舞台中仅限1次」+ SELECT + SKIP |
| `confirm_dialog_ep_t3_4_step019.png` | 确认弹窗（真机单帧） | ep-t3-4 step19，2026-11-22 02:23 | 「快进确认 / 未读的交流 / 是否快进? / 取消 / 确定」；和 F#8 回合结束确认框同 UI 组件 |
| `drink_limit_20261114.png` | 持有上限保留饮料（回放抓 bug） | 2026-11-14 01:03 | 「P饮料持有数量已达上限 / 请选择保留的3瓶饮料 / 还可选择2个」；暴露 `_checkbox_bands` 缺 `@staticmethod` 的 `TypeError` |
| `event_ep_t3_4_drink_choice.png` | 外出饮料选择事件屏（F#43） | ep-t3-4 step21，2026-11-22 02:23 | A3 归档：ヨーグルトパフェ -100P / つくねハンバーグ -50P / ドリンクバー 免费；P 费不是 +N 飘字 |

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
