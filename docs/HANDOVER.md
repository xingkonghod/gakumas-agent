# GDE × MaaGakumasu 交接文档

> 最后更新：2026-11-12 01:05（Asia/Shanghai）
> 仓库：`D:\Games\gakumas-agent`（branch `master`）
> 游戏：DMM 学园偶像大师（本地化中文），管理员进程

---

## 0. 一句话现状

**真机 produce 已经能自动跑起来**：从主页进入培育 → 走完「选择偶像/支援卡/回忆/开始确认」四步 → 语音/快进/演出设置弹窗 → 课程（出牌）→ 技能卡奖励 → 回到行动选择，循环推进。
当前正在真机跑第一个培育周目；**考试、结算、活动/打榜/课题尚未接入**。

最近两个关键修复（本轮）：
1. `find_game_hwnd` 会把标题含 `gakumas-agent` 的 daemon 控制台误认成游戏 → 截到 720x1396 黑图、点击打到控制台。
2. 自己算 `ClientToScreen` 的点击在本机 200% DPI 下**偏下**；改用 MAA 的 `Seize` 输入后坐标正确。

**输入方式结论（2026-11-12 实测 + 查 MaaFramework / MaaGakumasu 配置）**：

MaaFramework 的 Win32 输入方式对照（Python binding `MaaWin32InputMethodEnum` 文档）：

| 方式 | 后台 | 抢鼠标 | 结论 |
|---|---|---|---|
| Seize | 否 | 是 | 真实鼠标，必须前台；之前用它导致抢鼠标 |
| SendMessage / PostMessage | 是 | 否 | 本游戏不认（实测 diff≈0） |
| **SendMessageWithCursorPos** | 是 | **短暂** | 光标移到目标→发消息→还原；**原生 MaaGakumasu PC 实例就用它** |
| AnchoredTouch | 是 | 否 | 合成触摸 WM_POINTER，本游戏不认 |
| Interception | 否 | 驱动级 | 要装驱动，仍是真实输入 |

证据：`D:\Games\MaaGakumasu\config\instances\cfcfe1e4.json` 里
`Win32ControlMouseType = SendMessageWithCursorPos`、`Win32ControlKeyboardType = SendMessageWithCursorPos`。

所以 GDE 设备层默认已从 `Seize` 改为 `SendMessageWithCursorPos`：不抢前台、后台消息、光标点完即还原；同时保留 0.8s 用户空闲门限与 F12 急停。

---

## 1. 定位

- **MAA（MaaGakumasu）**：截屏/识别/点击、日常、商店、启动；其 `resource/base/pipeline/Produce.json` 是一套完整的日文 UI 培育流程（含 `GkAgentCoach` 自定义出牌决策），但难度节点按日文 `MASTER` 写死，中文界面下不能直接用。
- **GDE（本项目）**：MAA 的**决策层** + 中文界面导航；卡牌/道具/事件/考试/升级的决策 + 训练闭环。
- 原则：能用规则/搜索解决的，不调模型；能用小模型解决的，不调 LLM。

---

## 2. 已完成模块

| 模块 | 路径 | 说明 |
|---|---|---|
| 设备层 | `src/gkagent/device/win32.py` | MaaFramework Win32Controller；**点击统一走 MAA `Seize`**（真实鼠标，自动换算 DPI）；截屏 FramePool 且校验尺寸/黑帧重试；`find_game_hwnd` 只认 `UnityWndClass`、优先非最小化窗口 |
| 感知-模板 | `src/gkagent/vision/matcher.py` | OpenCV `TM_CCOEFF_NORMED` |
| 感知-OCR | `src/gkagent/vision/ocr.py` | RapidOCR；2x 放大、置信度过滤（0.4）、去重、坐标还原 |
| 感知-界面 | `src/gkagent/vision/recognize.py` | 关键词规则 → 屏幕类型 + 置信度 |
| 感知-手牌 | `src/gkagent/vision/cards.py` | 卡框/费用/AP/推荐位识别（本机卡面留白时费用偶有误读） |
| 卡库 | `src/gkagent/data/cards_db.py` + `data/card_library.json` | 1724 张培育卡，效果文本 → 价值分 |
| 道具库 | `src/gkagent/data/items_db.py` + `data/item_library.json` | 697 个道具/饮料，同样打分 |
| Tier | `src/gkagent/data/tier.py` | game8 H.I.F（2026-11）SS 档；升级优先级排序 |
| 导航 | `src/gkagent/nav.py` | OCR 找文字 → 点击 → 回主页；`click_verified` 点击后校验+偏移重试 |
| **培育 UI 驱动** | `src/gkagent/tasks/produce_ui.py` | **新增**：OCR 读屏关键词 → 每步只做一个动作（编成四步、弹窗、难度、行动选择、课程奖励、剧情跳过），带 16 个单测 |
| 产出任务 | `src/gkagent/tasks/produce.py` | 培育状态机（SSR/场景/支援/主界面/出牌/事件/考试/结算），15s 阶段兜底，回放记录 |
| 升级任务 | `src/gkagent/tasks/upgrade.py` | OCR 列表 → Tier 规划 → 强化/特训；遇「付费/购买」中止 |
| 其他任务 | `activity_fee/work/challenge/society/daily.py` | 日常任务骨架（真机未全部验证） |
| 策略 | `policy/search.py`、`policy/ocr_cards.py`、`policy/router.py` | 贪心搜索、OCR 读卡详情、规则路由 |
| 训练 | `runtime/replay.py`、`training/bc.py`、`scripts/train_bc.py` | replay → BC → ONNX（管线已验证，数据少） |
| **自动跑图** | `scripts/auto_produce.py` | **新增**：逐步截图 + OCR 决策 + 出牌策略，N 步后落 `data/auto_log.txt` |
| MAA 集成 | `integration/maa.py` + MaaGakumasu 内 CustomAction | 教练/插件模式已装 |

---

## 3. 关键运行方式

### 3.1 自动跑培育（当前主路径）

```powershell
# 经常驻 daemon（管理员权限，免 UAC）
python D:\Games\gakumas-agent\.venv\Scripts\python.exe scripts\agent_cmd.py shell `
  --command "D:\Games\MaaGakumasu\python\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 40" --timeout 900
```

- 每步：截屏 → RapidOCR → 规则决定点哪里 → **MAA Seize 点击**；课程内交给 `ProduceTask.decide_card`（SearchPolicy）。
- 产物：`data/auto/step_NNN.png`、`data/auto_log.txt`；脚本退出码 0 = 回主页或跑满步数。
- 连续 5 步「无可执行动作」会停，便于人看截图补规则。

### 3.2 常驻 agent

```powershell
schtasks /Run /TN GDEAgent                      # 启动（最高权限，不弹 UAC）
python ...\agent_cmd.py home                    # 回主页
python ...\agent_cmd.py produce                 # 旧 FSM（尚未接中文界面）
python ...\agent_cmd.py click --x 360 --y 1005  # 单点（Seize，真实鼠标）
python ...\agent_cmd.py shell --command "..."   # 管理员执行任意命令
python ...\agent_cmd.py quit
```

命令通道：`data/agent_cmd.json` → `data/agent_result.json`。
**改代码后必须**：`agent_cmd.py quit` → `schtasks /Run /TN GDEAgent`。

### 3.3 截图

```powershell
python scripts/agent_cmd.py shell --command "D:\Games\gakumas-agent\scripts\cap_game.cmd"
# 结果 data/new_account.png，正常 720x1280、mean > 100
```

---

## 4. 环境配置（已做）

| 项 | 值/命令 |
|---|---|
| Clash Verge TUN | `enable_tun_mode: true`；系统代理 127.0.0.1:7897 |
| UAC 免弹窗 | `ConsentPromptBehaviorAdmin=0`、`PromptOnSecureDesktop=0`（**需重启生效**） |
| DMM 自动管理员 | `HKCU\...\AppCompatFlags\Layers` → `D:\DMM\GamePlayer\DMMGamePlayer.exe = ~ RUNASADMIN` |
| 常驻任务 | `GDEAgent`（RunLevel Highest, Interactive）→ `python agent_daemon.py` |
| OCR | rapidocr 装在项目 venv（3.11）和 MaaGakumasu python（3.12） |
| 游戏窗口 | `UnityWndClass`，标题 `gakumas`；**本机 DPI 200%**，物理客户区 1080x1920，渲染 720x1280 |
| 点击 | 默认 `SendMessageWithCursorPos`（后台消息 + 光标短暂移到目标后还原），另有 0.8s 用户空闲门限与 F12 急停；`Seize` 仅作备用 |

---

## 5. 培育流程实测（中文本地化 UI）

1. 主页「プロデュース」→ 培育页（定期公演「初」）→ 「レギュラー」（约 359,900）
2. 1.选择偶像 → 下一步（约 398,1124）
3. 2.选择支援卡 → 自动（约 600,1041）→ 弹窗确定 → 下一步
4. 3.选择回忆 → 下一步 → 「可租借」弹窗下一步 → 「回忆编成确认」完成
5. 4.开始确认 → 开始培育（约 398,1124）
6. 首次进入弹窗：语音播放确认（选「不播放语音」）→ 交流快进设置 → 演出跳过设置
7. 剧情对话：SKIP/快进 → 「跳过/快进确认」→ 确定
8. 课程：剩余回合数 + 3 张手牌；点卡即出牌
9. 课程结算：能力值飘字 → 点击继续；技能卡奖励「请选择要领取的技能卡」→ 推荐卡 + 领取
10. 行动选择：「请选择行动」三训练（Vo 194,1012 / Da 360,1012 / Vi 525,1012，点两次确认）或「授课/活动奖励」二选一（授课 268,1010）
11. 活动奖励结算（P+N 飘字 / 角色立绘）→ 点击继续

---

## 6. 已知 Bug / 待验证

1. **考试（期中/最终）未接**：`审查基准` 与考试回合的界面还没实拍，驱动未覆盖。
2. 行动选择有多种变体（三训练 / 授课+活动奖励 / 外出等），目前只覆盖前两种。
3. 卡面留白时费用 OCR 会读错（30→31、9→0），SearchPolicy 仍能出牌但策略质量打折。
4. 支援卡页「自动」第一次点会弹「自动编成」确认，驱动靠通用弹窗规则兜住；个别弹窗文案不同会漏。
5. 回放只有寥寥几条，`auto_produce.py` 尚未写 ReplayDB。
6. 事件卡有多个选项时只点默认/推荐，没有做价值比较。
7. 旧 `ProduceTask.run/_play_main` 的模板与固定点按日文 UI 写，中文界面下多数不命中；主路径已改为 `produce_ui` 驱动。
8. 页面**最小化**后截屏会返回 720x1396 黑帧（窗口被 DMM/用户最小化），需 `force_show_game.ps1` 恢复。
9. **点空气**：OCR 只按关键词判屏，状态判错时会点在无按钮的位置并反复重试；还没有「点完校验屏幕是否变化」的机制。
10. 点击方式已从 `Seize` 改为 `SendMessageWithCursorPos`（对齐原生 MaaGakumasu 配置）；**尚未在游戏开启时实测**，需要真机验证一次（点 SKIP 看是否弹确认、光标是否还原）。

---

## 7. 下一步优先级

| 优先级 | 事项 |
|---|---|
| P0 | 跑完一个完整培育周目（含期中考试、结算），把考试/结算屏补进驱动 |
| P0 | 点击校验：点完立刻比对截屏，无变化就停止该动作并记录，杜绝「点空气」循环 |
| P0 | 事件卡多选项按卡库/道具库价值选择；课程奖励选最优卡 |
| P1 | `auto_produce.py` 接入 ReplayDB，积累出牌回放 |
| P1 | 支援卡/回忆选择按 Tier 与卡库打分，而不是直接「自动」 |
| P2 | supervisor 循环：最小化→恢复、daemon 掉线→重启、空闲→重跑 produce |
| P2 | 训练 BC → ONNX，替换/兜底 SearchPolicy |
| P3 | 活动/打榜/课题：按 MaaGakumasu 的 Challenge/Society/ActivityFees 管线补 GDE 决策 |

---

## 8. 安全与回退

- **付费钻**：升级任务遇「付费/钻石/购买」文本会中止；不要主动花
- **UAC 回退**：
  ```powershell
  reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v ConsentPromptBehaviorAdmin /t REG_DWORD /d 5 /f
  reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v PromptOnSecureDesktop /t REG_DWORD /d 1 /f
  reg delete "HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" /v "D:\DMM\GamePlayer\DMMGamePlayer.exe" /f
  ```
- **不要**对游戏窗口做最小化→恢复循环（会黑屏/卡渲染）；用 `force_show_game.ps1` 单次恢复
- 游戏重启后窗口句柄会变；`find_game_hwnd` 已改为严格类名匹配

---

## 9. 测试与提交

```powershell
cd D:\Games\gakumas-agent
.venv\Scripts\python.exe -m pytest -q --basetemp=data\pytest-tmp
.venv\Scripts\python.exe -m ruff check src tests
```

最近提交：

```text
ca1c2e3 feat(produce): OCR-driven UI driver + MAA Seize clicks; fix hwnd/capture
62d5f8d docs: handover for GDE x MaaGakumasu automation
e67749f fix(click): GetCurrentThreadId from kernel32
d5273b3 fix(click): attach input thread to bypass foreground lock
3049a25 fix(device): reject capture when game window is minimized
72c8880 revert(click): remove minimize/restore trick that broke game rendering
078a16c fix(click): force foreground via minimize/restore before physical click
```

---

## 10. 关键路径速查

```text
D:\Games\gakumas-agent\                 仓库
  src\gkagent\device\win32.py           设备层（Seize 点击/截屏校验/找窗口）
  src\gkagent\tasks\produce_ui.py       OCR 培育导航（新增）
  src\gkagent\tasks\produce.py          培育 FSM（出牌/事件/考试）
  scripts\auto_produce.py               自动跑培育（新增）
  scripts\agent_daemon.py              常驻 agent（计划任务）
  scripts\agent_cmd.py                 发命令（非管理员）
  data\auto\step_*.png                 自动跑图逐步截图
  data\auto_log.txt                    自动跑图日志
  data\replays\produce.sqlite3         回放库
  templates\                           GDE 识图模板
D:\Games\MaaGakumasu\                   MAA（资源/自定义动作）
  resource\base\pipeline\Produce.json   日文完整培育管线（参考）
  resource\zh_CN\                      中文本地化资源（不完整）
D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans   112 个本地化 JSON
```
