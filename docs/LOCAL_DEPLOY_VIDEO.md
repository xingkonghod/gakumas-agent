# 「学园偶像大师 · 本地化部署」视频解剖（BV1uHJB63EPW）

> **2026-11-22 更新**：用户拿到了作者新的**四游戏整合启动器包**（`偶像大师启动器.7z`，
> 215 MB，含 11-22 构建的启动器 + 学园本地服务源码 + 新离线培育等），已解包做静态分析：
> 见 **[LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)**。本文以下（2026-10-20）
> 记录的是当时 `GakumasUnlock-v3.5.0` 视频分析，**历史内容保留**。
>
> 来源：B 站 `BV1uHJB63EPW`「学园偶像大师科研成果：本地化部署」，UP 夏宇文括，5:35.9，2026-10-17。
> 简介：`https://wwbts.lanzoue.com/i1Ccp4cf5a6d` 密码 `9bse`。
> 本文全部结论来自**逐帧看画面**（视频无人声，见下）。证据帧在 `data/video/frames1080/`、裁剪图在 `data/video/crop_*.png`。

## 0. 一句话结论

视频里的「本地化部署」不是汉化补丁、也不是新客户端，而是 **本地私服 + 网络 hook**：

- 把 `GakumasUnlock\` 工具目录放进**官方 DMM 客户端**游戏根目录，运行 `安装.bat`；
- 安装程序替换游戏目录里的一个 DLL 做 **网络 hook**（原版备份为 `*.orig.dll`），并用自带的嵌入式 Python 起一个**本地服务，监听 `127.0.0.1:18443`**；
- 游戏仍由 **DMMGamePlayer** 启动，但所有请求被导到本地服务 → **离线运行 + 全内容解锁**（抽卡、卡牌、LIVE、摄影服装等）；
- 首次启动时用「参数抓取器」从 DMM 抓一次启动参数并保存，之后 `启动.bat` 可直接进游戏。

包体 15.9 MB：`GakumasUnlock-v3.5.0-CWDFIX-20261018-112215.zip`。安装时把 **1,363 个文件**复制进游戏目录（80% 时还剩 393 个 / 4.74 MB），主要是 Python 运行时、`mitm/`、`hook/`、`out/` 和服务端脚本。**不含 150 MB 级的 GameAssembly.dll**，所以不能靠它直接拿到解密后的 GameAssembly。

## 1. 视频音频/转写结论（别再看 transcript 了）

- 0:00–1:38.1 是**数字静音**：`silencedetect` 报 `silence_start: 0 / silence_end: 98.147`，20 s 窗口 RMS = **-120 dB、peak 0.00**。
- 1:38 之后才有声音：游戏 BGM + 角色语音（日文）。用 `language="zh"` 的 faster-whisper 强行转写，只会把日文语音幻听成中文，得到 399 字节的垃圾（例如「我能拍照吗?」「想再训练一点」），**不是 UP 的讲解**。
- 重跑一次 `scripts/transcribe.py --model small` 结果相同（`data/video/transcribe_rerun.log`）。逐帧画面才是唯一信息来源。

## 2. 时间线（画面证据）

| 时间 | 画面 | 关键信息 |
|---|---|---|
| 0:00–0:12 | DMM GAME PLAYER「マイゲーム」+ 资源管理器 | 游戏目录 `F:\Gakuen IDOLM@STER\gakumas`，10 个文件，**没有 version.dll** |
| 0:00–1:00 | 复制进度框 + `安装.bat` 控制台 | 「正在将 **1,363 个项目**从 `GakumasUnlock-1.1` 复制到 `gakumas`」，80% 时 393 项 / 4.74 MB，4.70 MB/s |
| 0:12–1:00 | `安装.bat` 5 步 | 见下方原文 |
| 1:00–1:40 | `启动.bat` 3 步 + 等待 | **本地服务 18443 监听**；首次「参数抓取器」；提示从 DMM 点「ダウンロード」 |
| 1:40–2:30 | DMM 下载 → 游戏启动 → 数据下载 58.39% | 官方客户端正常走数据下载 |
| 2:30–5:36 | 实机：抽卡、卡牌列表、LIVE、摄影模式 | 全内容解锁的展示，**没有考试/结算画面** |

### 2.1 安装控制台（原文抄录，`data/video/crop_h020_console.png` / `crop_h_015.png`）

```
======== 学园偶像大师 全解锁 · 一键安装 ========
[1/5] 正在自动查找游戏目录 ...
[1/5] 游戏目录: F:\Gakuen IDOLM@STER\gakumas
[2/5] 检查游戏进程 ...
      游戏正在运行，自动关闭 ... 继续
[3/5] 安装网络 hook ...
      已安装 (原版已备份为 .orig.dll)
[4/5] 检查 Python 环境 ...
      F:\Gakuen IDOLM@STER\gakumas\GakumasUnlock\python\python.exe
[5/5] 检查依赖库 ...
      完成

安装完成
游戏目录: F:\Gakuen IDOLM@STER\gakumas
下一步: 双击 "启动.bat"

说明:
- 包可以放在任何目录，不需要放进游戏目录
- 本系统不碰 version.dll (DMM 的 DRM 解密器)
- 汉化组件 (如果有) 可以继续用
- 卸载: 双击 "卸载.bat"
- 本包为离线包，不需要代理

请按任意键继续...
```

### 2.2 启动控制台（原文抄录，`crop_h030_console.png` / `crop_h040_console.png`）

```
======== 学园偶像大师 全解锁 · 启动 ========
已自动切换解锁版
  Python: F:\Gakuen IDOLM@STER\gakumas\GakumasUnlock\python\python.exe
[1/3] 清理旧服务 ...
      no running service
[2/3] 启动本地服务（后台）...
      服务已就绪（18443 监听中）
[3/3] 启动游戏 ...
==============================================
 本地服务已启动
==============================================
请从 DMMGamePlayer 启动游戏

首次使用：正在启动参数抓取器 ...
请从 DMMGamePlayer 启动游戏（点「ダウンロード」）
抓到参数后会自动保存，以后双击 启动.bat 就能直接进
等待中（最多 5 分钟）...
```

## 3. 部署包形态（画面可见）

```
<游戏根目录>\GakumasUnlock\
├─ hook\            # 网络 hook DLL / 注入组件
├─ mitm\            # 抓 DMM 启动参数用的 MITM（证书/代理配置）
├─ out\             # 运行输出/日志（很可能有服务端日志、存档、抓包）
├─ python\          # 嵌入式 Python（python.exe + 依赖）
├─ tools\
├─ game_path.txt    # 记录游戏目录
├─ README.md        # 6 KB
├─ 使用说明.txt      # 17 KB（最重要，包到手先看它）
├─ 安装.bat          # 一键安装（5 步）
├─ 启动.bat          # 起服务 + 起游戏（6 KB，里面有端口/命令行）
├─ 更新数据.bat      # 更新资源/数据
├─ 官方原版备份.bat  # 还原被 hook 的 DLL
└─ 卸载.bat
```

- 安装位置：**游戏根目录**（与 `gakumas.exe` 同级）；包本身可以放任意目录。
- 视频示例：`F:\Gakuen IDOLM@STER\gakumas`；我们本机对应 `D:\Games\Gakumas\gakumas`（但注意下面第 6 节）。
- 依赖：官方 DMM 客户端 + DMMGamePlayer；自带 Python，不需要系统 Python。
- 网络：**离线，不需要代理**；本地服务 `127.0.0.1:18443`。
- 兼容：不碰 `version.dll`，汉化组件可以继续用（对本机 `GakumasLocal` 的 `version.dll` 是利好）。
- Hook 方式：替换游戏目录内某个 DLL，原版备份成 `*.orig.dll`（视频没展示被替换的具体文件名，包到手看 `安装.bat` 即可确认；候选 `baselib.dll` / `UnityPlayer.dll`）。

## 4. 视频版本 vs 本机客户端版本

|  | 视频（2026-10-20） | 本机 DMM 客户端 |
|---|---|---|
| GameAssembly.dll | 154,336 KB | 164,327,424 B（≈156.7 MiB） |
| gakumas.exe | 627 KB | 641,160 B |
| version.dll | 无 | 5,995,520 B（GakumasLocal 汉化代理） |

两边不是同一版本；包名带 `v3.5.0`，**很可能只适配视频那时的 3.5.0**，装到本机新版本上可能 hook 偏移/协议对不上。这是后续最大风险点。

## 5. 能不能拿到「真实对局数据 / 算分逻辑」？

**能拿到数据，算分逻辑要看服务端实现：**

1. `mitm/` + 本地 18443 服务天然是**全量 API 中间人**。只要在本地服务下打一局考试，`out/` 日志（或抓包）里就能拿到**真实的考试请求/响应**（手牌、行动、分数等）——这对标定我们自己的模拟器是硬数据。
2. `out/` 很可能还有 SQLite/JSON 存档，能拿到玩家状态、卡牌、P 道具、课程/考试记录。
3. 算分公式的位置：
   - 如果这是**完整私服**（Python 重写服务端），考试结算若在服务端算 → **公式直接就在 Python 源码里**，这是最好的结果；
   - 如果私服只是「发 master data + 存档 + 放行」，分数由客户端算 → 服务端只能给我们**输入/输出样本**，公式仍在客户端 `GameAssembly.dll` 里（加密，需运行时解密后 dump）。
4. 包体只有 15.9 MB，**不含解密的 GameAssembly.dll**；`hook/` 里的 DLL 至多带 IL2CPP 方法偏移，不能替代解密后的代码。

## 6. 蓝奏云下载：已按指示停止，未拿到包

> **2026-11-22 更新**：作者后来发了新的**四游戏整合启动器包**（不是本节的 15.9 MB
> v3.5.0 zip；215 MB，含 11-22 构建的启动器/后端/文档），已解包分析 →
> [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)。本节保留 2026-10-20
> 当时的下载尝试记录。

已完成/确认的：

- 解析出真实文件名与大小：`GakumasUnlock-v3.5.0-CWDFIX-20261018-112215.zip`，页面标称 **15.9 M**，2026-10-18。
- 走通了：`wwbts.lanzoue.com/i1Ccp4cf5a6d` → 密码 `9bse` → `apifile.woozooo.com/ajaxfile.php?file=324920563`（`action=downprocess&sign=…&kd=1&p=9bse`）→ 返回 `dom=https://developer4.lanrar.com` + `url=?CG5…`。
- 卡在最后一步：`developer4.lanrar.com/file/?…` 先返回阿里云 `acw_sc__v2` JS 挑战（已用 Node 解出 cookie 并通过），随后是蓝奏的「系统发现您的网络异常，需要验证后下载文件」页；该页 `ajax.php` 需要 `file`+`el`+`sign` 三元组，实测：
  - `el=1` / `el=3` → `{"zt":0,"url":"验证码错误"}`
  - `el=2` → `{"zt":1,"url":"?SignError"}`

  即验证 token 与当前会话/出口 IP 不匹配，属于服务端风控，不是脚本参数问题。继续硬试只会触发更严的风控，故停止。
- 尝试过的入口：`ajaxfile.php`（现行）、`ajax.php`（下载页二次验证）、`acw_sc__v2`（已解）、`lanzou_final2.py`（保留，见 `data/dl/`）。**没有**反复刷下载链接。

> 建议：用户手动在浏览器打开链接下载（密码 `9bse`），把 zip 放到 `D:\Games\gakumas-agent\data\dl\`，我再解包分析。

## 7. 包到手后的检查清单（按优先级）

1. `使用说明.txt` / `README.md` / `安装.bat` / `启动.bat` —— 确认 hook 的 DLL 名、端口、是否需要 DMM 首次抓参。
2. `python\` 下是否有服务端 `.py` 源码（不是 pyc/exe）→ 直接读考试相关 endpoint。
3. `mitm\` 的证书/代理配置 → 判断抓参范围。
4. `out\` 里是否有日志/SQLite/JSON → 真实对局数据。
5. `hook\` DLL 导出表/字符串 → 找 IL2CPP 方法名与偏移（尤其 Exam/Score/Result）。
6. 版本核对：包是 3.5.0，本机客户端若已更新，先确认兼容性再装；**安装会改游戏目录**，必须用副本目录，不能动 `D:\Games\Gakumas\gakumas`。

## 8. 证据文件

- 关键帧：`data/video/frames1080/h_001…h_140.jpg`（1080p，0–140 s，1 fps）
- 裁剪：`data/video/crop_h015.png`、`crop_h020_console.png`、`crop_h020_notes.png`、`crop_h020_explorer.png`、`crop_h030_console.png`、`crop_h035.png`、`crop_h040_console.png`、`crop_h040_port.png`、`crop_h005_dl.png`
- 全片缩略图：`data/video/montage_0_140.png`、`montage_140_340.png`
- OCR 原始输出：`data/video/BV1uHJB63EPW.ocr.txt`（480p）
- 蓝奏：`data/dl/lanzou_ajax.json`、`data/dl/lanzou_ajax2.json`、`data/dl/lanzou_step_page.html`
