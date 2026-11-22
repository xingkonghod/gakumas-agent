# 四游戏整合启动器 · 2026-11-22 包分析（作者：本地部署路线同一作者）

> **来源**：用户 2026-11-22 提供的 `偶像大师启动器.7z`（215,136,770 B，
> sha256 `28eb9f8b06a89756ffdf60e9b650b635fe307be8f1361cef709a23b15e39e3ab`，
> 与附件一致）。包内根目录 `THE IDOLM@STER/`，解包 **400.1 MB / 1458 个文件**。
>
> **和本仓库的关系**：和 [LOCAL_DEPLOY_VIDEO.md](LOCAL_DEPLOY_VIDEO.md) 视频里的
> `GakumasUnlock-v3.5.0` 是**同一条技术线**（同一个 `yaha_proxy` hook + `mitm/`
> `cache_server.py` + `unlock.py` 后端）；用户确认是当初「本地部署」作者发的。
> 我们的 `C:\GakumasLocal\GakumasUnlock` 是 2026-10-20 的旧分支，**本包更新更多**。
>
> **归档位置**：7z 已存 `data/dl/偶像大师启动器.7z`（`.gitignore`）；
> 解包目录 `D:\Games\_launcher_inspect\THE IDOLM@STER\`（仓库外，只做静态分析）。
> 包内 `交付文件清单.sha256.json` **1457/1457 条逐条校验通过**（解包多出的 1 个文件
> 就是清单本身）。全程只读，**没有运行 exe / 本地服务 / 游戏**。

## 0. 一句话

这不是单个「学マス」补丁，而是**四游戏整合启动器**（学园偶像大师 / 百万现场 /
灰姑娘女孩 / 闪耀色彩）的完整分享包：启动器本体 + 学园本地服务源码 + 四游戏适配 +
完整文档 + 哈希清单。**构建时间 2026-11-22**（启动器 exe 18:42、后端/数据 19:45），
但**包内文档最新只到 11-14**——11-22 新增的离线培育/可玩性/错误提示等没有对应
发布说明，只能从代码和文件时间看。

包内文档记录的**新版本修复**（11-14 及以前）与 11-22 的代码变化见 §2；对
我们项目的影响见 §3。

## 1. 包结构（1458 文件 / 400 MB）

| 路径 | 内容 |
|---|---|
| `学マス启动器.exe` | 4,687,360 B（11-22 18:42；OriginalFilename=`学マス启动器-两游戏-中文报错.exe`；**无版本资源**，ProductVersion=0.0.0.0；sha256 `3a1f5c61…`） |
| `src/ui/` | 启动器 C# 源码（**11-22 版**）：`Launcher.cs` 205 KB、**新增 `LauncherErrors.cs` 18.7 KB**、`MillionPage/ResourceService/Dialog.cs` 等；构建脚本 `build-integrated.ps1` |
| `source/four-game-launcher/` | 同一套源码的**11-14 旧副本**（`Launcher.cs` 204.5 KB，无 `LauncherErrors.cs`） |
| `mitm/` | 学园本地服务（Python）：`cache_server.py`（gRPC 缓存/回放，59.6 KB）、`unlock.py`（98.3 KB）、`http1_bridge.py`、**`produce_runtime.py`（新）**、`master_lifecycle.py`、`activity_cache.py`、`octo_catalog.py`、`offline_proxy.py`、`local_costume_master.py`、`masterTrans/`、`records/`、`cache/`、`offline-fallbacks/`、`certs/` |
| `hook/` | `yaha_proxy.dll`（自实现 v29：接管 Cysharp 45 个原生导出，HTTP/1.1 → `127.0.0.1:18444` 的 http1_bridge → cache_server）、`gkm_inject.exe`、原 DLL 备份、`src/yaha_proxy.c` |
| `tools/` | `local_content_sync.py`（从已下载缓存同步内容，新）、`local_playability.py`（离线 Live 可玩性补丁，新）、`download_master_tables.py`、`master_integrity.py` |
| `MLTD-adapter/` | 百万现场离线适配（Node，含 `src/`、runtime、资源目录） |
| `python/` | 嵌入式 Python 运行时（与我们的 GakumasUnlock 同 hash） |
| `docs/` | 历史交接/排障（3.5.3 适配与复盘、SCSP 后端接口、双 Logo 等） |
| 根文档 | `00-先读我-四游戏整合.md`、`00-启动更新修复-20261114.md`、`学-新电脑通信失败修复说明.md`、`交接文档-20261112.md`（421 行）、`使用说明.md`、**`错误提示与解决方法.txt`（11-22 新增）**、`MuMu使用与维护.md` 等 |
| `交付文件清单.sha256.json` | 1457 条 `{file,bytes,sha256}`（11-22 19:45） |

## 2. 新版本（11-22 构建）改了什么（证据）

### 2.1 启动器（11-22 18:42，相对 11-14 源码的 diff）

- **新增中文错误诊断系统 `LauncherErrors.cs`**：把日志/退出码正则匹配成「中文原因 +
  处理方法」。覆盖 update 1–5、launch 1–7、Windows 2/3/5/32/126/193/740、
  gRPC 1–16、HTTP 401/403/404/429/5xx、端口占用、证书、DMM 票据、磁盘/权限等
  30+ 条规则；每个任务输出统一为「正在启动游戏… / 启动游戏完成 / 失败（退出码 N）
  + 处理方法」。
- **「更多」菜单新增「错误提示与解决方法」**，根目录新增同名 txt（11-22 18:42）。
- **百万现场页新增「停止服务」按钮**：关闭所选 MLTD 游戏 + 托管本地服务，
  模拟器保持开启；操作失败统一走 `MillionResourceReply.ExplainFailure()`（附诊断）。
- 修复/健壮性（diff 可见）：
  - 停止/重启任务时 `stoppingAllServices` 也计入 busy，避免停止中又被点启动；
  - 子进程 `Exited` 事件与输出流结束的**竞态**（SpinWait 等两个 stdout/stderr 流关闭后
    再读退出码）；
  - `grab_master` 任务按 **UTF-8** 输出（其余保持 GBK 936）；
  - 异常文案统一进 `LauncherErrors.FailedToStart`，不再直接抛 `ex.Message`。
- 注意：`src/ui/build-integrated.ps1` 的 `$sourceFiles` **没有列出 `LauncherErrors.cs`**
  → 用包内脚本无法直接重建 11-22 的 exe（作者本机构建脚本没同步进包；只记录，不建议动）。

### 2.2 学园本地服务（11-22 17:36–19:45，新增/更新）

- **新 `mitm/produce_runtime.py` + `produce_catalog.json`（70 KB）**：
  **离线培育进度状态机（Selection Exam / `produce-007` 日程）**。
  - catalog：161 个偶像卡（含初始卡组）、18 个 lesson、20 个 event、470 张卡强化表、
    `refresh=500‰`、3 个 exam 日程类型（step type 16/17/18）；
  - 支持动作：lesson 1–9、event 11–12、shop/consult 13、休息 14；StepLessonStart/End、
    StepEvent、StepShopStart/Buy/End、StepRefresh、ReadAdv、Next；
  - **考试/课程算分仍在客户端**：服务端只发 `exam_seed`（lesson 随机种子）、接收客户端
    回传的 lesson 结果（score/threshold/limit/stamina/point），记成长
    `stat = 200 + (action_type-1)//3`、`growth = min(score, limit, 3000-stat)`；
    **代码里没有 Audition/Exam 结算逻辑**（grep `Audition`/`ExamBattle` = 0 命中）。
- **新 `mitm/activity_cache.py`**：按 event id 校验/回放活动记录（`grab_master.ps1` 调用）。
- **新 `mitm/octo_catalog.py`**：按已安装 catalog revision 返回 no-change Octo 目录
  （离线时避免客户端强制资源更新；`offline_proxy.py` 接入）。
- **新 `mitm/master_lifecycle.py`**：官方 master 发布事务 + 单份「客户端确认后回退」槽；
  版本哈希不透明、不按文件时间判新旧。
- **新 `mitm/local_costume_master.py` + `tools/local_playability.py`**：
  把新可玩偶像/服装补进离线 Live（UserData Character 追加、Costume 的 live feature/motif
  修正、`CostumeLive_Master_Get` 覆盖包）。
- **新 `tools/local_content_sync.py`**（28.5 KB）：从已下载缓存同步内容（不联网、不改系统
  代理、不启动游戏）；19 类表（IdolCard/IdolCardSkin/Costume/Music/SupportCard/Item/
  ProduceStory/ProduceCard/Produce/ProduceItem/ProduceDrink/ShopItem/Story…）。
- 更新：`cache_server.py`（+produce 路由）、`unlock.py`、`offline_proxy.py`、
  `grab_master.ps1`、`launch_game.ps1`（11-14）；`masterTrans/`、`records/`、
  `offline-fallbacks/`、`live-*.json`、`static_userget.bin`（2.0 MB 离线存档）刷新；
  清单 1457 条 19:45 重签。
- **离线回放数据**：`mitm/offline-fallbacks/` 共 33 个响应夹具（Auth/Home/Master/System/
  Shop/Produce_Top/Produce_ViewPictureBookLive/PvpRate/User_Get 等），11-22 更新的是
  **`CostumeLive_Master_Get.{bin,db,json}`**（配合 `local_playability.py` 的新 Live 覆盖包）、
  `Photo_ReportMission.bin`、`Master_Get.bin`、`Home_ListEvent.bin`；
  `mitm/records/` 另有 9 个基线 API 录制（11-22 新增 `public_Master_Get_active.json`）。
- **`mitm/masterTrans/*.json` 是 19 类表的「id 清单」**（只有 `id` 字段，11-22 刷新）：
  `ProduceItem.json` 1115 条、`ProduceCard.json` 479、`IdolCard.json` 163、`Costume.json`
  591、`Music.json` 477、`ProduceStory.json` 3604 等；供 `local_content_sync.py` 判定
  哪些记录要同步（不是翻译文本）。

### 2.3 包内文档写明的既有修复（11-07 → 11-14，新包里仍有效）

- **11-14 V3/V2（更新初始化）**：有真实登录票据即先更新（**取消「DMM 必须常驻」的保守
  限制**）；只认真实 onetime_token（**拒绝 32 个零的离线占位票据**）；HTTPS 转发在代理
  TLS 失败时**回退直连**（两条线路都校验证书，不重复提交 POST）；停止服务保持最高优先级。
- **11-14 代理恢复修订**：学官方/在线更新前清理本包残留代理（识别 localhost/IPv6/HTTP/
  HTTPS 分列写法）；后台监视器不再无条件写回旧设置（不覆盖用户 Clash 代理）；停止服务只
  匹配本目录服务与所选游戏；CA 检查核对**包内证书精确指纹和有效期**（不绕过 TLS）。
- **11-13**：移除 MLTD 汉化入口/服务端译文覆盖；修正资源快照指针（原指向未附带的
  1078750，实际只有 1078590 → 显式用包内完整快照）。
- **11-07（学）**：在线更新桥接**丢失客户端版本/平台/会话请求头与官服错误头**
  （`http1_bridge.py` 修复：保留应用层元数据、透传业务错误头、识别 x-error-code 2004）；
  MLTD 中文安装路径 Windows 进程信息编码；MLTD 高分辨率/未知截图兼容（保留原图、不自动
  点击未知画面）。
- **11-12 交接（421 行）**另记录：CGSS 缺 sqlite3、中文路径 adb、上游代理端口自适应、
  MLTD 停止/PNG 尾部字节/活动 end_date 等修复。

## 3. 与我们的关系（重要）

- **同源，但不能替换我们的采集安装。** 我们的 [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)
  用本机改造过的 `C:\GakumasLocal\GakumasUnlock`：h2c hook + `GKM_TRAFFIC=1` 写
  `out/traffic.jsonl` + 服务 18443/18444。检查对比：**本包 `cache_server.py` 没有
  `GKM_TRAFFIC`（0 命中）**，`hook/yaha_proxy.dll` 与本机也不是同一构建
  （hash 不同）——拿新包覆盖会毁掉采集链路。**保持仓库外只读参考**。
- 值得参考/核对的具体点：
  1. `produce_runtime.py` 给出 Produce API 的**字段语义**（schedule row tag 24/25/26/28、
     lesson 结果字段、成长公式 `min(score, limit, 3000-stat)`、shop 商品 kind
     1=卡/3=饮料/997=强化/998=删卡、饮料上限 3），可对照我们的采集解析与
     `sim/produce.py` 的成长/上限口径；
  2. `local_content_sync.py` 的 19 类表清单（对照 [MASTER_DATA.md](MASTER_DATA.md)）；
  3. `master_lifecycle.py` 的「版本哈希不透明 + 客户端确认后回滚」思路；
  4. **`mitm/masterTrans/ProduceItem.json` 的 1115 个 id** 正好对上我们
     [I18N_TODO.md](I18N_TODO.md) 的「上游最新结构 1115 / 本地 1068 / 缺 47 条」口径；
     而且 **B6/T5③ 里 gkbench 的 11 个「未知 P 道具 id」全部在这 47 条里**
     （`pitem_01-3-349-0`、`pitem_02-3-336-1`、`pitem_03-3-334/337/345-*`、
     `pitem_3-258-research-event-008/009/010` 等）——该清单**只有 id、没有效果/描述**，
     所以**不能直接**用包内数据补 `p_items.json`（不猜效果）；正路是更新 master 快照。
     **2026-11-22 B7 已按正路完成**：gakumasu-diff `data/cache/ProduceItem.yaml` 已是最新
     1115 件 → `scripts/build_p_items.py` 合并重建 `p_items.json`（1068→1115，结构来自 yaml、
     卡名用仓库自译表、中文描述缺失处日文+显式标记、条件未知段保守不触发），
     gkbench 未知 id 清零；本包只提供 id 清单，没有效果/中文可拷（见 RULES_REFERENCE §5.3 /
     HANDOVER 二·补二十九）。
  5. **离线培育（Selection Exam）是这个包的新能力**（包内文档还写着「培育已取消/不支持」
     ——文档滞后于代码）；我们项目的初 REGULAR 路线不受影响，但说明作者已把 H.I.F
     選抜日程的 Produce 状态机做成了本地可玩。
- **风险/边界**：作者文档明确「本机自测，未做游戏内验收/异机验收」，很多功能只是代码和
  自测；包内含作者离线存档（`static_userget.bin`）和少量本机状态
  （`appearance-mode.txt`/`selected-game.txt`/`probe.json` 等），不是接收者账号；
  包内**未声明仓库级许可证**（MLTD runtime-node 有独立 LICENSE）→ **不要把包内代码/数据
  拷进本仓库**，只记结论（本项目 PROVENANCE 边界）。
- **我们不需要做迁移**：当前采集/模拟/真机路线不依赖新包；如作者后续再发新版本，按本
  文档的方法（sha256 清单 + 源码 diff + 文件时间）做增量对比即可。

## 4. 归档与复现

```
7z        D:\Games\gakumas-agent\data\dl\偶像大师启动器.7z   （gitignore）
解包      D:\Games\_launcher_inspect\THE IDOLM@STER\          （仓库外）
校验      交付文件清单.sha256.json：1457/1457 通过；7z sha256 = 28eb9f8b…39e3ab
启动器    sha256 3a1f5c617cd7784ce194570ca739f343cc8a36a6edf9443ff2646272af5c5593
```

> 11-22 的「新版本更新 + 修 bug」如果作者有**文字发布说明**（聊天/公告），目前没在包
> 内；本文件列的是包内可验证的变化与 11-14 文档化的修复。若拿到原文，可再逐条对号。

## 5. 交接任务（用户 2026-11-22 要求「写进交接文档、开新对话做」）

- [HANDOVER_NEXT §4 T9](HANDOVER_NEXT.md) 已登记三选一候选：**B7**（P 道具 47 条补全，
  默认首选，纯离线）/ **C0**（采集/更新可靠性经验吸收，纯离线）/ **E0**（离线培育测试台
  实验，需要独立副本 + 用户配合）。
- [WORKPLAN.md](WORKPLAN.md) 增 B7 / C0 / E0 候选节；[HANDOVER.md](HANDOVER.md) 二·补二十八
  记录本包分析与边界；[INDEX.md](INDEX.md) 状态行同步。
- 规则：一次会话只做 1 个；B7/C0 不需要真机；E0 先问用户再动（不碰采集安装）。
- **进度**：B7 已完成（2026-11-22，HANDOVER 二·补二十九）；**C0 已完成**（2026-11-22，
  排障判据整理进 [TROUBLESHOOTING §四](TROUBLESHOOTING.md) + [CAPTURE_PIPELINE](CAPTURE_PIPELINE.md)
  「游戏客户端大版本更新后自检」，见 HANDOVER 二·补三十）；**剩 E0**（需独立副本 + 用户配合）。
