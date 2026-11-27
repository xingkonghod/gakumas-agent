# 私有存档 / 私有仓库（2026-11-22）

> 目的：**完整 git 历史 + 采集原始数据 + 关键产物**的私有备份。官方一旦封堵，这些数据无法再采；
> 本仓库/本项目及全部存档**只能私有**，不公开、不 fork 到公开仓库、不在群里贴链接/截图。

## 1. 在哪

| 位置 | 内容 |
|---|---|
| `D:\GakumasAgentArchive\gakumas-agent.git` | **本地裸仓库**（private repo 形态，可直接 clone/push）|
| `D:\GakumasAgentArchive\gakumas-agent-YYYYMMDD.bundle` | **单文件完整历史**（可拷 U 盘/网盘；`git bundle verify` 校验）|
| `D:\GakumasAgentArchive\artifacts\` | 不入 git 的关键产物：`out/exam_setup.json`、`sim_engine_ab*.json`、`data/runs/*`、`data/bench_local/*`、`capture/traffic.jsonl` + `deck_snapshots.json` + `exam_truth.json` |
| `D:\GakumasAgentArchive\SHA256SUMS.txt` | bundle + artifacts 的 SHA-256 清单 |
| `%USERPROFILE%\Documents\gakumas-archive\` | **冗余副本**（防 D 盘挂掉：bundle + 清单 + README）|
| Gitee 私有仓库 | 已建（private=true），`master` + tags 已推；工作仓 remote 名 `gitee` |
| **GitHub 私有仓库（2026-11-28 新增）** | **已建（private=true）：`xingkonghod/gakumas-agent`**；工作仓 remote 名 `origin`（默认推送目标）；gh CLI 已登录（keyring），操作见 §4 |

## 2. 更新存档（可重跑，幂等）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\archive_private.ps1
# 加 -Push 同时推到私有远端（裸仓库 origin 已指向 Gitee 私有仓库）：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\archive_private.ps1 -Push
# GitHub 私有仓（工作仓 origin）单独推：
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

## 4. 推私有仓库（首次 / 换平台）

当前工作仓（`D:\Games\gakumas-agent`）已有两个私有远端：

```powershell
git remote -v
# origin  https://github.com/xingkonghod/gakumas-agent.git   (GitHub private, 默认)
# gitee   https://gitee.com/starry-sky-haven/gakumas-agent.git (Gitee private)
git push origin master --tags     # GitHub 私有
git push gitee  master --tags     # Gitee 私有
```

GitHub 首次/换机登录（**凭据走 gh keyring / Windows 凭据管理器，脚本不碰 token**）：

```powershell
winget install --id GitHub.cli -e
gh auth login --hostname github.com --git-protocol https --web --scopes repo
gh repo create gakumas-agent --private --source=. --remote=origin --push
```

存档脚本的 `-Push` 只推**裸仓库的 origin（当前=Gitee）**；GitHub 直接在工作仓 `git push origin`。

**安全红线**
- 仓库只能 **Private**；本文件/README 不含 token，也不要把 token 写进任何文档/命令历史；
- `data/hiro/`（AGPL 参考代码）、`data/master/`、`.venv`、`data/video/`、`data/GKMSUINet/` 大文件不入库（见 `.gitignore`）；
- 采集原始流量、牌堆快照只放本地 `artifacts/capture/`（不进 git/远端），必要时手动拷到加密盘；
- 不要在公开仓/群/issue 里贴：仓库链接、牌序数据、seed、截图、账号名。

## 5. 频率

- 重要节点（大功能提交、采集到新局、跑完整局）：`-Push` 一次；
- 平时每天一次不带 `-Push` 的本地存档即可（bundle 会覆盖当日文件）。
