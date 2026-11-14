# GDE × MaaGakumasu 交接文档

> 最后更新：2026-11-14 21:40（Asia/Shanghai）
> 仓库：`D:\Games\gakumas-agent`（branch `master`）
> 游戏：DMM 学园偶像大师（本地化中文），管理员进程

---

## 0. 一句话现状（2026-11-15 02:00）

> **新增：无画面模拟器**（`src/gkagent/sim/`）——卡表 1724 张真值、课程/培育模拟、6 人考试排名、
> 参数搜索（随机 + 进化）、单局回放前端 `docs/sim_viewer.html`、敏感性分析。
> 模拟器 12 周总和 653 vs 真机 632（校准过），能比较策略；**真机验证 C+ 还没做**，操作手册见 `docs/LIVE_RUN.md`。

## 0.1 一句话现状（2026-11-14 21:40）

> **开机先读 §3.0 启动流程**：Clash **TUN 模式**必须开（只开系统代理不够，DMM 启动游戏会报 120000）；DMM 只开一个实例；游戏必须从 DMM 里点卡片启动；daemon 用计划任务 `GDEAgent`（管理员）。

- **初星课题：29 / 60**。当前 NEXT = 「在培育中挑战获得 C+ 以上的评价吧」（0/1），卡在这里。
- **培育能全自动跑完**（多局 done=true，含期中考试）；期中考试已能过（重开后 2 位 442Pt）。
- **期末试镜/最终评价还不够 C+**（历史最好 C，常见 4-6 位不合格）；根因：属性成长低（支援卡等级/训练选择），今天刚升级支援卡。
- **支援卡**：主卡 Lv40、第二张 Lv37、第三张 Lv29（每日兑换所买素材后升级；再升需要更多素材）。
- **商店**：`scripts/shop_daily.py` 每日兑换所全买（自动跳过付费），实测 11 件/天。
- **速度**：课程步约 3s（确认步免 OCR）；非课程步 5-7s（OCR 瓶颈）。
- **日志**：`data/metrics.jsonl`（每步）、`data/failures.jsonl`（FAILED/不合格/卡死，带截图）、`data/exam_results.jsonl`（考试名次）、`data/final_grades.jsonl`（评价/分数）、`data/auto/auto_log_<ep>.log`、`data/auto/step_NNN.png`、`data/auto/fail_*.png`。
- **当前游戏状态**：出现「正在下载数据」→ 下载完成后回主页，需要继续推课题。

### 2026-11-13/14 这一轮修的重要问题（都已提交）

1. **出牌估值**：`cards_db.score_text` 改为真实数值（打分+27=31、打分+15=19），属性匹配 +4.0 / 不匹配 -1.5。
2. **训练选择**：跟随游戏「推荐」气泡（理性方案=视觉）；之前默认练舞蹈导致属性歪。
3. **体力**：休息阈值 12→15，且当前帧没读到体力时用上一帧（避免 2/34 体力硬练 FAILED）。
4. **确认步免 OCR**：两段式出牌的第二次点击不再截图/OCR → 课程步 ~3s。
5. **考试重开**：只有「不合格」才点再挑战；通过（如 2 位）点「下一步」。两段确认框（消耗再挑战道具）点「确定」；每局最多重开 2 次。
6. **饮料持有上限**：勾选框行按 x 610-655 列扫描（文字行 y 差 20-50px）；第三瓶在列表下方时**滚动查找**（`drink_scroll`）。
7. **弹窗按钮精确匹配**：`确定继续吗?` 的问句里也含「确定」→ `find_button()` 只认完全相等的按钮行。
8. **True End 条件成就弹窗**：点底部 ✕；「获得P点数」结果弹窗等 3 次后点关闭。
9. **回忆再生成确认**：取消（省票据）；培育结束「回忆概览」点「下一步」。
10. **横屏截图**：窗口被拉宽后 `post_screencap` 返回 (720,1280) → `capture()` 自动转置回竖屏。
11. **支援卡导航**：主页横幅「去升级2张支援卡…」也含「支援卡」→ 精确行匹配；主页按钮坐标 (95,1188)。
12. **授课「再次挑战」确认**（消耗道具重上）→ 取消，继续培育。
13. **商店**：`scripts/shop_daily.py`（每日兑换所按需买，付费项一律取消）。

### 还没解决的（下一轮重点）

1. **期末试镜拿不到 C+**：属性成长低（本局第 6 周 Vo171/Da224/Vi288 vs 对手 2,519Pt）。支援卡刚升到 40/37/29，还没用新卡组完整验证一局。
2. **培育结束检测**：偶尔把下载/结算屏误判成 home 提前结束（记录 done=true）。
3. **结果屏变体多**：再挑战/下一步、再挑战/结束培育、再次挑战确认 已分别处理，仍可能有新布局。
4. **偶像特训自动化**：导航仍不稳（「没有到达偶像界面」）。
5. **无人值守长跑**：supervisor 批次恢复前先手动单局验证。

### 2026-11-14 晚：出牌大脑 v2（新增，待实机验证）

**问题定位**：老逻辑 `pick_hand_card` 按"卡面文本价值"选牌，把卡牌左上角菱形的
**分数预览**（例：84）当成了体力费用（`DEFAULT_COST_ROI` 读的就是左上角），
高分牌被判"付不起"直接跳过；同时完全不看 `剩余回合数 / 审查基准 / 当前分 / SKIP`，
体力在头两回合烧光，后面回合空转 → 课程 FAILED（`fail_cplus-v9_014.png`：体力 3/34、审查基准 250 只打了几十分）。

**新增模块**

| 文件 | 作用 |
|---|---|
| `data/knowledge/mechanics.md` + `buffs.json` | 机制/buff 知识库（好调/集中/干劲/好印象/元气…，含倍率与出牌顺序，来自学マスwiki） |
| `src/gkagent/data/buffs.py` | 知识库加载与文本命中、出牌顺序 |
| `src/gkagent/data/card_effects.py` | 卡面文本 → 结构化效果 → 机制加权估值 |
| `src/gkagent/data/card_costs.py` | 卡名→体力费用缓存（从出牌确认帧的「体力 X / -Y」学习） |
| `src/gkagent/vision/lesson.py` | 课程读屏：分数预览菱形 / 爱心体力 / 剩余回合 / 审查基准 / SKIP |
| `src/gkagent/policy/lesson.py` | 出牌策略：分数÷体力、每回合体力预算、buff 先铺、没牌就 SKIP |
| `src/gkagent/policy/lesson_pick.py` | 接进 `auto_produce` 的适配层（读不到手牌时回退老路径） |
| `src/gkagent/knowledge/wiki.py` + `scripts/wiki_ingest.py` | **Wiki 接入**：抓 学マスwiki（EUC-JP）→ 本地缓存 → buff 词典（日文名/说明/出处），合并进 `buffs.json` |

`OcrEngine.line()` 新增"只识别"快路径（实测 10-30ms/个），手牌小数字不再走 2-5s 整屏 OCR。

**Wiki 接入用法**（不需要 API key，直连 seesaawiki 实测 0.7s/页）：

```powershell
python scripts\wiki_ingest.py            # 命中 data/cache/wiki 缓存（TTL 24h）
python scripts\wiki_ingest.py --refresh  # 强制重抓
```

- 抓 3 页：`buffs`（効果一覧）、`mechanics`（レッスン・試験詳細）、`hajime`（定期公演『初』）；
- 产物：`data/knowledge/wiki/*.txt`（正文，gitignore）、`buffs.json` 合并（人工中文名和权重**不覆盖**）、`wiki_snapshot.json`；
- 合并规则：按**日文名**对齐；对上的只补 `jp_desc`/出处，新条目以 `cn: []` 追加（中文卡面文本匹配不到，不会影响出牌）。

**验证**：`tests/test_lesson.py` 14 条（含真机帧 `live_lesson.png` / `lesson_now.png`）；
全量 `pytest` 与 `ruff check src tests` 均通过。真机帧上策略选中「聊天时间 84 分 / 6 体力」——
老逻辑正是把这张判成 useless 的。

**待办**：实机跑一局验证；卡面爱心体力小字 OCR 仍不稳（靠确认帧学习缓存补）；考试「移动」阶段未接新策略。

### 2026-11-14 23:30 实机验证（ep-verify1）

| 项 | 实测 |
|---|---|
| 时长 | 机器人自己跑 173 步 / 25 分钟（7.5s/步）；被打断后手动收尾，共 31 分钟 / 192 步 |
| 最终结果 | **不合格（6th，~180Pt；3rd 203、1st 589）** |
| 时间构成 | 课程 115 步 × 7.52s = 14.4 分钟（47%）；其余 67 步约 6 分钟 |
| 课程动作 | play 33 / confirm 31 / **skip 38** |

结论：**出牌已经不是主要瓶颈**（中段从 5th 追到 3rd），差在培育期属性成长（对手 1st 589 vs 我们 180）。
速度瓶颈是课程步每次 6.5s 的整块 OCR（卡名），已改成"轮廓定框 + 单行识别"（实测 0.4-2.1s），
理论整局约 17-18 分钟；但还差一次"改完后完整干净跑一局"的计时。

这一轮顺带修掉两个会自己停机的流程 bug：
1. 「领取完成」弹窗被当成领奖界面 → 反复点领取 → `card-reward/claim` 连续 10 次自停（`551e5b0`）；
2. 培育结束的「活动奖励进度」页被当成结算页 → 点空白 → `result-tap/settle` 连续 10 次自停（`d6a33b6`）。

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
| 设备层 | `src/gkagent/device/win32.py` | MaaFramework Win32Controller；**点击默认 `SendMessageWithCursorPos`**（后台消息＋光标点完还原，实测光标精确归位、不抢前台）；截屏 FramePool，接受 1279/1280 高度并校验黑帧重试；`find_game_hwnd` 只认 `UnityWndClass`、优先非最小化窗口 |
| 感知-模板 | `src/gkagent/vision/matcher.py` | OpenCV `TM_CCOEFF_NORMED` |
| 感知-OCR | `src/gkagent/vision/ocr.py` | RapidOCR；2x 放大、置信度过滤（0.4）、去重、坐标还原 |
| 感知-界面 | `src/gkagent/vision/recognize.py` | 关键词规则 → 屏幕类型 + 置信度 |
| 感知-手牌 | `src/gkagent/vision/cards.py` | 卡框/费用/AP/推荐位识别（本机卡面留白时费用偶有误读） |
| 卡库 | `src/gkagent/data/cards_db.py` + `data/card_library.json` | 1724 张培育卡，效果文本 → 价值分 |
| 道具库 | `src/gkagent/data/items_db.py` + `data/item_library.json` | 697 个道具/饮料，同样打分 |
| Tier | `src/gkagent/data/tier.py` | game8 H.I.F（2026-11）SS 档；升级优先级排序 |
| 导航 | `src/gkagent/nav.py` | OCR 找文字 → 点击 → 回主页；`click_verified` 点击后校验+偏移重试 |
| **培育 UI 驱动** | `src/gkagent/tasks/produce_ui.py` | OCR 读屏关键词 → 每步只做一个动作（编成四步、弹窗、难度、行动选择、课程奖励、剧情跳过），带 19 个单测 |
| **指标** | `src/gkagent/runtime/metrics.py` | **新增**：每步 capture/ocr/decide 耗时 + 点击回执 changed、每局 EpisodeRecord，写 `data/metrics.jsonl` |
| **无人值守** | `scripts/supervisor.py` + `scripts/start_supervisor.cmd` | **新增**：循环跑 auto_produce、窗口最小化恢复、连续失败退避、`data/STOP`/F12 停止 |
| **点击验证** | `scripts/verify_click.py` | **新增**：点一下菜单，打印 diff / 光标是否还原 / 前台是否被抢（已实测 OK） |
| 产出任务 | `src/gkagent/tasks/produce.py` | 培育状态机（SSR/场景/支援/主界面/出牌/事件/考试/结算），15s 阶段兜底，回放记录 |
| 升级任务 | `src/gkagent/tasks/upgrade.py` | OCR 列表 → Tier 规划 → 强化/特训；遇「付费/购买」中止 |
| 其他任务 | `activity_fee/work/challenge/society/daily.py` | 日常任务骨架（真机未全部验证） |
| 策略 | `policy/search.py`、`policy/ocr_cards.py`、`policy/router.py` | 贪心搜索、OCR 读卡详情、规则路由 |
| 训练 | `runtime/replay.py`、`training/bc.py`、`scripts/train_bc.py` | replay → BC → ONNX（管线已验证，数据少） |
| **自动跑图** | `scripts/auto_produce.py` | **新增**：逐步截图 + OCR 决策 + 出牌策略，N 步后落 `data/auto_log.txt` |
| MAA 集成 | `integration/maa.py` + MaaGakumasu 内 CustomAction | 教练/插件模式已装 |

---

## 3. 关键运行方式

### 3.0 启动流程（每次开机照做，2026-11-12 实测）

**第 1 步：开 VPN —— 必须是 TUN 模式，不能只开系统代理**

- 原因：DMM 客户端的 **Node 侧请求**（登录取 token、启动游戏）**不走系统代理**；只开系统代理时这些请求直连被 RST，表现为 DMM 日志 `ERR_CONNECTION_CLOSED` / `websocket 1006`，点游戏弹 **错误码 120000**。
- 做法：Clash Verge 托盘图标右键 → **TUN 模式** 打开。
  等价手工方式：`%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\verge.yaml` 里 `enable_tun_mode: true`，然后重启 Clash Verge。
- 验证（三条都过才算）：
  1. `Get-NetAdapter` 里有 `Meta`（Meta Tunnel），Status = Up
  2. `Get-NetRoute -DestinationPrefix 0.0.0.0/0` 里有 `Meta`，metric 0
  3. `curl.exe -s --noproxy '*' https://api.ipify.org` 返回日本 IP（不是本地 IP）

**第 2 步：启动 DMM Game Player（管理员）**

- `D:\DMM\GamePlayer\DMMGamePlayer.exe`（已配 RUNASADMIN，双击即管理员）；或 `scripts\start_dmm.cmd`
- **只能开一个实例**。重复启动会弹 `Error / Another instance is already running`。
  已多开：`taskkill /F /IM DMMGamePlayer.exe /T`，等 3 秒，再开一个。

**第 3 步：从 DMM 里启动游戏**

- DMM 窗口 →「マイゲーム」→ 点「学園アイドルマスター」卡片；DMM 会自动最小化，游戏窗口 `UnityWndClass / gakumas` 出现。
- **不要直接运行 `D:\Games\Gakumas\gakumas\gakumas.exe`**：需要 DMM 每次生成的 `onetime_token`，直接启动会秒退（日志 `dll.log` 里能看到带 token 的 "Execute of:: gakumas"）。
- 脚本辅助：
  - `scripts\click_screen.py <物理x> <物理y>` —— 管理员、物理像素（= 逻辑像素 × 2）
  - `scripts\probe_cursor.py <物理x> <物理y>` —— 校准落点（截图里画红圈）
  - `scripts\bring_dmm_front.ps1` / `scripts\maximize_dmm.ps1`
  - `scripts\launch_gakumas.cmd` —— `dmmgameplayer://play/GCL/gakumas/cl/win`（DMM 已在跑时可能被单实例吞掉，仅作备用）

**第 4 步：确认游戏窗口状态**

```powershell
Get-Process gakumas | Select-Object Id,SessionId,MainWindowTitle
# UnityWndClass 'gakumas' 必须 visible=True、iconic=False；渲染 720x1280
```

- 最小化时截屏会拿到 720×1396 黑帧；恢复用 `scripts\force_show_game.ps1`（单次恢复，不要反复最小化/恢复）。

**常见错误对照**

| 现象 | 原因 | 处理 |
|---|---|---|
| 点游戏弹「错误码 120000」 | DMM 启动 API 直连被 RST（VPN 没走 TUN），或游戏需更新 | 先按第 1 步验证 TUN；仍失败在 DMM 里更新游戏 |
| DMM 日志 `ERR_CONNECTION_CLOSED` / `websocket 1006` | 同上，Node 请求没走代理 | 开 TUN |
| `Another instance is already running` | DMM 多开 | taskkill 全部后只开一个 |
| 截图 720×1396 黑图 | 窗口最小化 / 抓错窗口（daemon 控制台） | `force_show_game.ps1`；`find_game_hwnd` 只认 `UnityWndClass` |
| 游戏秒退无窗口 | 直接运行了 `gakumas.exe` | 必须从 DMM 启动 |

### 3.1 自动跑培育（当前主路径）

```powershell
# 单批：跑 N 步（管理员）
python D:\Games\gakumas-agent\.venv\Scripts\python.exe scripts\agent_cmd.py shell `
  --command "D:\Games\MaaGakumasu\python\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 200 ep-xxx" --timeout 1500

# 无人值守：经 daemon 后台拉起 supervisor（3 局 x 200 步）
python ...\scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\scripts\start_supervisor.cmd" --timeout 60
```

- 每步：截屏 → （课程帧用模板快速判定，跳过整屏 OCR）→ RapidOCR → 规则决定点哪里 → `SendMessageWithCursorPos` 点击；课程内交给 `ProduceTask.decide_card`（SearchPolicy）。
- 产物：`data/auto/step_NNN.png`、`data/auto_log.txt`、`data/metrics.jsonl`（每步耗时/回执）、`data/supervisor.log`、`data/replays/produce.sqlite3`（出牌回放）。
- 停止：**F12** 或创建 `data/STOP` 文件；连续 5 步「无可执行动作」也会停。
- 实测（2026-11-12）：单步平均 ~4.8s，其中整屏 OCR 2–5s 是主要耗时；课程帧走模板快路径后应显著下降。

### 3.2 常驻 agent

```powershell
schtasks /Run /TN GDEAgent                      # 启动（最高权限，不弹 UAC）
python ...\agent_cmd.py home                    # 回主页
python ...\agent_cmd.py produce                 # 旧 FSM（尚未接中文界面）
python ...\agent_cmd.py click --x 360 --y 1005  # 单点（默认后台消息点击，光标会还原）
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
| Clash Verge | **TUN 模式必须开启**（`enable_tun_mode: true`，默认路由走 `Meta`）；系统代理 127.0.0.1:7897 只覆盖 Chromium，DMM 的 Node 请求必须靠 TUN |
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
8. 课程：剩余回合数 + 手牌；**两段式出牌**——第一次点卡只是选中（手牌框不变），再点同一点才真正打出（`lesson_pending` 记录位置+手牌框）
9. 课程类型选择：「重点练习歌唱/舞蹈/视觉效果」+ 底部「快进」；按推荐（正则 `推荐(歌唱|舞蹈|视觉)`）点对应行，点两次确认
10. 课程结算：能力值飘字 → 点击继续；技能卡/饮料奖励「请选择要领取」→ 点卡身（推荐标签在卡缘，向上 60px）+ 领取
11. 行动选择：「请选择行动」三训练（Vo 194,1012 / Da 360,1012 / Vi 525,1012，点两次确认）/ 四训练（多一个「授课」，此时 `training_hits>=2` 优先，不能选授课）/「授课+活动奖励」二选一（授课 268,1010）/「外出+咨询」（咨询 450,1027）
12. 期中考试「移动」阶段：先点上方技能卡 (185,500)，再点「移动」(360,1166)，两段交替；之后进入考试战斗，走课程快路径出牌
13. 外出/事件三选一（戏剧/体育/露营…）：OCR 把「P」和「-100」拆成两行，按 y 配对费用与选项，选最低消耗项，再点同一点确认
14. P 饮料持有上限 → 点「保留」(360,1166)；咨询商店 → 点「结束」(640,1165)；P 点数兑换不买
15. 活动奖励结算（P+N 飘字 / 角色立绘）→ 点击继续

---

## 6. 体力 / 出牌策略（2026-11-12 实机 + master 数据）

**游戏逻辑**
- 体力上限 35；课程出牌按卡面费用扣体力，付不起的牌打不出
- 每周只能做一个行动：训练 / 授课 / 外出 / 活动奖励 / 休息 / 咨询（选项随体力和周数变化）
- **休息**：回复 24 体力，但"1 周过去"（实测弹窗原文）
- **外出**：消耗 P 点数回复体力（实测 +24），三选一（戏剧 P-100 / 体育 P-50 / 露营免费）
- 饮料：回复体力/加打分，数量有限；`pdrink` 数据在 `data/master/drinks.json`

**已实现的策略（`scripts/auto_produce.py` + `tasks/produce_ui.py`）**
1. 每步读左上角 `X/35`（`parse_stamina`）
2. 出牌过滤体力付不起的牌（`decide_card(stamina=…)`）
3. 行动页体力 <12 且有「休息」→ 休息（弹窗「休息确认」点「休息」）
4. 课程内体力 ≤8 且还有回合 → 用一次饮料（每节课一次）
5. 卡牌用 OCR 卡名/效果查 `CardLibrary` 打分；权重已改为打分优先
   （得分/打分 6.0、伤害 4.0、护盾 0.8、元气 0.6、体力 0.4）
6. 外出三选一按 P 消耗最低选；饮料持有上限弹窗先补勾再「保留」

**还差的**
- 用剩余周数 + 审查基准差距做「练/休息/外出」预算决策（现在是固定阈值）
- 饮料按效果挑（体力回复 vs 打分），现在用第一瓶
- 卡牌用 `ProduceExamEffectType_*` 标签精确分类（打分/元气/体力回复）

---

## 7. 已知 Bug / 待验证

1. **考试后续阶段未完全覆盖**：期中考试「移动」已接（选卡+移动+战斗），考试结算/最终考试还没实拍。
2. 行动选择变体多（三训练 / 四训练+授课 / 授课+活动奖励 / 外出+咨询 / 外出+授课+休息），已覆盖五种，新的变体仍可能出现。
3. 卡面留白时费用 OCR 会读错（30→31、9→0），策略质量打折。
4. ~~支援卡页「自动」无限循环~~ **已修**：`support_auto_done` 只点一次自动编成，之后直接「下一步」。
5. ~~回放未接~~ **已接**：`auto_produce.py` 每步写 `ReplayDB`（run_id=episode）。
6. ~~事件选项无比较~~ **已修**：外出/事件选择改成点「最下面高亮选项」（两种布局：戏剧/体育/露营 与长句选项都适用；P 费用的「-」OCR 常丢，不再按费用配对），两步确认（`event_pending_y`）。
7. 旧 `ProduceTask.run/_play_main` 的模板与固定点按日文 UI 写，中文界面下多数不命中；主路径已改为 `produce_ui` 驱动。
8. 页面**最小化**后截屏会返回 720x1396 黑帧（窗口被 DMM/用户最小化），需 `force_show_game.ps1` 恢复。
9. **点空气**：`metrics.jsonl` 的 `changed` 记录回执；同一 `(screen,action,text)` 连续 10 次会停（签名里数字已归一化，防止 P/体力/回合每步变化导致签名永不相同），`unknown/unknown-tap` 连续 8 次会停。
10. ~~点击方式未验证~~ **已验证**（2026-11-12 12:11）：点菜单 diff=54、光标 (435,171) 精确还原、前台未变。
11. **OCR 仍是主要耗时**：非课程帧 2–5s；已加 ROI、digest 缓存、短文本补顶部条 OCR。
12. 过渡动画期间 unknown-tap 可能空点：guard 已放宽到 8 步。
13. 出牌策略质量未量化：需要看最终名次（目标 ≥ 第 3，用户手打能第一）。
14. ~~支援卡/偶像训练空转~~ **已修**：支援卡「Lv强化」、偶像「特训」都有两层/三层确认；支援卡列表会随选中卡滚动，每次升级后要滑回顶部再点目标卡。
15. **开局必须先回主页**：上一轮若停在支援卡/偶像/强化页，直接跑会连续 unknown-tap 自停；`auto_produce` 启动时已加 `Navigator.ensure_home()`。
16. **每局日志**：`data/auto/auto_log_<ep>.log`（`auto_log.txt` 会被下一局覆盖）。
17. ~~提示条「获得P点数」按气泡等~~ **已修**（2026-11-14）：等 3 次仍出现 = 结果弹窗，点关闭；「True End 条件成就」弹窗点底部 ✕（360,1215）。
18. **弹窗按钮必须精确匹配**：`确定继续吗?` 这种问句里也含「确定」，包含匹配会点到问句文字上 → 卡死 12 次。`find_button()` 只认完全相等的按钮行。
19. **P饮料持有上限**：勾选框行位置比文字行低 20–50px，按文字 y 点永远点不中；改为扫描 x 610–655 的勾选框列找行（`_checkbox_bands`）。「获得的饮料」段是灰色不可选，只勾「手持的饮料」段。
20. **再挑战是两段确认**：`再挑战 / 结束培育` → 点再挑战后再弹 `消耗再挑战道具，重新挑战考试吗？ 确定/取消`。第二段必须点**确定**，否则在两段之间 ping-pong（每局最多重开 2 次）。
21. **横屏截图**：窗口被拉宽后 `post_screencap` 返回 (720,1280)，`capture()` 自动转置回竖屏。
22. **支援卡导航**：主页横幅「去升级2张支援卡…」也含「支援卡」，必须用精确行匹配；主页按钮坐标 (95,1188)。
23. **Recall 页面**：培育结束的「回忆概览」要点「下一步」；回忆再生成确认弹窗要点取消（省票据）。
24. **期末/期中结算**：识别到「最终试镜/合格条件/需要得分」进入连拍模式，评价/排名写 `data/final_grades.jsonl`、`data/exam_results.jsonl`（含 FAILED 截图 `fail_<ep>_<step>.png`）。
25. **出牌估值**：`cards_db.score_text` 已按真实数值（打分+27=31），属性匹配 +4.0 / 不匹配 -1.5；训练选择跟随「推荐」气泡（理性=视觉）。
26. **每步耗时**：确认步不 OCR + 课程只读手牌 ROI → 课程步约 3s（2026-11-14 实测 `cplus-v2/v5`）。

---

## 7. 下一步优先级

| 优先级 | 事项 |
|---|---|
| P0 | 跑完一个完整培育周目（含期中考试、结算），把考试/结算屏补进驱动 |
| P0 | 用 `metrics.jsonl` 的 `changed` 做「点了没反应就停手」，杜绝空转 |
| P0 | 降低每步耗时：非课程帧改 ROI OCR（底部按钮区 + 顶部状态区），目标 <2s/步 |
| P1 | 事件卡多选项按卡库/道具库价值选择；课程奖励选最优卡 |
| P1 | 支援卡/回忆选择按 Tier 与卡库打分，而不是直接「自动」 |
| P2 | 训练 BC → ONNX，替换/兜底 SearchPolicy（回放已开始积累） |
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
  docs\HANDOVER.md                      本文档（启动流程见 §3.0）
  src\gkagent\device\win32.py           设备层（SendMessageWithCursorPos 点击/截屏校验/找窗口）
  src\gkagent\tasks\produce_ui.py       OCR 培育导航
  src\gkagent\tasks\produce.py          培育 FSM（出牌/事件/考试）
  scripts\auto_produce.py               自动跑培育（F12 急停）
  scripts\agent_daemon.py              常驻 agent（计划任务）
  scripts\agent_cmd.py                 发命令（非管理员）
  scripts\start_dmm.cmd                 启动 DMM（管理员）
  scripts\launch_gakumas.cmd            dmmgameplayer:// 协议拉起游戏（备用）
  scripts\bring_dmm_front.ps1           DMM 窗口置前
  scripts\maximize_dmm.ps1              DMM 窗口最大化
  scripts\click_screen.py               物理屏幕坐标点击（管理员）
  scripts\probe_cursor.py               点击落点校准（截图红圈）
  scripts\force_show_game.ps1           恢复最小化的游戏窗口
  scripts\cap_game.cmd                  截游戏图 → data\new_account.png
  data\auto\step_*.png                 自动跑图逐步截图
  data\auto_log.txt                    自动跑图日志
  data\replays\produce.sqlite3         回放库
  templates\                           GDE 识图模板
D:\DMM\GamePlayer\DMMGamePlayer.exe     DMM 客户端（RUNASADMIN）
D:\Games\Gakumas\gakumas\               游戏本体（v3.5.3，11.5GB，version.dll=汉化代理）
D:\Games\MaaGakumasu\                   MAA（资源/自定义动作）
  resource\base\pipeline\Produce.json   日文完整培育管线（参考）
  resource\zh_CN\                      中文本地化资源（不完整）
D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans   112 个本地化 JSON
```

---

## 11. 一句话备忘

**开游戏顺序：TUN（不是系统代理）→ 只开一个 DMM → マイゲーム点游戏卡片 → 确认 `gakumas` 窗口 visible 且不最小化。**
点游戏弹 120000 时，99% 是 TUN 没生效（DMM 的 Node 请求直连被 RST），先按 §3.0 的三条验证。
