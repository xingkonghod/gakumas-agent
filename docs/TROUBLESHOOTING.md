# 踩坑记录（实际问题 + 根因 + 修法）

> 只记**真实遇到过、并且确认了原因**的问题。按「现象 → 根因 → 修法 → 教训」写。
> 遇到新问题时先查这里，避免重复踩。

---

## 一、采集链路（最耗时的部分）

### 1.1 内存读不了：管理员也被拒

**现象**
```
OpenProcess             成功
EnumProcessModulesEx    err=5 (ACCESS_DENIED)
ReadProcessMemory       err=5 (ACCESS_DENIED)
同一份代码读 notepad    正常（69 模块）
```

**根因**：游戏进程有内核级保护（反作弊驱动 strip 句柄，不是 PPL——PPL 连 OpenProcess 都过不去）。

**修法**：放弃读内存，改走网络层（MITM）。**这也是为什么 MaaGakumasu 和我们都用 OCR。**

**教训**：先验证「能不能读」，再决定整个技术路线。我们花了两天才确认读不了。

---

### 1.2 GameAssembly.dll 被加密

**现象**
```
.text   VirtualSize 9.8MB   RawSize 4KB
il2cpp  VirtualSize 127MB   RawSize 4KB
.pdata  VirtualSize 12MB    RawSize 4KB
文件前部 114.5MB 高熵数据（熵≈8.0）
Il2CppDumper: CodeRegistration = 0
```

**根因**：代码段被加壳/加密，磁盘上没有明文。

**修法**：只从**明文的 global-metadata.dat** 解析出签名级 dump（101.6 万行），拿不到方法体。

**教训**：元数据能拿类名/字段名/枚举，但**拿不到实现**。真正要做到准确，得靠主数据 + 社区引擎。

---

### 1.3 TLS 握手失败：客户端不信任我们的证书

**现象**
```
TLSV1_ALERT_UNKNOWN_CA
SSLEOFError: UNEXPECTED_EOF_WHILE_READING
```

**根因**：客户端用 **rustls + 编译进二进制的根证书**（webpki），**不读 Windows 证书库**，所以装 `ca.pem` 到系统没用；hook 里的「强制接受证书」只在客户端调用特定函数时生效，v3.6.0 没调用。

**修法**：hook 把 `https://127.0.0.1:18443` 改成 `http://127.0.0.1:18444`（明文 h2c），并给 client 强制 `skip_certificate_verification`。

**教训**：客户端如果有自己的 TLS 栈，系统证书库的方案直接作废。

---

### 1.4 协议降级：grpc-dotnet 在明文 http 下退成 HTTP/1.1

**现象**
```
H2C peek text: 'POST /client.api.System/Check HTTP/1.1'
recv err: Invalid HTTP/2 preamble.
（客户端侧）Bad gRPC response. Response protocol downgraded to HTTP/1.1.
```

**根因**：grpc-dotnet 看到 scheme 是 `http` 就按 HTTP/1.1 发，而服务端在等 h2 preface。

**修法**：在 hook 里给 client 强制 `http2_only = 1`（改 `yaha_client_config_http2_only` 的调用）。

**教训**：改 scheme 会连锁影响协议版本，必须同时把协议固定住。

---

### 1.5 Firebase 认证超时：初始化失败的真正原因

**现象**
```
[FirebaseRestApi]: ERROR GetIdTokenAsync ... IsTimeout:[True]
Curl error 42: Callback aborted
（游戏弹）初始化错误 / 初始化失败
```

**根因**：Firebase 走 **Unity 内嵌 libcurl**，不经过 hook；而 Clash 当时是 TUN 模式、7897 关闭、系统代理也关 → Google 出不去。
DMM 启动游戏时会**注入代理环境变量**（`GamesPlayAssist.exe` 里有 `HTTP_PROXY` 等字符串），我们手动启动没注入。

**修法**：`launch_game.ps1` 给游戏进程注入 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`（仅 Firebase 域名需要）。

**教训**：游戏里有**两条网络栈**（grpc-dotnet 走 hook，libcurl 走系统/环境代理），漏一条就是「初始化失败」。

---

### 1.6 把死代理注入游戏（自己把自己坑了）

**现象**
```
Curl error 7: Failed to connect to 127.0.0.1 port 7897
（改成空字符串后）
Curl error 5: Unsupported proxy syntax in 'http://'
[Init] code : 300 : Connection  → 弹初始化错误
```

**根因**：脚本无条件写 `HTTP_PROXY=127.0.0.1:7897`，但用户切到 TUN 后 7897 已关；后来改成「探测不到就写空字符串」，libcurl 又报语法错。

**修法**：启动前 TCP 探测 7897/7890/TUN；**不通就删除**代理变量（`Remove-Item Env:...`），不要写空字符串。

**教训**：环境变量要么设成合法值，要么**完全不存在**，空字符串是毒药。

---

### 1.7 服务随控制台一起被杀

**现象**：双击 bat 启动后，控制台一关，服务和游戏一起退出。

**根因**：子进程挂在控制台进程树上，控制台退出被连带清理。

**修法**：服务用 WMI/独立进程启动；bat 末尾不要立刻 `timeout` 结束。

**教训**：Windows 上「后台服务」必须真正脱离父进程。

---

### 1.8 token 过期

**现象**：点标题弹「通信エラー」。

**根因**：`launch-args.json` 里的 `onetime_token` 会过期；每次从 DMM 启动会生成新的，写在
`C:\Users\<用户>\AppData\Roaming\dmmgameplayer5\logs\dll.log`。

**修法**：一键脚本从 `dll.log` 取最新一条 `Execute of:: gakumas ... /onetime_token=...` 刷新。

**教训**：游戏启动参数可以从 DMM 的日志里读，**不需要注入进程去抓命令行**。

---

### 1.9 VPN 状态判断错误

**现象**：以为切到了 TUN，实际「无 TUN 适配器 + 7897 未监听 + mihomo 未运行」→ 什么都连不上。

**修法**：启动脚本做**外网预检**（curl 一下 Google/官服，2 秒超时），不通就明确提示并退出。

**教训**：不要假设用户说「开了」就是真开了，用代码验证。

---

## 二、bot（屏幕识别与点击）

### 2.1 点击全部落空：窗口不是 720×1280

**现象**：领卡弹窗永远关不掉；界面在「日程/育成目标」标签间来回跳。

**根因**：游戏窗口被缩放到 **540×960（0.75 倍）**，而 bot 的坐标按 720×1280 设计算，
点击全部偏移。点「领取(360,1095)」实际落到标签栏。

**修法**：`device.click()` 里按实际 `GetClientRect()` 缩放坐标。

**教训**：**窗口尺寸是隐式契约**。一开始「能用」很可能只是因为当时窗口恰好是设计尺寸。

---

### 2.2 窗口改太大，内容看不全

**现象**：我把窗口改成客户区 720×1280，用户「完全看不到下面」。

**根因**：屏幕只有 1080 高，720×1280 的窗口需要 1316 高（含边框）。

**修法**：恢复 540×960，改代码缩放（见 2.1）。

**教训**：**不要通过改环境来适配代码**，应该让代码适配环境。

---

### 2.3 bot 自己点自己，被「用户活跃」门限拦住

**现象**：领卡界面「选卡 → 领取」两连点，第二次永远不生效。

**根因**：`click()` 默认 `respect_user=True`，点击前检查 800ms 内有无输入；而**bot 自己刚点的第一下**就触发了这个判定。

**修法**：内部流程用 `click_force()`，它透传 `respect_user=False`。

**教训**：防护措施要区分「人类输入」和「自己输入」。

---

### 2.4 外出事件被误判成剧情

**现象**：卡在「外出」三选一界面，一直点「快进」，来回弹确认框。

**根因**：事件屏识别**只依赖 OCR 到「快进」按钮**，按钮小/灰时识别不到 → 落到剧情分支。

**修法**：`(「快进」 in text or 「外出」 in text) and 「请选择行动」 not in text`。

**教训**：单一特征识别容易漏；用「组合条件 + 排除条件」。

---

### 2.5 领卡弹窗与成就弹窗互相抢

**现象**：`[achievement] close` ↔ `[card-reward] pick+claim` 无限横跳。

**根因**：领卡弹窗里有「条件成就」字样，成就分支先命中，点了关闭；下一帧又识别成领卡。

**修法**：成就分支加 `and 「请选择要领取」 not in text`。

**教训**：分支顺序 + 互斥条件是屏幕识别的基本功。

---

### 2.6 误开「育成目标」面板

**现象**：bot 在行动页点到目标图标，面板弹出后关不掉，一直循环。

**根因**：面板底部 ✕ 在 (360, 1226)，而领卡「领取」在 (360, 1095)——坐标接近，误点导致面板反复开关。

**修法**：先修坐标缩放（2.1），再给面板单独的关闭分支。

**教训**：**同一个坐标在不同屏幕上含义不同**，修坐标之前先确认缩放。

---

### 2.7 守护进程（GDEAgent）反复超时

**现象**：`{"ok": false, "error": "timeout waiting for daemon"}`，但命令有时最后又执行了。

**根因**：计划任务进程状态卡住 / 命令队列有残留。

**修法**：`schtasks /End` 再 `/Run`；确认 `whoami /groups` 里是 High Mandatory Level。

**教训**：提权通道要有健康检查，不能假设一直活着。

---

## 三、评测与研究（方法论问题）

### 3.1 本地评测和官方排行榜不可比

**现象**：本地 UINet 只有 greedy 的 0.93×，官方是 3.5×。

**根因**：三件事叠起来——题集分布不同（produce-001/006 vs 007/008）、裁判不同（我们的模拟器 vs GKMS）、
我们拿不到 `exam.types`（全 Vo）和饮料/附魔/P 道具。

**修法**：本地评测**只用于内部对比**，明确标注「不可与官方对齐」。

**教训**：跨裁判的绝对分数没有意义，只能比同一裁判下的相对排名。

---

### 3.2 learned 价值函数越训越差（−52%）

**现象**：训练好的线性 V 接进 expectimax，表现暴跌。

**根因**：**训练特征读取的是 LessonSim 状态，但传进去的是 ExpectState 对象**——
clear/focus/condition/stance 全部静默读成 0，模型权重塌缩。修好后变成 +11.4%。

**教训**：跨模块传状态时，**字段名不一致是静默失败**，必须写测试断言特征非零。

---

### 3.5 把「卡牌图鉴」当成了「考试牌堆」

**现象**：在 StepAuditionStart 响应里找牌堆，只看到 9 种卡；全量 User/Get 里 `userProduceCardList`
有 155+ 张，含同一 base 的 +0/+1 双变体、跨 p_card-00/01/02/03 多前缀——怎么洗都对不上实战。

**根因**：认错了字段。`userProduceCardList`(230550472) 是**图鉴/收集库**；StepAuditionStart 里的
9 种卡是 `userProduceProgressSupportCardList`(256246388) = **支援卡**。真正的当前培育牌组是
`userProduceProgressProduceCardList`(309641228)，每张带唯一 number 和 deleted 标志。

**修法**：按 number 重建牌组，且区分更新语义——Produce/Start、User/Get 是**全量快照**（整体替换），
其余步骤响应是**增量 upsert**（混用会把上一局的卡混进来）。重建结果与 User/Get 全量快照逐张吻合。

**教训**：protobuf 里名字相近的 repeated 字段语义可能完全不同（图鉴 vs 当前牌组 vs 支援卡）；
**先用「全量快照」交叉验证重建结果**，再谈下游重放。增量/快照不分，重建必污染。

---

### 3.6 洗牌重放：四场都已破解（2026-11-21 深夜，已解决）

**原现象**：同一套 `xorshift32(examSeedValue) + Fisher-Yates倒序洗 Number升序牌堆`，
期中 K=51 → 18/18 精确；期末（26 张）无论 k=0..2000、输入排序、种子变换都复现不出，
回合集合最好仅 1/8。

**根因（三个，叠在一起）**：
1. **期末牌堆里有 `isInitial` 卡**：`p_card-02-men-2_054`（主数据 `ProduceCard.isInitial=true`）。
   客户端第 1 回合先 `SetInitialCard`——从牌堆「底→顶」扫，把 isInitial 卡抽入手牌，再补抽到 3 张。
   旧模型把首回合当「牌堆顶 3 张」，于是**每一回合都错位**；只搜 K 当然搜不到。
2. **洗牌前消耗 K 不是常数**，它随回合数变：客户端开局先抽回合属性（前 turns-3 回合随机，
   turns-3 次）＋生成 5 个 NPC 的逐回合分数（5×turns 次），然后才洗牌。
   `K = (turns-3) + npc_count*turns`：期中 9 回合→51、期末 11 回合→63（不是固定 51）。
3. **turns 是配置回合数，不是实战回合数**（2026-11-21 新采集踩到）：中间考试有
   `forceEndScore`（produce-002 プロ：1700/1800），打到封顶分就提前结束，`ExamTurnEndLog`
   只上传实战回合；但回合属性/NPC 分数开局仍按配置回合生成。那场配置 9 回合、实战 7 回合，
   按实战回合算 K=39 → 整段错位，按配置回合算 K=51 → 15/15 精确。

**修法**：`src/gkagent/sim/exam_shuffle.py` 实现完整模型；`scripts/verify_shuffle.py` 自动读
主数据的 `isInitial` 与 NPC 数，并按「配置回合 ≥ 实战回合」自动试候选 K。结果：四场全中——
11-20 期中 18/18、期末 26/26；11-21 PRO 期中 15/15、期末 27/27（回合集合 6/6、8/8、5/5、9/9）。
`tests/test_exam_shuffle.py` 加了「按实战回合算 K 会错」的回归防线。

**顺带验证**：回合属性算法放在 RNG offset 0 上能逐项复现四场考试的属性序列（末 3 回合静态表
顺序随考试变：11-20 是 [2,3,1]、11-21 是 [2,1,3]，按 NPC 权重定序）；
洗后弃牌堆重洗（11-20 期中 T7）从洗牌后状态再消耗 45 次随机数也可精确复现 9/9。
「打出后去 Lost 区」的卡不进弃牌堆，重洗只洗 Grave 区。

**教训**：
- 「精确匹配」之后还要问「模型里有没有漏掉特殊字段」——`isInitial` 这种只在特定卡上为真的标志，
  平时看不见，一出现就让整段错位。
- 常量 K 是过拟合的产物：先假设 K=51 是「算法常数」，其实它是回合数的函数。**两场考试都不能
  区分「常数」和「随结构变化的公式」时，要去拆 RNG 消耗的每一步，而不是继续暴力搜。**
- **「实战观察到的结构」不等于「开局算法用的结构」**：forceEndScore 会让考试提前结束，
  但随机数已经在开局按完整配置消耗完了。凡是「先消耗随机数、再按条件提前结束」的地方都要留神。


---

### 3.3 本地 bench 超时退回贪心，把搜索的优势抹掉

**现象**：expectimax 本地评测 −22%。

**根因**：超时后整步退回 greedy，等于用规则跑完。

**修法**：改成 anytime（用当前最优动作继续），回到 +7%。

**教训**：基准测试的「兜底策略」会污染结论，要单独统计 fallback 率。

---

### 3.4 子智能体把产物写到 C 盘

**现象**：子智能体报告生成了 75MB 的 `dump.cs`，但我在 D 盘怎么都找不到。

**根因**：子智能体的 cwd 是 `C:\Users\...\deepseek-harness\default-workspace`，相对路径落在 C 盘。

**教训**：给子智能体的任务里**写绝对路径**；跨目录产物要求贴 `Get-Item` 输出。

---

## 四、工具与环境

| 问题 | 现象 | 修法 |
|---|---|---|
| 蓝奏云反爬 | 直链跳「网络异常需验证」 | 放弃自动下载，用户手动下 |
| pytest 临时目录 | Windows ACL 报错 | 必须带 `--basetemp=data/pytest-tmp-xxx` |
| PowerShell 引号 | 中文/引号组合导致 `unterminated string` | **写成 .py 文件再执行**，别用 `-c "..."` |
| `.venv` 被当模块 | `The module '.venv' could not be loaded` | 用 `& '.\\.venv\\Scripts\\python.exe'` 或先 cd 到项目根 |
| OCR 区域没对准 | 截屏 OCR 只出几个字 | 先截图确认 ROI，再调坐标 |
| 桌面截图截到别的窗口 | 全是浏览器 | 用 `PrintWindow` 抓指定窗口，或先 SetForegroundWindow |

---

## 五、还没解决的

| 问题 | 现状 |
|---|---|
| ~~考试时刻的「牌堆」字段在哪~~ | **已解决（11-21）**：`userProduceProgressProduceCardList`(309641228)。230550472 是图鉴、256246388 是支援卡，都不是牌堆。见 MASTER_DATA.md |
| seed + 牌堆 → 精确牌序 | 期中已破解（k=51，18/18）；期末异常未解（见 3.6） |
| bot 完整跑完一局 | 修了 4 个死循环，尚未端到端验证 |
| `StepAuditionEndExamBattle` 分数与评价用的「最終試験分数」差 618 | 实测 4798，反推评价需要 4180，字段映射未确认 |
| 52 条定制卡按基础卡处理 | 主数据已入库，可以查真实定义了 |
| 反作弊是否检测改 DLL | 未知，风险自担 |
