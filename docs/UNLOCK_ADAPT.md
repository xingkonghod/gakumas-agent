# GakumasUnlock v3.5.0 → 本机 v3.6.0 适配评估（只读静态分析）

> 包：`data/unlock/GakumasUnlock/`（`GakumasUnlock-v3.5.0-CWDFIX-20261018`）
> 本机：`D:\Games\Gakumas\gakumas`，客户端 **v3.6.0**（`stringliteral.json` 含 `"3.6.0"`；`GameAssembly.dll` 2026-11-13）
> 方法：PE 头 / 导出表 / 导入表 / strings / 包内源码阅读。**未安装、未启动游戏、未反汇编函数体**。
> 工具：`tools/yaha_hook_check.py`（本次新增，可复用于新包对比）

---

## 0. 结论先行

| 问题 | 结论 | 难度 |
|---|---|---|
| hook 怎么挂的 | **按导出名（P/Invoke 名）替换 DLL + 运行时 `LoadLibrary` 原版转发**，**不是** IAT patch，**不是** 固定 RVA 打补丁 | — |
| 版本升级会不会失效 | **hook 层几乎不会**：45 个导出名与 v3.6.0 现装 DLL **完全一致（45/45）** | **低** |
| `cache_server.py` 有没有版本校验 | **没有**。`version / 3.5 / 3.6 / app_ver / master_ver / rules_ver` 在所有 `.py` 中 0 命中 | — |
| 安装改了哪个文件 | `gakumas_Data\Plugins\x86_64\Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll`（备份 `.orig.dll`），**不碰 `version.dll`** | — |
| 真正要重做的是什么 | `cache/`、`offline-fallbacks/`、`masterTrans/`、`forge/SystemCheck.bin`、`static_userget.bin` 等**数据层** | **中-高** |
| 能不能用 `dump.cs` | **能，而且很关键**：101.6 万行 v3.6.0 元数据，含全部消息类、字段名、`XxxFieldNumber = N`，可自动重建 protobuf schema | — |

---

## 1. hook 机制判定：按导出名（by name），不是按 RVA

### 1.1 一句话机制

`yaha_proxy.dll` 是一个**同名导出表面的转发器（wrapper）**：

1. `安装.bat` 把游戏自带的 `Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll` 备份为 `....Native.orig.dll`，再把 `hook\yaha_proxy.dll` 复制成该文件名；
2. 游戏（C# `DllImport`）按**函数名**加载 `yaha_*` 的 45 个入口，于是调进我们的 proxy；
3. proxy 内部 `LoadLibraryW(<同目录>\Cysharp...Native.orig.dll)` + `GetProcAddress` 逐个转发（日志 `orig=%p` / `fallback orig=%p`；字符串里同时存在 `.orig.dll` 与 `%ls....real.dll` 两个候选名，安装脚本只创建 `.orig.dll`，因此运行时走 `.orig.dll`）；
4. 在 `yaha_request_set_uri` 里做字符串匹配：host 命中 `game-gakuen-idolmaster.jp` 且路径含 `/client.api.` → 改写成 `https://127.0.0.1:18443<path>`；
5. 在 `yaha_client_config_set_server_certificate_verification_handler` / `..._skip_certificate_verification` 里**强制放行证书**（`GkmAlwaysAccept`）。

### 1.2 证据（可复现）

**导出表**（`tools/yaha_hook_check.py` 输出）：

```
hook : yaha_proxy.dll             internal name=yaha_proxy_v9.dll  exports=45
stock: Cysharp...Native.dll       internal name=yaha_native.dll    exports=45
export names identical : True
missing in hook        : -
extra in hook          : -
```

45 个导出全是 `yaha_*` API（`yaha_init_runtime`、`yaha_build_client`、`yaha_request_set_uri`、`yaha_request_begin`、`yaha_request_write_body`、`yaha_request_response_get_*` …），与游戏 C# 侧 P/Invoke 一一对应。

**导入表**：

```
hook imports: [('KERNEL32.dll', 18), ('msvcrt.dll', 29)]
KERNEL32: GetModuleFileNameA GetModuleHandleA GetProcAddress LoadLibraryW VirtualProtect?
          VirtualQuery? GetLocalTime Sleep ...（其余为 CRT/线程初始化）
```

→ 只依赖 `LoadLibraryW + GetProcAddress` 做**按名转发**；没有任何 `CreateFile/ReadFile/WriteProcessMemory/内存扫描` 迹象。

> ⚠️ `VirtualProtect/VirtualQuery` 出现在导入表里，但对应字符串 `VirtualProtect failed with code 0x%x`、`Address %p has no image-section`、`Unknown pseudo relocation protocol version` 全部是 **MinGW-w64 的 pseudo-reloc 运行时**带来的（编译器 `GNU C23 16.2.0 -mtune=generic -march=x86-64 -g -O2`），不是 hook 逻辑。别被误导。

**关键 strings**（ASCII，在 wrapper 区间 `< 0x20000`）：

```
=== proxy v8 (permissive cert verifier) dir=%s
orig=%p
fallback orig=%p
MISSING %s
### REDIRECT -> %s
https://127.0.0.1:%d%s
https://127.0.0.1:%d/
game-gakuen-idolmaster.jp
/client.api.
### BEGIN #%ld / ### REQ_BODY #%ld len=%llu / HEX: %s / ### REQ_COMPLETE #%ld
### SET_CERT_VERIFY_HANDLER intercepted -> installing permissive verifier
### SKIP_CERT called arg=%ld -> forcing true
GkmAlwaysAccept
%syaha-proxy.log
Cysharp.Net.Http.YetAnotherHttpHandler.Native.orig.dll
%lsCysharp.Net.Http.YetAnotherHttpHandler.Native.real.dll
yaha_proxy.c
```

**端口**：`18443` 不以 ASCII 出现，而是作为立即数 `0x480B` 出现在 `.text` 偏移 `0x3d68`、`0x3e5c`（`https://127.0.0.1:%d%s` 的 `%d` 实参）。**端口编死在 DLL 里，改端口要改二进制。**

**为什么不是 RVA hook**：

- 没有 `version.dll` / `GameAssembly.dll` / `UnityPlayer.dll` / `Il2Cpp` / `Mono` / `Mingw` 之外的任何游戏模块名字符串；
- 没有任何特征码/字节序列（PB 风格）或 `MH_CreateHook` 类导入（对照：同目录的汉化 `gakumas-local` 才用 MinHook，日志里全是 `ADD_HOOK: Xxx at 00007FFD...`）；
- 本身就是一个**完整替换的 DLL**，加载即生效，不需要找游戏函数地址；
- `.pdata/.xdata` 只覆盖它自己的 45 个函数。

**文件形态备注**：`yaha_proxy.dll` 3,271,680 B，但真实节区只到 `~0x11400`（70 KB），其余 **3.2 MB 全是 0x00 填充**（不是内嵌原版 DLL；没有第二个 `MZ`）。所以"文件大小接近原 DLL"是填充造成的，**不能拿文件大小做版本判断**。

### 1.3 与 `gkm_inject.exe` 的关系

`hook/gkm_inject.exe`（108,365 B）是一个 **注入式启动器**：

```
imports: CreateProcessW, CreateRemoteThread, VirtualAllocEx, WriteProcessMemory,
         ResumeThread, TerminateProcess, GetFileAttributesW, GetFullPathNameW, LoadLibraryW …
strings: "[gkm_inject] exe  : %s" / "hook : %s" / "cwd  : %s"
         "created suspended, pid=%lu" / "LoadLibraryW returned 0x%lX" / "resumed, game is running"
         "[gkm_inject] hook not found: %s" / "gkm_inject.c"
```

流程 = 创建挂起进程 → 注入 `LoadLibraryW(hook)` → 恢复运行。**但 `安装.bat`/`启动.bat`/`launch_game.ps1`/`serve.bat` 全都没有调用它**（grep 0 命中）。本包里它是**未使用的备用路径**（可能是给"不想替换 DLL / 被文件锁 / 以后换 hook 形式"预留的）。不含 URL/端口，因此它只负责把 DLL 塞进进程，拦截逻辑仍由 DLL 决定。

> 因此：**当前生效路径 = DLL 替换**；`gkm_inject` 与"按 RVA"无关，不要把它当成 RVA hook 的证据。

---

## 2. 版本检查在哪里

### 2.1 服务端（本地假服务器）：**没有**

对 `mitm/cache_server.py`、`mitm/unlock.py` 全文件 grep：

```
version | 3.5 | 3.6 | app_ver | master_version | rules_version | _ver
→ 0 命中
```

`cache_server.py` 只做：路径 → FORGE → CACHE → UPSTREAM → 兜底。**不会拒绝任何客户端版本。**

### 2.2 客户端侧：有版本概念，但离线时不构成拦截

- `global-metadata.dat` 字符串表有 `"3.6.0"`、`"AppVersion"`、`"ForceAppVersion"`；
- `dump.cs` 里存在：
  - `AppVersionHeaderKey` / `GetAppVersion()`（gRPC/HTTP 头里带 AppVersion，发往服务端；**假服务端直接忽略**）；
  - `Campus.Common.Master.ForceAppVersionMaster` + `Campus.Common.Proto.Client.Master.ForceAppVersion`（master 表驱动的强制升级）；
  - `ConditionType.AppVersionGreaterThanOrEqual = 69` / `AppVersionLessThanOrEqual = 70`（活动/任务的版本条件）；
- `SystemCheckRequest`（dump.cs:460228）**只有 `IdToken` 一个字段**，没有版本号；
- `SystemCheckResponse` 是维护公告/URL，`forge/SystemCheck.bin` 是 v3.5.0 抓的固定包（1064 B，解密后 1017 B），不含 `"3.5.0"` 字样。

结论：**升级到 v3.6.0 不会被"版本校验"直接拒绝**；真正的问题是数据版本错位（见 §4）。

---

## 3. `安装.bat` 到底改了哪个文件（源码确认）

`安装.bat`（GBK 编码，`chcp 936`）第 3 步：

```bat
set "YAHADIR=%GAMEDIR%\gakumas_Data\Plugins\x86_64"
set "YAHADLL=%YAHADIR%\Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll"
set "YAHAORIG=%YAHADIR%\Cysharp.Net.Http.YetAnotherHttpHandler.Native.orig.dll"

if exist "%YAHAORIG%" (
  echo       已安装（原文件已备份为 .orig.dll）
) else (
  copy /Y "%YAHADLL%" "%YAHAORIG%"     :: 备份
)
copy /Y "%CD%\hook\yaha_proxy.dll" "%YAHADLL%"   :: 替换
```

- **没有** `version.dll`、**没有** `gakumas-local\`、**没有** roots.pem；
- 只写两个文件：`Cysharp...Native.dll`（替换）、`Cysharp...Native.orig.dll`（备份）；
- 另外在包目录写 `game_path.txt`（卸载时删）。

本机现状（安装前）：

```
version.dll                                        5,995,520 B  2026-09-17   ← DMM DRM，未被动
Cysharp...Native.dll                               3,149,824 B  2026-11-09   ← 原版，无 .orig.dll
```

→ 当前**未安装**（没有 `.orig.dll`）。

> README/使用说明里"改 version.dll""官方账号.bat 把 version.dll 改名"等描述是**旧版本文档残留**：`官方账号.bat` 现在做的事是 `copy .orig.dll → .dll`，与 version.dll 无关。

---

## 4. 适配到 v3.6.0：需要做什么

### 4.1 hook 层（工作量：**低**，基本零改动）

1. 直接沿用/替换 `hook\yaha_proxy.dll`；
2. 用 `tools/yaha_hook_check.py` 对比**新包 hook** 与**当前 v3.6.0 原版 DLL** 的导出名集合（本机已 45/45 一致）；
3. 若未来 Cysharp 升级、原版 DLL 新增导出 → proxy 会缺入口，首次调用抛 `EntryPointNotFoundException`。判定方法就是那个脚本的 `missing in hook` 列表，**不需要重新定位特征码/偏移**；
4. 端口 18443 编死在 DLL（`0x480B` 立即数），要换端口得改二进制或换新包。

**为什么这个 hook 天然版本无关**：它不读游戏内存、不算 RVA、不 patch 代码，只要求「游戏仍用同名 DLL + 同 45 个导出名 + 把 base URL 交给 `yaha_request_set_uri`」。

### 4.2 数据/协议层（工作量：**中-高**，真正的工作）

| 需要重做/更新 | 原因 | 怎么做 |
|---|---|---|
| `mitm/cache/`（288 条） | `GKM_MATCH=exact`，请求体含版本/会话变化 → 大量 miss → 走 `offline-fallbacks` 的**v3.5.0 旧响应** | 用在线 MITM 跑一轮（登录→首页→各页面），让 `cache_store` 自动重建 |
| `mitm/offline-fallbacks/`（27 个） | 同上（离线兜底） | 在线模式下把新响应另存为 fallback |
| `mitm/masterTrans/`（19 个，仅 ID 列表） | v3.6.0 新增卡/服装/曲目 → 解锁列表缺新内容 | 游戏目录里已有**全量 v3.6.0 解密 master**：`gakumas-local\local-files\masterTrans\`（112 files / 95.5 MB），直接重跑 `unlock.py` 的 `load_master` 生成精简版 |
| `mitm/static_userget.bin`（818,166 B） | 全解锁存档是 v3.5.0 快照；新版本 `UserGetResponse` 可能有新字段 | 在线抓一条真实 `User/Get` → `unlock.Unlocker.build_static(tpl)` 重生成 |
| `mitm/live-*.json` | 新卡/新服装 ID | 从 v3.6.0 master 重新导出 |
| `mitm/forge/SystemCheck.bin` | v3.5.0 公告数据；协议字段未变，一般不致命 | 可选：重新抓一条 v3.6.0 的 `System/Check` 响应替换 |
| protobuf schema | v3.6.0 新增字段/消息 | **`dump.cs` 直接生成**（见 §5） |
| `unlock.py` 里的字段号 | 少量硬编码 `F_*` 字段号 | 用 `dump.cs` 对照校验（大多稳定，新增字段不影响旧字段号） |

### 4.3 加密（**零工作量**）

`SECKEY = b"Kb31v85u"` 在 v3.6.0 metadata 里**仍存在**：

```
stringliteral.json: { "index": 14654, "value": "Kb31v85u" }
```

→ 解密/加密逻辑、`decrypt_body()` 无需改动。（注意 index 从包注释的 14296 变成 14654，说明"按 index 硬编码"不可靠，按值找即可。）

### 4.4 难度评级

| 目标 | 难度 | 说明 |
|---|---|---|
| 让 hook 加载、游戏能启动 | **低** | 复制 1 个 DLL；导出面已验证一致 |
| 恢复到 v3.5.0 那种"能看 MV/剧情/换装"的完整度 | **中** | 需要在线抓一轮重建 cache/master |
| 支持培育（本包本来就不支持） | **高** | 需要真服务端状态机，不是适配能解决的 |
| 采集考试数据 | **低-中** | 不依赖解锁功能，只需要 hook + 解密（在线转发） |

---

## 5. `dump.cs` 能怎么帮适配

`data/reverse/out/dump.cs`（75 MB / 1,016,639 行）头部说明：由**本机 v3.6.0** 的 `global-metadata.dat`（46,660,356 B，sha256 `856a60ff…`）生成，**无 RVA/无函数体**，但名字/签名/枚举全在。

可直接支撑的自动化：

1. **重建 `.proto`**：每个消息类都有
   ```csharp
   RankFieldNumber = 1;
   ScoreFieldNumber = 2;
   ...
   System.Int32 Rank { get; set; }
   ```
   解析 `type#…FieldNumber = N` + 属性类型 → 生成 `message` 定义和字段号；再配合 `unlock.fields()` 做通用解码，**不需要官方 .proto**。
2. **确认"数据在哪条消息"**：例如考试结算字段就是靠 dump.cs 定位到 `ProduceStepAuditionEndExamBattleRequest.result`（§3 已用）。
3. **新增/改名检测**：对比新包的 dump.cs（或 metadata）与当前，diff 类名/字段号，就知道 v3.5.0 的 `cache`/`unlock` 哪里需要跟着改。
4. **枚举值**：`ExamCommandType`、`ExamPhaseType`、`ExamReplayRouteType` 等枚举常量可直接从 dump.cs 取，用于把 `ExamActions` 解成人类可读操作。

局限：**没有函数体**（GameAssembly.dll 在磁盘上是 DMM 加密的：4 KiB `.text` stub + ~114 MB 加密块，dump 工具也拿不到 RVAs）。所以 dump.cs **不能**回答"某行算法怎么写"，只能回答"数据长什么样、叫什么名字"。算分公式仍要靠 `docs/RULES_FROM_BINARY.md` 那条运行时 dump/对拍路线。

---

## 6. 拿到 10/20 新包后怎么比（清单）

1. **hook**
   ```powershell
   python tools\yaha_hook_check.py --hook <新包>\hook\yaha_proxy.dll
   ```
   看 `export names identical`、`missing in hook`、`internal name`、`immediate 18443` 是否还在；
2. **哈希/版本**：新包 `hook\yaha_proxy.dll` 的 sha256 与本包 `866f913a047d712b…` 比较；变了就看 strings 里的 `=== proxy v8/v9` 标记；
3. **安装脚本**：`安装.bat` 的 `YAHADIR/YAHADLL` 是否仍是 yaha DLL（有没有又改回 `version.dll`）；
4. **服务端**：`cache_server.py` 是否新增 `version` 校验、`tamper.cfg`、`GKM_*` 环境变量；
5. **数据**：`cache/` 条数、`masterTrans/` 文件数、`static_userget.bin` 大小、`forge/SystemCheck.bin` 是否换新；
6. **协议**：对比 `unlock.py` 的 `SECKEY`/`F_*` 字段号。

---

## 附录 A：45 个导出（proxy 与 v3.6.0 原版完全一致）

```
yaha_build_client
yaha_client_config_add_client_auth_certificates      yaha_client_config_add_client_auth_key
yaha_client_config_add_override_server_name          yaha_client_config_add_root_certificates
yaha_client_config_connect_timeout                   yaha_client_config_http2_adaptive_window
yaha_client_config_http2_initial_connection_window_size
yaha_client_config_http2_initial_max_send_streams
yaha_client_config_http2_initial_stream_window_size
yaha_client_config_http2_keep_alive_interval         yaha_client_config_http2_keep_alive_timeout
yaha_client_config_http2_keep_alive_while_idle
yaha_client_config_http2_max_concurrent_reset_streams
yaha_client_config_http2_max_frame_size              yaha_client_config_http2_max_send_buf_size
yaha_client_config_http2_only                        yaha_client_config_pool_idle_timeout
yaha_client_config_pool_max_idle_per_host
yaha_client_config_set_server_certificate_verification_handler
yaha_client_config_skip_certificate_verification
yaha_complete_task                                   yaha_dispose_context
yaha_dispose_runtime                                 yaha_free_byte_buffer
yaha_get_last_error                                  yaha_init_context
yaha_init_runtime                                    yaha_request_abort
yaha_request_begin                                   yaha_request_complete_body
yaha_request_destroy                                 yaha_request_new
yaha_request_response_get_header_key                 yaha_request_response_get_header_value
yaha_request_response_get_headers_count              yaha_request_response_get_trailers_count
yaha_request_response_get_trailers_key               yaha_request_response_get_trailers_value
yaha_request_set_has_body                            yaha_request_set_header
yaha_request_set_method                              yaha_request_set_uri
yaha_request_set_version                             yaha_request_write_body
```

## 附录 B：本机实测事实（用于对照新包）

| 项 | 值 |
|---|---|
| 游戏目录 | `D:\Games\Gakumas\gakumas`，12,631.4 MB / 20,540 files |
| `gakumas.exe` | 641,160 B，2026-11-13 19:36 |
| `gakumas.exe._` | 661,360 B，2026-11-13 19:36 |
| `GameAssembly.dll` | 164,327,424 B（156.7 MiB），2026-11-13 19:37；**磁盘上是 DMM 加密形态**（4 KiB stub + ~114 MB 加密块） |
| `global-metadata.dat` | 46,660,356 B，2026-11-13 19:37，sha256 `856a60ff…` |
| `version.dll` | 5,995,520 B，2026-09-17（DMM DRM） |
| 原版 yaha DLL | 3,149,824 B，2026-11-09，sha256 `9899ab66fe3dc53d…`，internal `yaha_native.dll` |
| 包内 hook | 3,271,680 B，sha256 `866f913a047d712b…`，internal `yaha_proxy_v9.dll` |
| 是否已安装 | **否**（无 `.orig.dll`） |
| D 盘剩余 | 17.9 GB |

> 注意：`GameAssembly.dll` 的"体积 160.5 MB vs 154.3 MB"之类的对比对本 hook 没有意义——hook 完全不碰它，也不依赖任何 IL2CPP 偏移。

## 附录 C：本次只读证据命令

```powershell
# PE/导出/字符串（无第三方依赖）
python tools\yaha_hook_check.py

# 包内字符串（wrapper 区）
python - <<'PY'
import re
d=open(r'...\hook\yaha_proxy.dll','rb').read()[:130000]
for m in re.finditer(rb'[ -~]{4,}', d): print(m.group(0).decode('latin-1'))
PY

# 版本关键字
Select-String -Path ...\mitm\*.py -Pattern 'version|3\.5|3\.6|app_ver|master_version'

# 当前 metadata 是否仍含 AES key
Select-String -Path data\reverse\out\stringliteral.json -Pattern 'Kb31v85u'
```

---

**边界声明**：以上均为静态分析；未运行 `安装.bat`/`启动.bat`/游戏，未写游戏目录，未连接官服。新包到手后按 §6 逐项对比即可给出"直接用 / 小改 / 重做数据"的结论。
