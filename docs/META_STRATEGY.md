# 学マス 环境与训练数据（2026-11）

## 一、数据从哪来

### 1. 本地 Master 数据（最权威）

游戏本地化插件把 Master 数据库导出成了 JSON：

```
D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans\
```

`scripts/build_master_dataset.py` 会把它整理成：

| 文件 | 行数 | 内容 |
|---|---:|---|
| `data/master/produce_cards.json` | 1817 | 培育技能卡：id、名称、描述文本、效果标签 |
| `data/master/support_cards.json` | 202 | 支援卡：id、名称、效果文本 |
| `data/master/events.json` | 6894 | 培育事件：选项文本/效果 |
| `data/master/event_suggestions.json` | 3066 | 事件建议/奖励 |
| `data/master/items.json` | 1068 | 培育道具 |
| `data/master/drinks.json` | 29 | 饮料 |
| `data/master/skills.json` | 1508 | P 技能/触发 |
| `data/master/idol_cards.json` | 152 | 偶像卡 |

数据是**中文**（和当前游戏 UI 一致），可以直接用于卡牌识别、特征提取和事件决策。

### 2. 网上环境/攻略（策略先验）

- [game8 H.I.F 回忆编成](https://game8.jp/gakuen-idolmaster/784697)：センス/ロジック/アノマリー 三套回忆与核心卡
- [game8 SR 支援卡 Tier](https://game8.jp/gakuen-idolmaster/784687)：SR 支援强度、SP 课+饮料体系
- [game8 H.I.F 攻略](https://game8.jp/gakuen-idolmaster/783836)
- [GAMEX 2026 H.I.F 指南](https://gamexjp.com/games/%e5%ad%a6%e3%83%9e%e3%82%b9/2819/)
- [Gakumas Note 支援卡计算器](https://happymillefeuille.github.io/gakumas/)
- [NGA 培育思路](https://ngabbs.com/read.php?tid=42852272)（需登录）

## 二、当前环境要点（H.I.F, 2026-11）

### センス（感性）

- 核心循环：**存在感**、**シュプレヒコール** 做循环；**スポットライト** 过牌；终盘 **話題沸騰** 提参数后打火力牌。
- 道中必拿：**国民的アイドル**、**至高のエンタメ**。
- PLv 低：用 **飛躍**、**情熱ターン** 自定义代替。

### ロジック（理性）

- やる気 / 好印象 两条线；好印象叠层后靠高倍率卡收分。

### アノマリー（非凡）

- 全力 / 強気；靠状态层数和专属卡循环。

### 支援卡

- **SP 课 + 饮料**体系是当前主流；`ふわふわでワクワク`（SP 课无限拿饮料）被 game8 评为 SR 最强。
- 6 张支援 + 1 张租借；优先同属性、SP 课、饮料/事件加成。

## 三、这些数据怎么用于训练

1. **卡牌语义特征**：用 `produce_cards.json` 的 tags + text 生成特征（费用、伤害、护盾、抽牌、SP、状态层数），作为 BC/价值网输入。
2. **事件策略**：`events.json` + `event_suggestions.json` 提供选项和收益文本，先做规则/检索，再蒸馏。
3. **出牌先验**：用核心卡表（存在感/シュプレヒコール/スポットライト/話題沸騰/国民的アイドル/至高のエンタメ）初始化策略权重。
4. **回放训练**：`runtime/replay.py` 采集真实对局的 state-action-reward，做 BC；再用 `sim` 搜索生成 teacher 动作做蒸馏。
5. **环境更新**：游戏更新后重跑 `build_master_dataset.py`；网上 Tier 表每月复核一次。

## 四、命令

```powershell
cd D:\Games\gakumas-agent
uv run python scripts/build_master_dataset.py
uv run pytest tests/test_master.py -q
```

数据默认不提交 git（体积大、可本地重建），只提交生成脚本和本文档。
