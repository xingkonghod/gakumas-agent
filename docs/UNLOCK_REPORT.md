# GakumasUnlock 数据采集评估（只读阶段报告）

> 对象：`data/unlock/GakumasUnlock/`（`GakumasUnlock-v3.5.0-CWDFIX-20261018`，适配游戏 v3.5.0）
> 本机客户端：**v3.6.0**（`stringliteral.json` 中存在字面量 `"3.6.0"`；游戏文件时间戳 2026-11-13）
> 约束：本报告全部基于**静态阅读**，未安装、未启动游戏、未连接官服、未使用用户账号。
> 生成时间：2026-11-20

---

## 0. TL;DR

| 问题 | 结论 |
|---|---|
| 这个包是不是完整私服？ | **不是**。`cache_server.py` 是「gRPC 响应缓存/回放 + 解锁篡改」层，没有业务状态机 |
| 考试（audition）结算是谁算的？ | **客户端算、上传**；服务端另有**复算校验**（`AntiCheatSummaryResult.calculated_score` vs `logged_score`） |
| 离线（断网）模式能产生考试数据吗？ | **不能**。`使用说明.txt` 明确「培育需要完整服务端状态机，本方案不支持」，缓存里也没有任何 `Produce/Step*` 响应 |
| 想拿 ground truth 该怎么做？ | **在线 MITM**：保留真实官服，只把流量截下来解密（AES key 在 v3.6.0 未变） |
| 现有日志够不够？ | 有 `mitm/mitm.log` + `mitm/records/*.json`（hex），但**不覆盖生产对局**，且需加解密/JSONL 落盘 |
| 安装风险 | 只改**一个 DLL**（yaha native），有 `.orig.dll` 备份，3 秒可还原；但用户在用客户端，建议**硬链接克隆**到副本再装 |
| 适配 v3.6.0 | **hook 本身几乎零成本**（按导出名转发，45/45 名字完全一致）；真正的工作量在**缓存/master/协议** |

---

## 1. 包与运行机制（实测）

### 1.1 安装/启动链路

| 文件 | 行为（源码实测） |
|---|---|
| `安装.bat`（GBK） | 找游戏目录写 `game_path.txt` → 关游戏 → 备份并替换 **1 个文件**：`gakumas_Data\Plugins\x86_64\Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll` → 备份为 `....Native.orig.dll` → 检查 `Crypto/h2` |
| `启动.bat` | 停旧服务 → `start /min powershell start_service.ps1` → 轮询 `Get-NetTCPConnection -LocalPort 18443` → `launch_game.ps1` 用 `launch-args.json` 直接 `Start-Process gakumas.exe`（跳过 DMM）；首次没有 args 时走 `capture_args.ps1` |
| `mitm/start_service.ps1` / `serve.bat` | 起 `python\python.exe cache_server.py`，关键环境变量见下 |
| `mitm/launch_game.ps1` | `gakumas.exe /viewer_id=… /onetime_token=… /open_id=… /pf_access_token=…`，工作目录 = 游戏目录 |
| `mitm/capture_args.ps1` | 先 `NtQueryInformationProcess` 读 PEB 拿命令行，失败退 `Get-CimInstance Win32_Process`；写 `launch-args.json` |
| `卸载.bat` | 恢复 `.orig.dll` → 删 `.orig.dll` → 删 `game_path.txt` |

**重要：`安装.bat` 不碰 `version.dll`。** 当前游戏目录的 `version.dll` 仍是 DMM 的 DRM 解密器（5,995,520 B，2026-09-17）。README 目录树里写的 `version.dll` 是**过期文档**；`使用说明.txt` 开头（2026-10-17 更新说明）已写明改用 yaha 网络库替换。

### 1.2 服务端口与模式（`mitm/start_service.ps1`）

```powershell
$env:GKM_MODE           = 'offline'      # cache-only
$env:GKM_MATCH          = 'exact'        # path + sha1(body) 严格匹配
$env:GKM_MITM_PORT      = '18443'        # TLS(h2) 监听
$env:GKM_H2C_PORT       = '18444'        # 明文 h2c 监听（hook 重写 URI 用）
$env:GKM_UPSTREAM_PROXY = '127.0.0.1:1'  # 永远连不上 = 纯离线
$env:GKM_STATIC_USER    = '1'            # 用 static_userget.bin 当 User/Get
```

`cache_server.py` 的处理优先级（`mitm/cache_server.py:396-587`）：

```
特殊写操作(UNLOCKER.handle_write) → Gasha/Draw → IdolCard/Release → Profile(已禁用)
→ FORGE(forge/index.json, 最高优先级) → CACHE(offline/hybrid) → UPSTREAM(online)
→ offline-fallbacks/<Api>.bin → 空成功帧(b'\x00\x00\x00\x00\x04\xfa\xf0\x04\x00')
```

### 1.3 协议与加密（这是采集的关键资产）

`mitm/unlock.py:24-25, 181-217`：

```python
SECKEY = b"Kb31v85u"                    # global-metadata.dat stringLiteral[14296]
AESKEY = hashlib.md5(SECKEY).digest()

def decrypt_body(rb):
    ln = int.from_bytes(rb[1:5], "big")     # 5 字节 gRPC 帧头
    pl = rb[5:5+ln]
    kl = pl[3]; hk = pl[4:4+kl]             # 每帧随机 hk（29 字符 base62）
    iv = hashlib.md5(SECKEY + hk).digest()
    pt = AES.new(AESKEY, AES.MODE_CBC, iv).decrypt(pl[4+kl:])
    return pt[:-pt[-1]]                     # PKCS#7
```

实测（本次运行，读缓存不回放）：

```
/client.api.Costume/Set      reqlen=81  dec=53 B head=0a0473736d6b10011a1b636f7374756d65...
/client.api.Auth/Login       reqlen=865 dec=844 B head=0ac90665794a68624763694f694a...
```

**结论：请求体、响应体都能用同一个 key 解成明文 protobuf。** 且该 key 在 v3.6.0 的 metadata 中仍然存在（`stringliteral.json` index **14654**，注意不是包里注释写的 14296），所以升级后依然能解。

---

## 2. API 端点清单

协议是 gRPC over HTTP/2，路径格式固定 `/client.api.<Service>/<Method>`。服务端**不按端点做业务路由**，只按路径做缓存/forge/解锁，所以"端点清单"有两个来源：①包里抓到的；②客户端二进制里的完整 RPC 面。

### 2.1 假服务端会"特殊处理"的路径（`cache_server.py` / `unlock.py`）

| 路径 | 处理 | 位置 |
|---|---|---|
| `/client.api.User/Get` | 永不缓存（`NO_CACHE_PATHS`），离线直接发 `static_userget.bin` | `cache_server.py:31, 544-565` |
| `/client.api.System/Check` | FORGE 固定响应（`forge/SystemCheck.bin`，1064 B） | `cache_server.py:100-127`；`forge/index.json` |
| `/client.api.Gasha/Draw` | 本地伪造抽卡结果 | `cache_server.py:406-420` |
| `/client.api.IdolCard/Release` | 本地固定响应 | `cache_server.py:423-434` |
| `/client.api.Profile/Get` | 篡改名字/评论（本地分支已 `if False` 关闭）；转发后会 dump 到 `profile-real.hex` | `cache_server.py:436, 517-532` |
| `/client.api.Costume/Set` | 写操作本地处理 + 更新解锁状态 | `unlock.py:1228-1236` |
| `/client.api.Story/Read`、`/Story/ReadProduceStory`、`/Story/ReadDearnessStory`、`/Story/Unlock`、`/Story/UnlockProduceStory`、`/Story/UnlockDearnessStory` | 写操作本地处理 | `unlock.py:1237-1274, 1352-1405` |
| `/client.api.Tutorial/Progress`、`/Home/SetCharacters` | 写操作本地处理 | `unlock.py:1266-1284, 1317-1336` |

### 2.2 已缓存 / 可离线回放的 API（`mitm/cache/`，33 个 API 目录，288 条）

```
Auth/Login 109      CoinGasha/List 0    Costume/Set 28       Friend/List 1
Gasha/Draw 4        Gasha/GetPrecaution 1                    Home/Enter 1
Home/ListEvent 1    Home/Login 1        IdolCard/Release 2   LoginBonus/Check 1
Master/Get 1        Meishi/Get 1        Mission/Receive 7    Music/SendActionLog 3
Notice/Get 1        Notice/ListAll 1    Notice/UpdateCategoryTime 3
Produce/Top 1       Produce/ViewPictureBookLive 44           Profile/Get 9
Profile/UpdateName 1                    PvpRate/Get 1        SelectionMemory/List 1
Shop/Top 1          Story/ReadDearnessStory 8                Story/Unlock 1
Story/UnlockProduceStory 1              System/Check 43      Tutorial/Progress 6
Tutorial/UnlockFeature 2                User/Get 1           Work/Start 2
```

另有 `mitm/offline-fallbacks/` 27 个 `.bin`（Auth_Login、Home_Enter、Master_Get、Produce_Top、User_Get 818 KB 等），`mitm/records/` 7 条完整请求/响应审计样本。

**注意：`Produce` 只有 `Top` 和 `ViewPictureBookLive` 两个端点有缓存——没有 `Produce/Start`、`Produce/Step*`、`Produce/Result`。**

### 2.3 客户端完整 gRPC 面（从 v3.6.0 `global-metadata.dat` 提取）

- **53 个 service**：`Auth, Character, CoinGasha, Competition, Costume, Exchange, Friend, Gasha, Gift, Guild, GvgRaid, Health, Home, IdolCard, Invitation, Item, LoginBonus, Master, Media, Meishi, Memory, MemoryRemake, Mission, Money, Movie, Music, Notice, Photo, PlayGames, Preference, Produce, ProduceHighScore, ProduceSeason, ProducerRanking, Profile, PvpRate, Refine, Research, SelectionMemory, Seminar, Shop, Startup, Story, StoryEvent, SupportCard, System, TicketExchange, Tour, Tower, Trail, Tutorial, User, UserBlock, Work`
- **303 个 RPC 方法名**（`__Method_*` 常量）
- **191 个 Produce/Exam 相关请求/响应消息类**（`Produce*Request/Response`）

### 2.4 produce（培育）与 exam（考试）相关 RPC

按客户端消息类/方法常量整理（路径 = `/client.api.Produce/<Method>`，待在线日志最终确认前缀）：

| 阶段 | RPC / 消息 | 说明 |
|---|---|---|
| 入口 | `Top` | 培育首页（包里有缓存） |
| 开局 | `ProduceStart` / `ProduceStartRequest/Response` | 选偶像卡/支援卡/记忆，服务端建 session |
| 流程 | `ProduceNext`、`ProduceNextSkip`、`ProduceSave`、`ProduceCheckProgress`、`ProduceContinue`、`ProduceRestart`、`ProduceRetire`、`ProduceEnd` | 步骤推进/存档/中断 |
| 考试开始 | `StepAuditionStart`、`StepAuditionRefresh`、`StepAuditionContinue` | 抽 NPC、刷新手牌 |
| **考试结算** | **`StepAuditionEndExamBattle`** ← `ProduceStepAuditionEndExamBattleRequest/Response` | **客户端上报整场战斗结果** |
| 考试收尾 | `StepAuditionEnd` → `ProduceStepAuditionEndResponse`（奖励/记忆奖励/效果） | 服务端回奖励 |
| 考试结果（UI/别的模式） | `StepAuditionExamEnd`、`StepAuditionExamResult`、`RefineStepAuditionExamResult` | 只带 mission 序号，响应只有奖励 |
| 课程/小考 | `StepLessonStart/Continue/End/ExamEnd/ExamResult`、`StepOpenLesson*`、`StepSelfLesson*` | 同类结构 |
| 回放/反作弊 | **`SendExamReplayLog`** → `ProduceSendExamReplayLogRequest`（produceId + idolCardId + replayRouteType + target…） | 服务端指定样本上传 |
| 最终结算 | `ProduceResult` → `ProduceResultResponse` | 奖励 / 高分更新 / 挑战槽 / 排名结果，**不含单场分数** |
| 其它 | `GetExam`、`ListExam`、`PlayExamBattle`、`EndExam`、`PvpRatePlayExamBattle`、`SeminarGetExamRawResult` | PVP/研讨会也有考试 |

---

## 3. 考试结算是客户端算还是服务端算？（代码证据）

> 证据来源：`data/reverse/out/dump.cs`（由**当前 v3.6.0** 的 `global-metadata.dat` 生成，仅元数据无函数体，但**消息字段号完整**）。

### 证据 1：上报请求里带着完整战斗结果

`ProduceStepAuditionEndExamBattleRequest`（dump.cs:445153-445200）：

```csharp
type#104421 ResultFieldNumber = 2;        // Common.ExamBattleResult Result
type#104421 TurnEndLogsFieldNumber = 3;   // repeated 回合结算日志
type#104421 DeviceProduceUuidFieldNumber = 4;
type#104421 NpcResultsFieldNumber = 5;    // repeated { Number, Score }
```

同一请求的**响应**（dump.cs:445214-445255）只有：

```csharp
type#104421 ShouldTransitionSeminarFieldNumber = 1;
type#104421 CommonResponseFieldNumber = 9999;
```

→ 响应里**没有任何分数/名次**，说明分数不是服务端在这一步算完回传的。

### 证据 2：`ExamBattleResult` 字段 = 我们要的全部 ground truth

`Campus.Common.Proto.Client.Common.ExamBattleResult`（dump.cs:471107-471186）：

```csharp
RankFieldNumber          = 1;   // 名次
ScoreFieldNumber         = 2;   // 总分
StaminaFieldNumber       = 3;   // 剩余体力
ProduceDrinkIdsFieldNumber = 5;
ProduceItemsFieldNumber  = 6;
ExamTriggerCountsFieldNumber = 7;
VocalScoreFieldNumber    = 8;   // 三维
DanceScoreFieldNumber    = 9;
VisualScoreFieldNumber   = 10;
ExamActionsFieldNumber   = 100; // repeated ExamCommandLog（出牌/移卡/喝饮料…）
```

`ExamCommandLog`（dump.cs:471200-…）：`commandType`、`phaseType`、`selectIndexes`、`useIndex`、`useProduceCard`、`useProduceDrinkId` —— **逐操作可还原**。

### 证据 3：服务端确实会复算（反作弊）

`Campus.Common.Proto.Client.Common.AntiCheatSummaryResult.Types.Score`（dump.cs:475519-475549）：

```csharp
IdFieldNumber              = 1;
CalculatedScoreFieldNumber = 2;   // 服务端复算分
LoggedScoreFieldNumber     = 3;   // 客户端上报分
```

`ExamAntiCheatTarget`（dump.cs:475458-475505）：`features / dates / userIds / logIds` —— 服务端抽检哪些战斗日志。配合 `ProduceSendExamReplayLog` 使用。

### 证据 4：客户端内建确定性考试模拟器

metadata 里存在：`ExamPlayLogSimulator`、`ExamSimulation`、`ExamSimulationId`、`ExamSeedValue`、`ExamBattleBaseScore`、`ExamBattleConditionThresholdMultipleScore`、`ExamResultType`、`ReceiveExamResultAsync`、`StepAuditionExamResultAsync`（`Campus.InGame.*`）。即客户端能凭 log 重放整场考试，服务端也有同样的 Go 实现用于校验。

### 结论

```
客户端：抽牌/出牌/结算 → 本地 ExamSimulation 算分/名次 → 立即展示
                     ↓
        StepAuditionEndExamBattle{ ExamBattleResult(Rank,Score,Vocal,Dance,Visual),
                                   TurnEndLogs, NpcResults }   ← 明文可截获
                     ↓
服务端：用 ExamActions/TurnEndLogs 复算 → AntiCheat* 比对 → 记录 HighScore → 回奖励
```

**采集定位：`ProduceStepAuditionEndExamBattle` 的请求体 = 一局中每一场考试的"玩家所见"结算（分数/名次/三维/操作序列），是天然 ground truth；服务端复算值只在反作弊回执里出现（不是每局都有）。**

---

## 4. 现有日志能力

| 日志 | 位置 | 内容 | 对采集是否够用 |
|---|---|---|---|
| `mitm.log` | `mitm/mitm.log`（`cache_server.py:53,57-66`） | `REQ <path>`、`BODY <path> len=`、`CACHE HIT / UPSTREAM / FORGE / LOCAL / OFFLINE-EMPTY`、TLS 错误 | 只有路径和长度，无内容 |
| `records/` | `mitm/records/<seq>_<path>.json` | `req_body_hex`、`resp_body_hex`、`status`、`source`、`ts`（`cache_server.py:676-683`） | 有内容但是**密文 hex**，且**早退分支**（Gasha/IdolCard/本地写操作/离线兜底）不落盘 |
| `yaha-proxy.log` | hook 目录（字符串 `%syaha-proxy.log`） | hook 自己的 `### REDIRECT/REQ_BODY/HEX` 日志 | 也是密文；且只在 DLL 侧 |
| `probe-report.txt` | `mitm/` | `GKM_TAMPER=probe` 时生成 | 与采集无关 |
| `capture.log` | `mitm/capture.log` | 抓 `viewer_id` 的探测日志 | 无关 |

**缺口：没有一份「解密后的、逐请求的、可解析字段的」JSONL。**

---

## 5. 安装风险与建议方案（等批准，不装）

### 5.1 实际改动面

- 只替换 `gakumas_Data\Plugins\x86_64\Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll`（3,149,824 B）；
- 备份 `...Native.orig.dll`；
- **不动** `version.dll` / `GameAssembly.dll` / `global-metadata.dat`；
- 游戏目录内容零改动（不写 assets）。

### 5.2 风险点

| 风险 | 等级 | 说明 |
|---|---|---|
| 用户正在用客户端 | 中 | 替换后若崩溃，游戏需先还原 DLL 才能正常玩；`卸载.bat` 3 秒可还原 |
| 版本漂移 | 中 | 包适配 v3.5.0；本机已 v3.6.0。hook 本身按导出名转发（见 `UNLOCK_ADAPT.md`），但缓存/master 是 3.5.0 的 |
| 磁盘 | 中 | 游戏目录 **12,631.4 MB / 20,540 文件**；D 盘剩余 **17.9 GB** → 完整复制可行但只剩 5.3 GB |
| 反作弊/封号 | 低-中 | 离线模式零外发；**在线采集会用真实账号发真实请求**，风险由用户承担 |
| 回滚 | 低 | `.orig.dll` + `卸载.bat`；手工 `copy /Y .orig.dll .dll` 也行 |

### 5.3 三个方案（按推荐排序）

1. **硬链接克隆到 `D:\Games\GakumasLocal2\`（推荐，0 额外空间）**
   - `New-Item -ItemType HardLink` 逐文件链接（同盘 NTFS），**排除 `gakumas.exe`**（DMM DRM 启动时会重写它，硬链接会污染原目录）；
   - 或者 `robocopy /MIR` 全量复制（12.6 GB，剩 5.3 GB，可接受但不宽裕）；
   - 在副本上 `安装.bat`（`game_path.txt` 指向副本）；
   - 原目录零接触，用户随时可玩。
2. **临时单 DLL 换入/换出（最轻）**
   - 只在采集会话期间替换 DLL，结束后立即 `copy /Y .orig.dll .dll`；
   - 风险是会话中断来不及还原（概率低，但会直接影响用户）。
3. **全量复制 + 保留**（如果要长期跑采集，方案 1 的镜像更好）。

> **不推荐**：在 `D:\Games\Gakumas\gakumas` 上直接安装再依赖 `卸载.bat`——满足不了"不污染"的要求。

---

## 6. 采集方案：怎么拿到"一局培育的每一场考试得分/名次"

### 6.1 为什么不能用离线模式

- `使用说明.txt`：**「Q: 培育能玩吗 A: 不能。培育需要完整的服务端状态机，本方案不支持。」**
- 缓存里没有 `Produce/Start`、`Produce/Step*`、`Produce/Result`；
- 离线时未命中端点返回空帧 → 培育在第一步就会卡住；
- 所以 **离线假服务端永远看不到考试数据**。

### 6.2 推荐：在线透明 MITM（保留真实服务端）

架构不变（hook → `127.0.0.1:18443` → `cache_server.py`），只改：

```bat
set GKM_MODE=online              (或 hybrid)
set GKM_UPSTREAM_PROXY=127.0.0.1:7897    (Clash 日本节点)
set GKM_STATIC_USER=0            (用真实账号数据)
set GKM_CAPTURE=1                (新增)
```

**必须同时关闭解锁篡改**（`UNLOCKER.tamper` / `static_user`），否则：
1. 上行的解锁列表会污染真实账号数据；
2. 响应被改后，采集到的不是"原始 ground truth"。

前置条件：日本 IP、用户自己的 DMM 账号、`launch-args.json`（token 几小时~一天过期）。这一步**需要用户明确同意用其账号在线跑**。

### 6.3 加日志：`data/unlock/traffic.jsonl`

在 `handle_client` 的 `StreamEnded` 分支、拿到完整 `path/body` 后（`cache_server.py:385`）和响应发送前（`:663`）插入：

```python
import unlock, json, time, datetime
def _cap(seq, direction, path, raw, meta=None):
    try:
        pt = unlock.decrypt_body(raw)          # gRPC 帧 → 明文 protobuf
        rec = {
            'ts': datetime.datetime.now().isoformat(timespec='milliseconds'),
            'seq': seq, 'dir': direction, 'path': path,
            'len': len(raw), 'plain_len': None if pt is None else len(pt),
            # 首选：按 dump.cs 生成的 schema 解码成 JSON
            'msg': decode_message(path, direction, pt) if pt else None,
            # 兜底：保留明文/密文 hex，任何时候都能离线重解
            'plain_hex': pt.hex() if pt else None,
            'raw_hex': raw.hex(),
            **(meta or {}),
        }
        with open(r'D:\Games\gakumas-agent\data\unlock\traffic.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass
```

要点：

1. **双向都记**（请求 + 响应）；请求体同样能用 `decrypt_body` 解开（已实测）。
2. **字段名从 `dump.cs` 自动生成**：dump.cs 里每个消息都有 `XxxFieldNumber = N` + 属性类型，可脚本解析成 `{类名: {字段号: 字段名}}`，再用 `unlock.fields()` 递归解码，不需要手写 `.proto`。
3. **落盘按 append + 每行一条**，游戏崩溃也不丢；文件放 `data/unlock/`，不写进游戏目录。
4. 可选：直接按 `produce_id` 聚合出 `data/unlock/produce_runs.jsonl`（一场培育一行，内嵌每场考试）。

### 6.4 要重点抓的端点（按价值排序）

| 优先级 | 路径 | 产出 |
|---|---|---|
| P0 | `/client.api.Produce/StepAuditionEndExamBattle` | **每场考试：rank/score/vocal/dance/visual/stamina + 逐操作 ExamActions + NPC 分** |
| P0 | `/client.api.Produce/StepAuditionEnd` | 该场奖励/记忆奖励 |
| P1 | `/client.api.Produce/ProduceStart`、`ProduceNext`、`ProduceSave`、`ProduceCheckProgress` | 牌组、支援卡、事件三选一、卡牌成长 → 完整一局轨迹 |
| P1 | `/client.api.Produce/ProduceResult` | 最终评级/奖励/高分更新（`HighScoreUpdateResult` = 服务端认可分） |
| P2 | `/client.api.Produce/SendExamReplayLog` 及其响应 | 服务端抽检/复算信息 |
| P2 | `/client.api.ProduceHighScore/*`、`ProducerRanking/*` | 别家/历史分数，可做对照集 |

> 抓不到 `StepAuditionEndExamBattle` 时的兜底：`User/Get` 返回的 `UserProduce*` 里含历史（produce history/high score），可以在 `User/Get` 全量快照里离线挖。

### 6.5 数据校验（防"客户端算的分不可信"）

- 客户端上报分 vs 服务端 `AntiCheatSummaryResult.calculated_score`（抽检时才有）；
- `ProduceResultResponse.HighScoreUpdateResult` 里的 after/before 分数（服务端认可）；
- 用 `ExamActions` 自己写回放器，与 `ExamBattleResult` 对拍（仓库已有 `docs/RULES_FROM_BINARY.md`、`SIMULATOR.md` 可复用）。

---

## 7. 版本状态

本机客户端已是 **v3.6.0**，该包为 v3.5.0 构建。详细适配评估见 **`docs/UNLOCK_ADAPT.md`**（hook 机制、版本检查、难度评级、dump.cs 如何复用）。简要结论：

- hook 按**导出名**转发，与 v3.6.0 现装 DLL 的 45 个导出**完全一致** → hook 本身大概率可用；
- 服务端**没有版本校验**（`cache_server.py`/`unlock.py` 无任何 version 判断）；
- 真正的兼容性风险在 master 数据/缓存/新内容，不在 hook。

---

## 附：本次分析用到的只读命令/脚本

- `tools/yaha_hook_check.py`（新增，无依赖，可对比新包）
- `data/reverse/out/dump.cs`（v3.6.0，101.6 万行）、`stringliteral.json`
- `data/reverse/unlock_pe.py`（PE 导出/导入/字符串）
- `data/reverse/unlock_decrypt_probe.py`（解密 SystemCheck / Produce_Top / 缓存响应）
- `data/reverse/unlock_endpoints_scan.py` + `unlock_endpoints_scan.out.txt`（303 个 RPC 方法 / 191 个消息类清单）
- 全程未执行 `安装.bat`/`启动.bat`/游戏，未写游戏目录，未联网到官服。
