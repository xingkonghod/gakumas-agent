# MITM / 采集 FAQ（常见问题）

> 面向群里/仓库访客的说明：**我们公开什么、不公开什么、工具从哪来、为什么榜单算法不需要 MITM**。
> 详细技术内容都在仓内文档里（见各节链接），本页只做口径。

## 1. 我们能分享什么 / 不分享什么

| 内容 | 状态 | 说明 |
|---|---|---|
| MITM **原理/链路/踩坑** | ✅ 公开 | [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)（结构/配置/四个坑）、[UNLOCK_REPORT.md](UNLOCK_REPORT.md)（端点/加密静态分析）、[UNLOCK_ADAPT.md](UNLOCK_ADAPT.md)（hook/版本适配） |
| 更新/协议断链**判据** | ✅ 公开 | [TROUBLESHOOTING.md §四](TROUBLESHOOTING.md)（游戏大版本更新后 13 条自检判据） |
| 采集**辅助脚本** | ✅ 公开 | `tools/yaha_hook_check.py`、`scripts/dig_traffic.py`、`scripts/swipe_capture.py`、`scripts/diag_capture_methods.py`、`scripts/check_run_capture_offline.py` |
| **工具本体**（GakumasUnlock / yaha_proxy / `mitm/*.py`） | ❌ 不在本仓 | 第三方社区工具，本仓**没有再分发权**；请从作者发布处/群文件获取 |
| **原始流量 / 账号会话**（`traffic.jsonl` 等） | ❌ 永不公开 | 含账号会话信息，只放本地私有存档 |

原因：MITM + 游戏客户端属于游戏 **ToS 灰区**，账号封禁风险自担；我们的红线是**不公开工具本体、不公开原始流量与账号会话**。

## 2. 采集链路一句话

游戏副本跑在本地（`C:\GakumasLocal`）→ 网络 hook 把请求导到本地服务 → 服务端透明转发到官服，
并把请求/响应解密落盘；再用纯函数重放/校验这套数据。结构、配置和四个坑见
[CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)；更新断链的排障判据见 [TROUBLESHOOTING.md §四](TROUBLESHOOTING.md)。

## 3. 「启动器整合包里有现成算法吗？」——**没有**

对 `GakumasUnlock-v3.5.0` 启动器包做过静态分析（[UNLOCK_REPORT.md](UNLOCK_REPORT.md)）：

- **不是完整私服**：`cache_server.py` 是 gRPC 响应**缓存/回放 + 解锁层**，没有业务状态机；
- 出牌侧只有 `follow` / `produce-follow`（**照 gkbench station 计划回放**）和 `produce_runtime.py`（Produce API 字段语义）；
- 没有搜索/决策算法（没有 expectimax / MCTS / seedlock 这类求解器）。

> 结论：想「装个包就有算法」不成立；要么用现成的 station 计划回放，要么自己写搜索。

## 4. 「跑榜单需要 MITM 吗？」——**不需要**

- **榜单算法是现成的、且只用公开观测**：`submissions/gkagent-ex-seed-v6/`（可直接托管复现，240 槽 1,461,263；
  seed 赛道第 2、hosted 第 1），入口 `algo.py:ExSeedV6Algo`，复现命令见 [submissions/README.md](../submissions/README.md)。
- 牌序 seed **不是**从流量里读的：从画面（回合属性、抽到的牌、公开编成）**自反推**（seed_scan 内核 + Draws 抽牌追踪
  + FastCut 快筛，通常 1–3 回合锁定），算法如实声明 `sees_seed=false` + `about.sees="seed"`。
- MITM 只用于我们**本地**的 seed/牌序研究、规则校准和真机 bot；与榜单成绩无依赖。

## 5. 工具从哪拿

## 5. 工具从哪拿 / 有没有开源仓

**工具本体（学马 GakumasUnlock 整合包）：没有公开仓。** 作者按「整合包」分发（群文件 / 网盘），包内文档明确写
「Gitee 尚无上传成功证据，GitHub 和网盘已取消」；我们拿到的是 v3.5.0 的本地副本（`C:\GakumasLocal`），
本仓不转发、不打包。安装方式、静态分析结论与适配记录见 [UNLOCK_REPORT.md](UNLOCK_REPORT.md) / [UNLOCK_ADAPT.md](UNLOCK_ADAPT.md)。

**同一条技术线（`yaha_proxy` hook + `mitm/`）相关的公开仓**（工程参考，均非学马解锁工具本体）：

- 作者 GitHub：<https://github.com/yuzeis>
- 学马相关：[GKMSMainWheel](https://github.com/yuzeis/GKMSMainWheel)（考试引擎 + 原生核心，AGPL）、
  [GKMSUINet](https://github.com/yuzeis/GKMSUINet)（出牌网络）、
  [gkmasToolkit](https://github.com/yuzeis/gkmasToolkit)（资源解包）
- 同作者的 MITM 框架（**其它游戏**，MITM 架构可对照）：
  [Roco-Kingdom-MITM-Server](https://github.com/yuzeis/Roco-Kingdom-MITM-Server)、
  [Roco-Kingdom-Protocol-Parser](https://github.com/yuzeis/Roco-Kingdom-Protocol-Parser)、
  [StarResonanceMITMServer](https://github.com/yuzeis/StarResonanceMITMServer)、
  [StarResonanceHeadlessMITMClient](https://github.com/yuzeis/StarResonanceHeadlessMITMClient)
- 评测框架：[gakumas-bench](https://github.com/matto49/gakumas-bench)（gkbench 的开源实现）
- 本地化插件（同一个 `yaha` hook 生态）：[gakuen-imas-localify](https://github.com/chinosk6/gakuen-imas-localify)

> 一句话：**学马这条线只有「引擎/出牌网/解包」是开源的，解锁+采集整合包本身不在 GitHub**；
> 想要 MITM 工程实现，看上面同作者的其它游戏 MITM 仓即可。

## 6. 风险提示（用之前先读）

- 涉及游戏 ToS 与账号封禁，**风险自担**；不要用主账号、不要多人共用同一份采集产物；
- 游戏大版本更新后先按 [TROUBLESHOOTING.md §四](TROUBLESHOOTING.md) 的判据自查（客户端版本、协议 hash、
  代理残留、DMM 更新还原 hook 等），再动手；
- 采集产物（流量/牌序/账号会话）**不要公开分发**。