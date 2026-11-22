# gkbench（hiro.matto.top/gkbench）数据与 F 阶段口径

> 2026-11-22 建立。用户已登录该站（可下载公开数据）；本文件记录**怎么批量下载、哪些数据要令牌、
> 已下载了什么、参考分是多少**，以及和 [WORKPLAN 阶段 F](WORKPLAN.md) / F0 的关系。
>
> 规则红线不变：**ranked 用保密种子（只托管跑、算法只看画面），不能带 seed/牌序**；
> 能下载的固定种子题/公开答案只能用于**本地分析、理论上限当分母**（官方也这么定：看种子的搜索
> 只作 denominator、不参与排名）。

## 1. 站点结构（本地克隆 `data/bench_repo`，MIT）

两种评测：

| | 固定种子题（fixed） | 保密种子（template·32 个/题） |
|---|---|---|
| 种子 | 题集自带；开发集公开可下（`public_seeds` 或令牌） | 服务器私有，永不下发 |
| 怎么跑 | 本地跑完上传（`mode=self`）或托管（`hosted`） | 只能托管（`gkbench eval`） |
| 怎么比 | 同题同种子逐局配对；有理论上限（oracle/privileged）当分母 | 同题同格子号配对，几何平均比值 |
| 公开什么 | 成绩、逐步记录、`exam_sha`、存档里的答 | 只公开成绩（逐步记录登录后可见；`exam_sha`/答不下发） |
| 排行 | 「固定种子」 | 「保密种子」（ranked 主榜） |

存档格式 `gkms.audition_save.v2`：一题 = `loadout`（编成；含 `seed` 就是固定种子题）+ `check`
（起点核对：回合/分数/体力/手牌/规则版本/引擎提交号）+ `meta` + `runs`（各算法答：`route`
动作串 `p<i>/d<i>/e/s<i,j>`、`score`、`step_ms`）。详见 `data/bench_repo/docs/format.md`。

## 2. 公开只读 API（不用登录就能拉）

| 接口 | 内容 | 令牌 |
|---|---|---|
| `GET /api/sets` | 题集列表（problems/runs/public_seeds/场景统计） | 不需要 |
| `GET /api/runs?set=<set>` | 某题集全部运行（algo/kind/mode/均分/规则版本/privileged） | 不需要 |
| `GET /api/runs/<run>` | 一次运行的逐局摘要：**含 `route` 出牌路线**、分数、回合属性 `types`、tags | 不需要 |
| `GET /api/runs/<run>/episodes/<id>/<seed_index>` | 逐局完整记录（`steps`：每步 obs/action/algo_meta） | **保密种子要登录（403）**；固定种子公开 |
| `GET /api/sets/<set>/problems` | 题模板列表（编成/场景/题族） | 不需要 |
| `GET /api/sets/<set>/saves?answers=1` | 题模板存档 NDJSON（每行一题 + 公开算法的答/路线） | 不需要 |
| `GET /api/sets/<set>/saves?fixed=1` | 追加固定种子题行 | **要令牌/公开种子**（否则静默跳过） |
| `GET /api/sets/<set>/seeds` | 开发集固定种子（`seed`+`split`+`fixed_id`+`check`） | **要令牌**（`public_seeds=false` 时 401） |
| `GET /api/leaderboard?set=<set>&kind=fixed\|template` | 榜单（含 `vs_oracle` 几何平均/胜率） | 不需要 |

令牌：网页「我的」页（`/gkbench/me`）生成**命令行令牌**，存 `~/.config/gkbench/token`
（Windows：`C:\Users\<user>\.config\gkbench\token`）或设 `GKBENCH_TOKEN`。

## 3. 批量下载工具

`scripts/bench_download.py`（stdlib，只读公开接口；可重复执行、已下跳过）：

```powershell
# 目标算法（默认四个）；hif 题集；逐局 steps 默认就下、saves/leaderboards 一起
.venv\Scripts\python.exe scripts\bench_download.py --sets hif
# 只要 run 索引（含 route）和榜单，不下逐局 steps / 存档
.venv\Scripts\python.exe scripts\bench_download.py --sets hif --no-episodes --no-saves
# 带令牌（网页「我的」→ 命令行令牌），补保密种子逐局记录
$env:GKBENCH_TOKEN = "..."; .venv\Scripts\python.exe scripts\bench_download.py --sets hif
```

输出（gitignore，不入库）`data/bench_local/gkbench_dl/`：

```
sets.json                     # /api/sets
<hif>/runs.json               # 全部 run 概要（190）
<hif>/runs/<run>.json         # 目标算法 run 的逐局索引（含 route/score/types，一个 run 一个文件）
<hif>/episodes/<run>/<id>_<i>.json   # 固定种子（公开）逐局完整 steps
<hif>/saves.jsonl             # 题模板存档 NDJSON（505 题，含公开答）
<hif>/leaderboard_fixed.json  # 固定种子榜（含 vs_oracle）
<hif>/leaderboard_template.json # 保密种子榜（ranked 主榜）
manifest.json                 # 请求数/字节数/需要登录的逐局清单（断点续传依据）
```

## 4. 2026-11-22 已下载（公开部分）

`hif` 题集（505 题 / 190 runs）：**176 次请求、39.4 MB**。

| 算法 | 精确匹配 runs | 备注 |
|---|---:|---|
| `external:uinet` | 37 | 36 template（480/800 局/run）+ 1 fixed（70 局，steps 已下） |
| `external:uihorizon` | 13 | 8 template（最多 960 局）+ 5 fixed（lockprobe/submission-check，steps 已下） |
| `external:official-ai` | 2 | 480 / 957 局 template |
| `external:best-known` | 28 | 全部 template（280~800 局/run） |
| `external:oracle` | 2 | 理论上限（固定种子 70 局 + template） |
| 变体（`--variants`） | 13 | UINet 2.1 native/hud/roster/uiobs、UIHorizon v2.0/v2.2 等 |

- 目标 run 索引里**带 route 的局合计 36,350**（含保密种子局；索引公开 route，逐步 obs 需登录）。
- 固定种子（公开）逐局 steps：**79 局**（uinet 70 + uihorizon lockprobe 9）。
- 题模板存档：505 题（公开答只有 `external:uinet` 5 题/160 行——保密种子答不进公开存档）。

## 5. 参考分（2026-11-22 抓取，hif）

**固定种子榜（fixed；70 题一套，oracle-30s 当分母）**

| 算法 | n | 均分 | vs oracle 几何 |
|---|---:|---:|---:|
| oracle-30s（理论上限） | 70 | 567,948 | 1.0000 |
| pimc-vote-16w-2s | 70 | 302,202 | 0.5101 |
| uinet | 70 | 290,128 | 0.4986 |
| greedy | 70 | 41,507 | 0.0596 |
| uihorizon（lockprobe/submission-check） | 1~4 | 22,753~6,460,361（单题探针，不可比） | — |

**保密种子榜（template = ranked 主榜；960 局/算法）**

| 算法 | 均分 | vs best-known 几何 |
|---|---:|---:|
| best-known（分母） | **1,452,088**（928 局那版 1,486,205） | 1.0000 |
| UIHorizon v2.1Preview-Kummer | **631,129** | 0.5113 |
| UIHorizon v2.0Preview-Freiheit | 636,109 | 0.5017 |
| UIHorizon v2.2Preview-Gratwanderung | 571,828 | 0.4604 |
| UINet v2.1-Kummertranen | **578,722** | 0.4551 |
| uinet（internal 旧版） | 469,890 | 0.3740 |
| official-ai（asahi老师策略） | **232,710** | 0.2131 |
| hiro-rules | 95,341 | 0.0786 |
| greedy | 87,571 | 0.0710 |

> 这些数字与 README/COMPARE 里引用的一致（README 的 631k/579k/233k 是 template 榜口径）。

## 6. 还缺（要令牌，F0 用）

1. **`/api/sets/hif/seeds`**：开发集固定种子 + `check`（回合/分数/体力/**手牌**/规则版本）——
   F0 用它**交叉验证我们的洗牌模型**（`seed`+牌组 → 开局手牌/回合属性 vs 官方引擎的 `check.hand`）。
2. **保密种子的逐局 `steps`**：uinet/uihorizon/official-ai/best-known 的 template runs 只有 route
   索引，逐步观测要登录；拿到后可做行为分析/教师数据（不用于 ranked 提交）。
3. **`saves?fixed=1` 的固定种子存档**（含 `check`），同样要种子权限。

拿到令牌后同一命令重跑即可断点补齐（`manifest.json` 里有 `need_login_episodes` 清单）。

## 7. 与 F 阶段的关系

- **F0（先做）**：官方种子/`check` → 洗牌模型交叉验证 + 考试起点/规则版本校准；
- **F1**：用同题同种子把我们的 `LessonSim` 判官和官方分对齐（口径校准，先分清裁判差异）；
- **F2**：public-safe 适配器（不看 seed）→ 托管提交 → 按 ranked 榜口径（vs best-known 几何平均）对比；
- **离线研究**：公开 route/步骤可当 UINet/UIHorizon/官方 AI 的行为参照（教师数据方向，注意不用于 ranked）。
