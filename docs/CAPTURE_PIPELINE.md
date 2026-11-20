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
- 离线培育（服务端状态机，作者暂不做）
