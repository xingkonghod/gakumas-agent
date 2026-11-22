# 真机采集链路（2026-11-20 打通）

## 一句话
游戏副本跑在 `C:\GakumasLocal`，网络 hook 把请求导到本地服务，服务端透明转发到官服并把请求/响应解密后落盘。

## 结构
```
C:\GakumasLocal\                     ← 游戏副本（12.34GB，从 D 盘完整复制，D 盘原版不动）
  gakumas_Data\Plugins\x86_64\
    Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll   ← hook（h2c 版）
    ...orig.dll                                          ← 原版备份
  GakumasUnlock\
    mitm\cache_server.py      ← 本地服务（online 透明代理 + 采集）
    mitm\launch_game.ps1      ← 启动游戏（代理探测、token、环境变量）
    mitm\capture_launch.ps1   ← 一键流程（外网预检 → token → 服务 → 游戏）
    一键采集启动.bat           ← 双击入口
    out\traffic.jsonl         ← **采集结果**
    out\service.out.log       ← 服务日志
```

## 关键配置
| 项 | 值 | 说明 |
|---|---|---|
| 模式 | `GKM_MODE=online` | 离线模式不能跑培育 |
| 上游 | 直连（TUN）或 7897 代理 | 服务端自动探测 |
| 解锁 | `GKM_UNLOCK=0` | **必须关**，否则污染账号数据 |
| forge | `GKM_FORGE=0` | 同上 |
| 静态用户 | `GKM_STATIC_USER=0` | 同上 |
| 采集 | `GKM_TRAFFIC=1` | 写 `av\traffic.jsonl` |
| 加密 | AES-CBC，`SECKEY=b"Kb31v85u"` | 服务端自动解密 |

## 已解决的四个坑
1. **TLS 不被信任**（客户端 rustls 编译进根证书）→ hook 改走明文 h2c（18444）
2. **grpc-dotnet 降级 HTTP/1.1** → hook 强制 `http2_only=1` + `skip_certificate_verification=1`
3. **Firebase 走 libcurl 不用系统代理** → 启动脚本注入 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`（仅 Firebase 域名）
4. **代理端口已关仍注入** → 启动前 TCP 探测 7897/7890/TUN，不通则**清除**代理变量（不能写空字符串，libcurl 会报 `Curl error 5`）

## 用途
```powershell
# 采集一局
双击 C:\GakumasLocal\GakumasUnlock\一键采集启动.bat
# 提取考试结果
.venv\Scripts\python.exe scripts\extract_exams.py
```

## 已验证的真实数据
| 时间 | 考试 | 名次 | 分数 | 歌唱 | 舞蹈 | 表现 | 操作数 |
|---|---|---:|---:|---:|---:|---:|---:|
| 12:37 | 期中 | 3 | 569 | 413 | 87 | 69 | 10 |
| 15:10 | 期末 | 2 | 4798 | 3266 | 476 | 1056 | 17 |

整局最终：B / 7404，三维 1011 / 493 / 779。

## 还没做的
- **选偶像**：bot 不会在偶像列表里挑人（只点"下一步"），需要人工选好再交给 bot
- 离线培育：我们仍不做；作者 11-22 包已新增 `produce_runtime.py`（Selection Exam/produce-007
  状态机，只到 lesson/event/shop/rest，**没有考试结算**）——与我们采集链路无关，
  只作为 E0 实验候选，见 [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md) §2.2。

## 游戏客户端大版本更新后自检（2026-11-22 外部经验吸收）

> 完整判据表在 [TROUBLESHOOTING §四](TROUBLESHOOTING.md)；来源见
> [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)（作者 11-22 整合包，只读参考）。
> 更新后按顺序走，**不要**用「绕过校验/伪造版本/旧目录当最新」换一次能跑。

1. **先 DMM 更新完再采集**：官方 `System/Check` 返回 HTTP 200 空体 + `x-error-code=2004`
   = 客户端太旧（不是本地服务坏），先 DMM 更新并进大厅（TROUBLESHOOTING 四#1）。
2. **核对 hook 还在**：DMM 更新会把 hook DLL 还原成原版 → 游戏直连官服、`traffic.jsonl`
   不再增长。重装 hook 后必须证明一次「起采集 → 进大厅 → traffic 有新行」；
   模式判定要用显式标记，**不要**只比对 DLL 文件是否相同（四#2）。
3. **证书/TLS**：本地 h2c 明文方案不变（上面四坑 1/2）；若改用接管系统代理的离线模式，
   停服务必须**先还原系统代理再停进程**，顺序反了全机断网（四#9/#10）。
4. **上游代理**：端口别写死，按 7897/7890/TUN 探测后注入或清除环境变量（TROUBLESHOOTING
   1.6/1.9）；Firebase 的 libcurl 环境变量仍要注入（1.5）。
5. **登录票据**：DMM 重启后刷新 `onetime_token`（1.8）；抓包时可照作者判据核对
   `Auth/Login` 请求体（865 正常 / 833 缺 32 字节 token → 1003；`x-p-s` 只在 DMM 常驻时
   有值，四#7）。
6. **协议/主表变化 = 停**：见 `Protocol changed` / `compatibility review required` /
   `master envelope differs`，或 Master 表结构/长度/SQLCipher 校验失败 → 保留旧数据、
   不重试不伪造，记录客户端版本与原始样本后改代码（四#3/#4）；版本哈希不透明，
   **不要按文件时间判新旧**（四#5）。
7. **采到新局后重建并核对**（不绿就是采集断链，先修再谈别的）：
   `.venv\Scripts\python.exe scripts\build_exam_setup.py`（应 4/4 场、初始 86/86、重洗 24/24）
   → `scripts\verify_exam_wiring.py`（应 36/36 手牌、3/3 重洗、known_draw 29/29、beam 28）。
8. **更新后自清理**：本地服务会占住解压目录（删目录报「正在运行中」）；先还原代理、
   再停服务、再删目录（四#9/#11）。


## 窗口必须是 720x1280 客户区（2026-11-20 踩坑）

C 盘副本启动时窗口只有 **540x960**（0.75 倍），而 bot 的点击坐标按 720x1280 设计算，
结果所有点击都落在错误位置（点「领取」落到卡片区、点 ✕ 落到卡片），
表现为「领卡弹窗反复出现 / 在日程-目标标签间来回切 / 面板自己关掉」。

**修法**：把窗口客户区调回 720x1280。
```powershell
# 用 MoveWindow 按边框差补到客户区 720x1280（实测窗口 733x1316）
```
调完后 `GetClientRect` 应为 `(720, 1280)`。
