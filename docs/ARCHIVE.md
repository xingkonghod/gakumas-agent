# 存档 / 仓库（2026-11-22 建，2026-11-28 改为「代码公开 + 存档私有」双轨）

> **代码仓**：GitHub **公开**（对外/群分享），AGPL-3.0-or-later，见 [../LICENSE](../LICENSE)。
> **存档仓**：Gitee **私有**（完整历史 + tag 快照）＋ 本地裸仓库/bundle/artifacts（采集原始数据、令牌、牌序真值等
> 只在存档侧，**永不进公开仓**）。官方一旦封堵，采集数据无法再采 → 存档侧必须继续私有。

## 1. 在哪

| 位置 | 内容 |
|---|---|
| `D:\GakumasAgentArchive\gakumas-agent.git` | **本地裸仓库**（private repo 形态，可直接 clone/push）|
| `D:\GakumasAgentArchive\gakumas-agent-YYYYMMDD.bundle` | **单文件完整历史**（可拷 U 盘/网盘；`git bundle verify` 校验）|
| `D:\GakumasAgentArchive\artifacts\` | 不入 git 的关键产物：`out/exam_setup.json`、`sim_engine_ab*.json`、`data/runs/*`、`data/bench_local/*`、`capture/traffic.jsonl` + `deck_snapshots.json` + `exam_truth.json` |
| `D:\GakumasAgentArchive\SHA256SUMS.txt` | bundle + artifacts 的 SHA-256 清单 |
| `%USERPROFILE%\Documents\gakumas-archive\` | **冗余副本**（防 D 盘挂掉：bundle + 清单 + README）|
| Gitee 私有仓库（存档） | 已建（private=true），`master` + tags；工作仓 remote 名 `gitee`（**URL 不写进公开文档**，见本地存档 README.txt） |
| **GitHub 公有仓库（2026-11-28）** | **公开：`xingkonghod/gakumas-agent`**（对外/群分享，AGPL-3.0-or-later）；工作仓 remote 名 `origin`（默认推送目标）；gh CLI 已登录（keyring），操作见 §4 |

## 2. 更新存档（可重跑，幂等）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\archive_private.ps1
# 加 -Push 同时推到私有远端（裸仓库 origin 已指向 Gitee 私有存档）：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\archive_private.ps1 -Push
# GitHub 公开仓（工作仓 origin）单独推：
git push origin master --tags
```

脚本会：打 `archive-YYYY-MM-DD` tag → 更新裸仓库 → 生成/覆盖当日 bundle → 备份 artifacts/capture →
写 SHA256SUMS → 更新冗余副本 →（`-Push` 时）push `master` + tags。

## 3. 从存档恢复

```powershell
# 方式 A：单文件 bundle
git clone D:\GakumasAgentArchive\gakumas-agent-YYYYMMDD.bundle gakumas-agent-restored

# 方式 B：本地裸仓库
git clone D:\GakumasAgentArchive\gakumas-agent.git gakumas-agent-restored

# 方式 C：从远端私有仓库
git clone https://gitee.com/<you>/gakumas-agent.git gakumas-agent-restored

cd gakumas-agent-restored
python -m venv .venv; .venv\Scripts\pip install -e .
```

恢复后按 [HANDOVER_NEXT §2](HANDOVER_NEXT.md) 跑四条基线；`out/exam_setup.json` 可从
`artifacts/` 拷回，或跑 `scripts\build_exam_setup.py` 重建（依赖 `C:\GakumasLocal` 的采集文件）。

## 4. 推仓库（公开 GitHub / 私有 Gitee）

当前工作仓（`D:\Games\gakumas-agent`）两个远端：

```powershell
git remote -v
# origin  https://github.com/xingkonghod/gakumas-agent.git   (GitHub，公开，默认)
# gitee   <Gitee 私有存档 URL，不写进公开文档>                (Gitee，private 存档)
git push origin master --tags     # GitHub 公开（对外/群）
git push gitee  master --tags     # Gitee 私有存档
```

GitHub 首次/换机登录（**凭据走 gh keyring / Windows 凭据管理器，脚本不碰 token**）：

```powershell
winget install --id GitHub.cli -e
gh auth login --hostname github.com --git-protocol https --web --scopes repo
gh repo create gakumas-agent --source=. --remote=origin --push      # 公开
```

存档脚本的 `-Push` 只推**裸仓库的 origin（当前=Gitee）**；GitHub 直接在工作仓 `git push origin`。

**红线（公开仓）**
- 公开仓**只能**放：自写代码/文档/投稿快照 + 已脱敏的公开数据；**不放** token、gkbench 保密种子、采集原始流量、
  游戏客户端/引擎源码、账号信息（`.gitignore` + `submissions/README.md` 说明已覆盖）；
- 私有存档（Gitee/本地 artifacts）保持 private：采集数据、牌序真值、bundle、密钥；
- 群/issue 里可以贴公开仓链接，**不要贴** token、seed/保密牌序、账号名以外的私有存档链接。

## 5. 频率

- 公开仓：每个阶段（大功能/成绩更新）推一次 `origin`；
- 私有存档：重要节点 `-Push` 一次；平时每天一次不带 `-Push` 的本地存档（bundle 会覆盖当日文件）。
