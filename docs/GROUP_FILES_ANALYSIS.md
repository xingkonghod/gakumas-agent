# 群文件分析：OCR 根因、魔改 MAA、手机实验版

> 2026-11-22 凌晨，用户提供群文件（论文/2B run/`GKMSMAA_20261120.zip`/`GKMS小白鼠实验版.apk.1`）。
> 本文件记录**已解包/已实测**的结论与下一步；所有原始文件只存本地存档，**不入仓库**（许可证原因，见 §5）。

---

## 0. 一句话结论

**我们的 OCR 有问题是真的**：我们用的是 RapidOCR 默认 **中文** 模型（`ch_PP-OCRv4`，字典无假名），
日文 UI 只剩汉字碎片（`飲物持` / `？` / `、。`）；换成魔改 MAA 包里自带的**日文 OCR 模型**
（det+rec+keys，keys 18,708 行含 86 平假名/94 片假名/15,565 汉字）后，同一张截图能完整读出日文。
管理员说"没问题"，是因为 MaaGakumasu 自带日文模型（他们 PC 端就是那套），也可能用 Localify 把客户端本地化成中文。

**这是一个可以一次性修好大量文本分支的问题**（剧情选项/事件/课程/领奖…），优先级应排在 #42/#43 之前。

> ✅ **2026-11-22 已修复（WORKPLAN A1）**：正式换上官方 PP-OCRv6 small 多语言模型（Apache-2.0），
> `scripts/download_ocr_models.py` 一键下载/校验 → `data/models/ocr_jp/`，`OcrEngine` 自动加载；
> 实测 `step_025.png` 完整读出日文（见 §2「已落地」）。本文件 §1 的实测证据保留作根因记录。

---

## 1. OCR 根因：实测证据

| 项目 | 我们的 OCR | 魔改 MAA 包（MaaGakumasu 系） |
|---|---|---|
| 检测模型 | `ch_PP-OCRv4_det_infer.onnx`（4.6 MB） | `resource/base/model/ocr/det.onnx`（9.7 MB） |
| 识别模型 | `ch_PP-OCRv4_rec_infer.onnx`（10.6 MB，**中文字典**） | `resource/base/model/ocr/rec.onnx`（21.1 MB） |
| 字典 | RapidOCR 内置中文字符集（**无假名**） | `resource/base/model/ocr/keys.txt`：**18,708 行**；平假名 86、片假名 94、汉字 15,565、字母 52 |
| 日文结果（同图 `step_025.png`） | `飲物持` / `？` / `、。` / `本日。`（只剩碎片） | `ヨーグルトパフェ`、`つくねハンバーグ`、`ドリンクバー`、`そこまで真剣だと慰労を超えますが……`、`倉本さんのお気に入りは……`（完整） |
| 常用 UI 文本 | 中文 UI（「审查基准」「期中截止」「剩余回合」）可读 | 同样可读（汉字集覆盖） |

**实测方法**（2026-11-22，本机）：

```python
# 用 RapidOCR 的 config_path 指向魔改 MAA 包的日文模型
cfg = yaml.safe_load(rapidocr_config)
cfg["Det"]["model_path"] = r"...\GKMSMAA\resource\base\model\ocr\det.onnx"
cfg["Rec"]["model_path"] = r"...\GKMSMAA\resource\base\model\ocr\rec.onnx"
cfg["Rec"]["rec_keys_path"] = r"...\GKMSMAA\resource\base\model\ocr\keys.txt"
engine = RapidOCR(config_path=cfg_path)
```

结论：**同一个引擎（RapidOCR）、同一张图，只换模型/字典，日文识别从"碎片"变成"完整句子"**。
所以不需要换整个识别框架，只需要让 OCR 模型可配置，并把日文模型作为默认。

---

## 2. 修复方案（下个会话 P0）—— ✅ 已落地（2026-11-22，WORKPLAN A1）

### 方案 A（推荐，合规）→ ✅ 已采用
- 模型：官方 **PP-OCRv6_small_det + PP-OCRv6_small_rec**（Apache-2.0；多语言：中/日/英 + 46 拉丁语系），
  从 PaddleX 官方 ONNX 包下载（URL + sha256 锁在 `scripts/download_ocr_models.py`）；
- 与现有 RapidOCR 兼容（`config_path` 指向同一套 `config.yaml`，Det/Rec 换模型 + Rec 换字典）；
- 优点：许可证干净（Apache-2.0），模型不进仓库（`data/models/*` gitignore），下载脚本可重复/可校验。

### 方案 B（本地自用，AGPL）→ 仅作本地对照，未入库
- 路径：`D:\GakumasAgentArchive\group_files\GKMSMAA\resource\base\model\ocr\{det,rec}.onnx + keys.txt`；
- 2026-11-22 实测：官方 v6 模型与 MAA 模型在 `step_025.png` 上输出逐行相同（MAA 包其实是不同
  sha 的同代 v6 转换版）；正式方案不影响 MAA 只读研究。

### 已落地（代码/配置/验证）
1. `src/gkagent/vision/ocr.py`：`OcrEngine(config_path=…)` + 环境变量 `GKAGENT_OCR_CONFIG` +
   本地 `configs/ocr_jp.yaml` 自动发现（优先级从高到低；都缺则内置中文模型）。
   配置/模型缺失**直接报错**（禁止静默回退中文模型）；两阶段引擎与单行 `_line_core` 共用模型配置。
2. `configs/ocr_jp.example.yaml`：完整 RapidOCR 配置（v6 det 预处理参数），Det/Rec/字典指向
   `data/models/ocr_jp/`（相对路径按 YAML 目录解析；也支持 `%VAR%`/`$VAR` 与绝对路径）。
3. `scripts/download_ocr_models.py`：下载 + sha256 校验 + 导出 18,708 字字典 + 生成
   `configs/ocr_jp.yaml`（`--check` 自检；离线机器可手动放 tar 后重跑）。
4. `scripts/ocr_probe.py`：单张截图 OCR 探针（`--roi/--config/--json`），验字/排查用。
5. 测试：`tests/test_ocr_config.py`（17 条配置接线单测）+ `tests/test_ocr_jp_model.py`
   （4 条真图回归：日文/对白/中文 UI/决策选选项不点快进；模型缺失自动 skip）。
6. **实测**（本机 2026-11-22，全屏 720x1280，≈1.0s）`data/auto/step_025.png`：
   `ヨーグルトパフェ / つくねハンバーグ / ドリンクバー / そこまで真剣だと慰労を超えますが…… /
   倉本さんのお気に入りは……`；中文 UI `外出/审查基准/快进` 同时可读；
   `ProduceDriver` 同帧判定 `event-choice/last-row` → 点 (360,935) 选项（旧中文模型只剩碎片，
   会去点「快进」）。
7. 真机日志新增 `[ocr] 模型 = …`（`auto_produce.py`），一局开头即可确认实际用的模型。

### 代码接入点（历史记录，已实现）
1. `src/gkagent/vision/ocr.py::OcrEngine.__init__`：新增 `config_path`（或读环境变量 `GKAGENT_OCR_CONFIG`）；
2. `configs/ocr_jp.example.yaml`：从 RapidOCR 包内 `config.yaml` 复制，把 Det/Rec 换成日文模型路径
   （**不要把 AGPL 模型文件打进仓库**）；
3. 保留现有的布局兜底（F#41 剧情选项识别）作为第二道保险。

### 预期收益（换模型后）
- 剧情选项/事件选项/课程卡名/领奖/结算文本的**文本规则恢复**：F#41 的布局兜底可以降级为兜底；
- 课程决策「表情的基础 (2.0)」这类卡名/分数读取更准 → 直接帮助修 **F#42（连打 buff 0 分 FAILED）**；
- 事件屏「快进/选项/费用」识别更稳，减少 F#43 类结果页空转。

---

## 3. 魔改 MAA 包（`GKMSMAA_20261120.zip`）结构

已解压到 `D:\GakumasAgentArchive\group_files\GKMSMAA\`（44 MB，99 个文件）。

### 3.1 定位
- **MaaGakumasu 的魔改分支**（上游 v1.5.3 / commit `b7c08c4`，AGPL-3.0；`docs/UPSTREAM.md` 逐文件列出对应关系）；
- 不是完整的 MAA 应用，而是 **station 的"执行层"**：station（外部程序，`battle_connect.py --web`，`127.0.0.1:8765`）
  提供计划（`/api/frame` 的 `advice` + `basis`），`gkmsmaa` 负责把计划映射到屏幕点击。

### 3.2 模块（`gkmsmaa/`）
| 文件 | 作用 |
|---|---|
| `launch.py` / `__main__.py` | 入口；子命令 `probe`（只读考试屏）、`follow`（跟随 station 计划）、`produce-follow`（培育决策）、`ranking`（H.I.F TOP100 录像/点击） |
| `follow.py`（37 KB） | station 计划 → 屏幕动作；dry 默认不点；`--auto` 逐步点击并等 station `basis/executed` 变化确认；处理 tap 丢失重试、饮料对话、picker 选牌、提权检查 |
| `produce_follow.py`（90 KB） | 培育：schedule/card_pick/story/shop/card_change/keep-drinks/retry 等屏的跟随与确认 |
| `player.py` / `screen.py` / `bridge.py` | MaaGakumasu `ProduceCardsAuto` 的重写（play/drink/skip/wait）+ 文本归一化 + 屏幕动作映射 |
| `ranking.py` | H.I.F TOP100 榜单抓取/跟随（截图/点击，dry 默认） |
| `winpriv.py` | `ShellExecuteEx(runas)` 提权与"游戏提权/本进程未提权"保护 |
| `models.py` / `models.json` | 从网站按 sha256 下载 onnx 模型；`resource/` 里是 MAA 卡牌检测+OCR 模型与 produce 图标模板 |

### 3.3 对我们的价值（**只学架构/参数，不拷代码**）
- "**station 出 plan → 执行层按屏点**" 与我们"策略层 → produce_ui 点击"同构，但他们的执行层有大量
  **tap 确认/重试/提权/多阶段 picker** 的工程细节（rev184~254 修的问题与我们 FAILURES #17/#27/#36/#37 高度重合）；
- `produce_follow.py` 的屏分类（schedule/card_pick/story/shop/card_change）可直接对照重写我们的 `produce_ui` 分支；
- 其 `probe`（只读识别考试屏、输出 JSONL+截图）与我们 `LessonReader` 思路一致，可对照校准。

---

## 4. 手机实验版 APK（`GKMS小白鼠实验版.apk.1`，1.18 GB）

外层是 **LSPatch 打包的 Gakumas Android APK**（`lspatch/config.json`: VERSION 487 / API 102 / LSPatch canary-3106），
内含：

| 组件 | 大小 | 判断 |
|---|---|---|
| `assets/lspatch/origin.apk` | 537.8 MB | 原始游戏 APK |
| `assets/lspatch/modules/io.github.chinosk.gakumas.localify.apk` | 81.2 MB | **Gakumas Localify**（本地化模块）：4,836 entries，含 `assets/gakumas-local/local-files/masterTrans/ProduceCard.json`（20.7 MB）、`ProduceExamEffect.json`（18.6 MB）等**master 中文翻译** |
| `assets/lspatch/modules/org.nyarot.gkms.phone.apk` | 24.1 MB | **gkms-phone 实验模块**：`libgkms-gadget.so`（24 MB）+ `gkms-gadget.config` / `gkms-gadget.connect.config` / `gkms-gadget.portal` / `.pem` / `identity.json` / `xposed_init` → 手机端 **gadget 桥**（连外部 portal/station，可能用于采集/遥测/远程执行） |
| `assets/Octo/*` | ~320 MB | 游戏资源缓存（数字命名 bundle） |
| `assets/bin/Data/Managed` 等 | — | Unity/IL2CPP 游戏本体（`libil2cpp.so` 255 MB、`global-metadata.dat` 37 MB） |

**推断**：这是他们的"**移动端实验客户端**"= 原版游戏 + Localify（中文化）+ gkms-phone gadget（与 station 通信/采集）。
与 PC 端"魔改 MAA 执行层 + station"是同一条研究线的移动版本。

**我们已解包的内容**：`D:\GakumasAgentArchive\group_files\GKMS实验版APK\`
（`AndroidManifest.xml`、`lspatch/config.json`、两个模块 APK；未解 origin/资源包以免占用空间）。
**未做**：模块 dex 反编译、gadget 协议逆向（无必要；且涉及许可证/安全风险，保持只读观察）。

---

## 5. 许可证与安全边界（写死）

| 物品 | 许可证 | 允许 | 禁止 |
|---|---|---|---|
| MaaGakumasu / GKMSMAA（含模型资源） | **AGPL-3.0** | 只读研究、本地加载模型（方案 B） | 拷贝代码/模型进本仓库或私有仓库；衍生分发 |
| Localify 模块 / gkms-phone 模块 | 未声明（社区模块） | 只读分析 | 拷贝/反编译分发 |
| 论文/精简版 docx / run12 PDF | 公开文档（群分享） | 引用公式/结论并标注作者与日期 | 整篇转载/商用 |
| `launch_gakumas.ps1` | 社区脚本（未声明） | 借鉴思路（pf_access_token 直启） | 直接拷入仓库 |

原文件位置：`D:\GakumasAgentArchive\group_files\`（本地存档；不随 git / Gitee 私有仓库同步）。

---

## 6. 下一步（建议顺序）

1. ~~**P0-1 OCR 换日文模型**（§2）：`GKAGENT_OCR_CONFIG` + `configs/ocr_jp.example.yaml`；先本地用 MAA 模型验证
   （零下载），再做 Apache-2.0 版（PaddleOCR japan）作为可入库的正式方案~~ → ✅ **2026-11-22 已完成**
   （官方 PP-OCRv6 Apache-2.0；见 §2「已落地」与 WORKPLAN A1）；
2. **P0-2 重跑真机**（离线阶段 A 收尾后）：OCR 修好后先跑一局到考试，验证 F#41/#42/#43 是否随文本识别恢复而消失；
   然后验 T3 `[exam-plan] locked_turn=2~3 / verified=N`；
3. **P1** 对照论文公式补 `RULES_REFERENCE`/模拟器（T5）；自写离线最优路线（Bellman/分支定界/GNRPA 思路）；
4. 手机实验版：仅在需要时再深挖 gadget 协议/用途（当前判断足够）。
