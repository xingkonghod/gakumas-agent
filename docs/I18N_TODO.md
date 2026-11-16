# 汉化工作交接（已暂停）

> 状态：**已暂停**（用户决定先做别的）。本次**没有翻译任何条目**，没有 `translation_new.json`；
> 只做了扫描盘点、术语表、扫描脚本和本文档。恢复时从下面「恢复步骤」继续。

## 0. 一句话结论

官中补丁 v2.3.66 已覆盖绝大部分文本；真正缺中文的是**游戏更新后新增的 12 个技能卡变体（3 张卡）和 47 条 P 道具**。
其余表基本已汉化：`ProduceStory.json` 甚至只有标题/提示、没有对话正文；剧情对话在 `resource/adv_*.txt` 里，
补丁用 `<r=日文>中文</r>` 内嵌，97,764 条消息里只有 1 条拟声词没翻。

## 1. 数据源与基线（重要，别踩坑）

| 用途 | 路径 | 说明 |
|---|---|---|
| 现有中文卡表（基线） | `data/master/produce_cards.json` | **1817 行 / 476 id**，来自 chinosk6 补丁 v2.3.66（缓存在 `data/cache/masterTrans_new/`） |
| 游戏目录的旧补丁覆盖层 | `masterTrans/ProduceCard.json` | 只有 **1724 行 / 452 id**（2026-09-16 版），**不是**仓库基线 |
| 上游最新结构 | `data/cache/ProduceCard.yaml` | **1829 行 / 479 id**（vertesan/gakumasu-diff） |
| P 道具中文基线 | `data/master/items.json` / `masterTrans/ProduceItem.json` | 1068 条，全部已有中文 |
| P 道具上游结构 | `data/cache/ProduceItem.yaml` | 1115 条 |
| 游戏文本目录 | `D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans\` | 共 110 张表 |
| 剧情资源 | `D:\Games\Gakumas\gakumas\gakumas-local\local-files\resource\` | 3490 个 `adv_*.txt`，358.8 MB |

> ⚠️ **不要直接重跑 `scripts/build_master_dataset.py`**：它从游戏目录的 1724 行旧覆盖层导出，
> 会把仓库的 1817 行基线覆盖回 1724。补卡请基于 `data/master/produce_cards.json`。

## 2. 扫了哪些表、每张表缺多少

扫描脚本：`scripts/i18n_scan.py`（`--story` 会额外扫 358 MB 剧情资源）。全量结果在
`data/i18n/untranslated.json` 的 `summary` + `entries`。

### 2.1 P0：整条缺失（补丁里完全没有，需要新译）

| 表 | 本地基线 | 上游最新 | 缺口 | 说明 |
|---|---:|---:|---:|---|
| `ProduceCard` | 1817 行 | 1829 行 | **12 个变体 / 3 张卡** | 每张卡 4 个强化变体全缺 |
| `ProduceItem` | 1068 条 | 1115 条 | **47 条** | 补丁覆盖层里没有这些 id；本地已有的 1068 条中 0 条日文名/描述 |

技能卡缺口（`data/i18n/untranslated.json` 里 `priority=P0, table=ProduceCard`）：

| id | 卡名（日） | 稀有度 | 类型 | 4 变体费用 |
|---|---|---|---|---|
| `p_card-01-ido-1_138` | 一途な従者 | R | ActiveSkill | 5 / 2 / 2 / 2 |
| `p_card-01-ido-2_170` | 忠義を胸に | Sr | MentalSkill | 4 / 1 / 1 / 1 |
| `p_card-01-ido-3_292` | 柔らかな光の中で | Ssr | ActiveSkill | 5 / 4 / 4 / 2 |

P 道具缺口 47 条（N 12 / R 2 / SR 7 / SSR 26），按方案分组：

- **感性（Plan1）**：初星オブジェ（銀）×3、初星オブジェ（紫）、従者の必需品 ×2、ねぎらいコーヒー、
  王子様隠しかぼちゃ、お掃除の成果、お返しの髪飾り ×2、天性の才能 ×2、世界を魅了する姿 ×2、
  お誘いチケット、お嬢様おでかけセット、仲良しアルバム、なにかが変わる予感 ×2
- **理性（Plan2）**：初星ライト（オレンジ）×2、初星ライト（紫）×2、お手製ぴったり衣装、
  星々を統べる輝き ×2、規格外の魅力 ×2、花海ファームランタン、過激め？チョイス
- **非凡（Plan3）**：初星フラッグ（青）×2、初星フラッグ（紫）×2、限界への挑戦券、
  夢見る輝き ×2、ヒーローの輝き ×2、止まない嵐 ×2、小悪魔の色気 ×2
- **共通（Common）**：ゼミパーカー ×3

每条都带 `jp_name`、`jp_desc`（YAML 分段原文 ` / ` 拼接）、`rarity`、`plan`。

### 2.2 其余 110 张表（逐字段查日文假名）

共扫描 **110 张表 / 51,406 行**。命中假名的只有 30 行，且绝大多数是「未定義のパターン」占位或混排：

| 表 | 命中行 | 命中字段 | 性质 / 处理建议 |
|---|---:|---:|---|
| `ProduceExamEffect.json` | 13 | 28 | `未定義のパターン(Type: …)` 效果模板占位（P2） |
| `ProduceExamTrigger.json` | 5 | 11 | 同上（P2） |
| `ProduceSkill.json` | 1 | 1 | 同上（P2） |
| `ProduceStepEventDetail.json` | 2 | 2 | 同上（P2） |
| `Story.json` | 5 | 5 | 活动 020 标题 `ライブツアーイベント特別編 GO MY WAY!! 第N话`，只差前半段（P2） |
| `Localization.json` | 2 | 2 | 分享文案里的日文 hashtag（P2，可不翻） |
| `CharacterDetail.json` | 1 | 1 | `凑 みや`（角色昵称，P2） |
| `SupportCard.json` | 1 | 1 | `不是‘ア’而是‘エ’！`（保留假名的梗，P2） |
| `Music.json` | 149 | — | 歌词/作曲者名，**不翻**（版权 + 非 UI） |
| `Rule.json` | 6 | — | 法务/特商法公示原文，**不翻** |

> 其余表（`events`、`drink`、`shop`、`Achievement`、`Mission`、`Tips` 等）**零命中**，说明现有补丁已覆盖。

### 2.3 剧情（重点纠正）

**`ProduceStory.json` 里没有对话正文**：只有 `id` / `title` / `produceEventHintProduceConditionDescriptions`
（3427 行），且 100% 中文。对话正文在 `local-files/resource/adv_*.txt`：

- 3,490 个文件 / 97,764 条 `[message]` / 159,163 个 `<r=日文>中文</r>` 段
- **整句未翻：0 条**（每条消息都带双语 ruby 标签）
- 只有 1 条拟声词 `～～～～～っ♪` 原文照留（`adv_cidol-hrnm-3-002_03.txt`，建议保持）
- 1,337 个段的「中文」与日文完全相同，但绝大多数是 `……——。`、`！？`、`～～♪` 这类标点/拟声，
  50 个段保留日文假名（如 `100プロ`、`ちゃん`、`てれぱしー（心灵感应）`），属于补丁既有风格，不算未翻

结论：**剧情批次目前没有需要补的正文**。若以后游戏新增剧情，需等新版 `resource/adv_*.txt` 落地后再扫；
翻译时只改 `<r=…>` 后面的可见中文，`{0}`、`\n`、`<nobr>`、`</r>`、`<r=…>` 必须逐字保留。

## 3. 未汉化清单文件

- **`data/i18n/untranslated.json`**：全量清单（JSON 对象，`summary` + `entries`）。
  - `entries` 共 **110 条**：12 卡 + 47 道具 + 51 条其余表字段命中；
  - 每条含 `table`、`priority`、`id`、`jp_name`、`en_name`、`category`，P0 卡/道具额外带
    `upgrade` / `rarity` / `plan` / `jp_desc`；
  - `en_name` **留空**：仓库里没有可信的英文名来源（gakumasu-diff 只有日文），不臆造；
  - 如果要恢复原任务里的「四字段数组」，直接取 `entries` 再挑字段即可（它是四字段的超集）。
- 汇总统计也在 `summary`：卡/道具缺口、各表命中数、剧情扫描、扫描范围。

## 4. 术语表

**`data/i18n/glossary.json`**（翻译时强制套用）：

- `terms`：33 个核心词（やる気→干劲、元気→元气、集中/好調/好印象/绝好调、温存/强気/全力/全力値、
  熱意/高揚、スコア→打分、ターン→回合、スキルカード→技能卡、レッスン→训练、オーディション→试镜…）
- `effect_types`：88 个 `ProduceExamEffectType_*` → 中文（直接取自 `masterTrans/ProduceDescriptionExamEffect.json`）
- `card_grow_effect_types`：38 个成长效果中文（取自本地化表）
- `plan_types`：4 个（共通 / 【感性专用】 / 【理性专用】 / 【非凡专用】）
- `characters`：24 个角色 id → 中文全名（有村麻央、藤田琴音、秦谷美铃、十王星南、仓本千奈…）
- `preserve_tokens`：`{0}`、`\n`、`<nobr>`、`<r=…>` 等必须原样保留的标记
- `notes`：`en_name` 留空原因；既有译名里的疑似笔误（如 `複製`、`全力值值增加`）暂按原样，改动需整表统一

核心词速查：

| 日 | 中 | 日 | 中 |
|---|---|---|---|
| やる気 | 干劲 | 元気 | 元气 |
| 集中 | 集中 | 好調 | 好调 |
| 好印象 | 好印象 | 絶好調 | 绝好调 |
| 温存 | 温存 | 強気 | 强气 |
| 全力 / 全力値 | 全力 / 全力值 | 熱意 | 热意 |
| スコア | 打分 | ターン | 回合 |
| スキルカード | 技能卡 | レッスン | 训练 |
| オーディション | 试镜 | プロデュース | 培育 |

## 5. 已写/待写的脚本

已写：

- `scripts/i18n_scan.py`：扫描并生成 `data/i18n/untranslated.json` + `glossary.json`。
  ```
  .venv\Scripts\python.exe scripts/i18n_scan.py          # 主表（快）
  .venv\Scripts\python.exe scripts/i18n_scan.py --story  # 含 358MB 剧情资源（约 40s）
  ```

待写（恢复后建议先写）：

- `scripts/i18n_apply.py`：消费 `data/i18n/translation_new.json`，把译文合并回 master。
  建议格式（对 lead 给的 `{table: {id: {field: 中文}}}` 的落地扩展）：
  ```json
  {
    "ProduceCard": {
      "p_card-01-ido-1_138@0": {"name": "一途的从者", "desc": "…", "confidence": "high"},
      "p_card-01-ido-1_138@1": {"name": "一途的从者+", "desc": "…"}
    },
    "ProduceItem": {
      "pitem_01-1-100-0": {"name": "从者的必需品", "desc": "…"}
    }
  }
  ```
  - 卡牌用 `id@upgrade` 作 key（4 个变体的描述数值不同，不能只按 id 存一条）；
    道具按 id 即可。
  - 卡牌写回 `data/master/produce_cards.json`：追加 12 行
    `{id, name, upgrade, text, tags}`，tags 从 YAML 的 `produceDescriptions` 聚合（可参照
    `scripts/build_master_dataset.py` 的 `tags()`）。
  - 道具写回：`data/master/items.json` 追加 47 条（该文件在 `.gitignore`，属于本地产物）；
    另需让 `scripts/build_p_items.py` 支持 `--i18n <translation_new.json>`，
    否则它只读本地 1068 条覆盖层，新道具进不了 `data/knowledge/p_items.json`。
  - 合并后跑 `scripts/build_card_table.py`，应看到 `匹配到中文卡名: 1829 / 1829`。

## 6. 恢复步骤（按批次）

1. **P0-卡**：给 3 张卡的 12 个变体译 `name` + `desc`（参照同方案同效果的现有中文卡，数值/`<nobr>` 原样）；
2. **P0-道具**：47 条 `name` + `desc`（道具描述分段含效果标签，按 `data/master/items.json` 现有格式拼接）；
3. `i18n_apply.py` → `build_card_table.py` → 验证卡表 1817→1829；`pytest tests/ -q` + `ruff check src tests`；
4. 提交：`feat(i18n): P0 补全（技能卡+P道具 59 条）`；
5. P1 事件/支援卡：本地事件文本已翻译（仅 2 条占位），**先拉上游
   `ProduceStepEventDetail` / `SupportCard` 的 diff YAML** 才能判断新增条目（当前 `data/cache/` 里没有这两张表）；
6. P1 剧情：当前无需补；等新 `resource/adv_*.txt`；
7. P2：`未定義のパターン` 占位、`Story.json` 活动标题、`Localization` 分享文案；`Music`/`Rule` 不翻。

## 7. 纪律

- **不覆盖已有中文**：现有 1817 条卡名/描述、1068 条道具不得改动。
- 术语一致性优先于文采；低置信度保留原文并标 `"confidence": "low"`。
- 不碰 `src/gkagent/sim/`、`src/gkagent/policy/`（其他智能体在改）。

## 8. 本次提交内容

- `docs/I18N_TODO.md`（本文）
- `scripts/i18n_scan.py`
- `data/i18n/untranslated.json`（扫描产物）
- `data/i18n/glossary.json`（术语表）
