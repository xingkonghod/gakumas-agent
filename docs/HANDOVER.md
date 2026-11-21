# 项目交接（2026-11-20 收尾）

> **导航看 [INDEX.md](INDEX.md)**（按任务列了该读哪些文档）。
> 本文只写：现状 + 下一步 + 路径速查 + 注意事项。

## 一、这个项目在做什么

让 AI 自动玩《学园偶像大师》的培育（produce）模式：
读屏幕 → 决策（出牌/选行动）→ 点击 → 复盘。

当前主线是**初（REGULAR/PRO）**模式，目标是逼近手打水平（A / 10,237）。

---

## 二、今天（11-20）完成了什么

### A. 真机数据采集彻底打通（最重要的基础设施）

```
游戏副本      C:\GakumasLocal（12.34GB，D 盘原版的完整复制，D 盘不动）
采集工具      C:\GakumasLocal\GakumasUnlock
一键启动      双击「一键采集启动.bat」
采集产物      C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl
提取考试结果  python scripts\extract_exams.py
文档          docs/CAPTURE_PIPELINE.md
```

**解决的四个坑**（详见文档）：
1. 客户端 rustls 不信任我们的证书 → hook 改走明文 h2c（18444）
2. grpc-dotnet 在明文 http 下降级 HTTP/1.1 → hook 强制 `http2_only` + 跳过证书校验
3. Firebase 走 libcurl 不用系统代理 → 启动脚本注入代理变量（仅 Firebase 域名）
4. 代理端口已关仍注入 → 启动前 TCP 探测，不通就**清除**变量（不能写空字符串）

**已采到的真实数据**：
| 考试 | 名次 | 分数 | 三维 | 操作数 |
|---|---:|---:|---|---:|
| 期中 | 3 | 569 | 413/87/69 | 10 |
| 期末 | 2 | 4798 | 3266/476/1056 | 17 |

整局：**B / 7404**，三维 1011/493/79。

### B. 模拟器与公式校准

```
src/gkagent/sim/hajime_eval.py    初评价公式（属性和×2.3 + 名次分 + 期末分分段折算）
src/gkagent/sim/hajime_data.py    验证过的常数（考试基础分 / 课程档位 / 收益公式）
```

**4 局实机逐分回归通过**（9973 / 10428 / 8790 / 12903），测试在 `tests/test_hajime_eval.py`。

### C. 主数据入库（游戏真实数据）

```
来源   vertesan/gakumasu-diff 提交 d31baf6
产物   data/hiro/vendor/gakumas-player/data/master/<commit>/catalog.sqlite
规模   286 表 / 163,974 行 / 476 卡 base / 1,817 卡变体（74MB）
```

已验证 `produce-001` 考试基础分：中間 600/封顶 900、最終 2450（与社区文档一致）。

### D. seed 在流量里（今天最大的发现）

```
UserProduceProgress.ExamSeedValueFieldNumber = 600
同一培育的三个响应里 seed 一致：
  StepAuditionStart / StepAuditionEndExamBattle / User/Get → 0x504C4509
```

配合客户端同款 RNG（xorshift32，见 hiro 的 `gakumas_exam/rng.py`）可以精确重放洗牌。
工具：`scripts/find_seed.py`、`scripts/verify_seed.py`。

### E. bot 的几个死循环修复

```
f6b99c0  外出事件屏识别（不再只靠「快进」按钮）
9bd3551  click_force 不再被「用户活跃」门限拦截自己；领卡选卡后等按钮点亮
7e58b4b  点击坐标按实际客户区缩放（窗口非 720x1280 时全部落空）
```

---

## 三、社区情报（他们做到哪了）

**hiro-gakumas-hero**（matto49，AGPL-3.0，28 star）：

```
H.I.F 本战夺冠 6 次（最高 130 万）；初 REGULAR 评价 A（10,428）
架构  识别层 / 战略层 / 操作层，层间只交换数据契约
特点  读不到就留空不猜；状态纯函数可重放；动作前预算下一帧做互验
规模  120 模块 / 600+ 测试
平台  Mac 成熟，Windows 还在追赶（DMM 版最好第 2）
```

**QQ 群「初星学园情报处理部」关键结论**：
- `uihorizon 和 uinet 都到头了`，`上了十倍的训练量指标反而倒退了`
- 他们在做 **seed 反推**（2^31-1 枚举 + 观测剪枝），并已逆出来，但**定下规矩实战不用**
- 他们用 **frida 注入**（需要管理员），有人卡在 `VirtualAllocEx 0x5`
- 没人提过 **MITM/抓包**——这是我们独有的路线

详见 `docs/QQ_GROUP_NOTES.md`、`docs/HIRO_VIDEO_NOTES.md`。

---

## 四、下一步（按优先级）

### ① 把「考试时刻的牌堆」字段挖出来（最高优先）

```
已知：seed 在流量里（field 600）
缺：  StepAuditionStart 响应里「当前牌堆」的字段位置
      响应 9,027 字节，里面只有 9 种卡（编成用），不是牌堆
方法： 用 data/reverse/out/dump.cs 里的字段名映射，逐层解析 StepAuditionStart 响应
完成标准：用 seed + 牌堆洗牌，结果与实战出牌序列能对上
```

**成功后**：seed + 牌堆 → 精确牌序 → 完全信息搜索（比他们的「反推」省一步）。

### ② bot 能无人值守跑完一局

```
现状：能跑到领卡/外出等界面，修了几个死循环，但还没跑完一整局
已知坑：窗口必须是 720x1280 客户区（现在窗口 540x960，代码已按比例缩放）
下一步：起 bot 跑一局验证，卡住就抓屏幕看是哪一屏
```

### ③ 三引擎真机 A/B（需要 ② 完成）

```
rules / expectimax(ensemble) / uinet
同偶像同卡组各一局，用 extract_exams.py 比真实考试分数
```

---

## 五、关键路径速查

```
游戏副本          C:\GakumasLocal
采集工具          C:\GakumasLocal\GakumasUnlock
一键启动          C:\GakumasLocal\GakumasUnlock\一键采集启动.bat
采集数据          C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl
主数据库          D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master
元数据 dump       D:\Games\gakumas-agent\data\reverse\out\dump.cs（75MB，勿读全文）
策略配置          D:\Games\gakumas-agent\data\knowledge\policy.json（lesson.engine）
当前引擎          rules
```

**常用命令**：
```powershell
# 提取考试结果
.venv\Scripts\python.exe scripts\extract_exams.py
# 挖 seed
.venv\Scripts\python.exe scripts\find_seed.py
# 跑 bot（需游戏停在培育设置界面）
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 340 ep-xxx --skip-home"
# 全量测试
.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=data/pytest-tmp-xxx
```

---

## 六、坑与注意事项

| 坑 | 说明 |
|---|---|
| 窗口尺寸 | bot 的坐标按 720x1280 设计，代码已按实际客户区缩放；但**窗口不能改大到超过屏幕**（1316 高会看不到底部）|
| 重启游戏后 token | `launch-args.json` 里的 onetime_token 会过期，从 DMM 启动一次即可刷新（一键脚本自动做）|
| VPN | 必须日本节点；TUN 和 7897 任一生效即可，两个都关会「初始化失败」|
| 守护进程 | `GDEAgent` 计划任务偶尔卡住，`schtasks /End` 再 `/Run` 重启 |
| 不要碰 D 盘原版 | `D:\Games\Gakumas\gakumas` 是用户正在用的客户端 |
| 采集必须关 unlock | `GKM_UNLOCK=0 / GKM_FORGE=0 / GKM_STATIC_USER=0`，否则污染账号数据 |
| 读 memory 不可行 | 游戏进程有反作弊，管理员 ReadProcessMemory 也被拒（实测 err=5）|
| AGPL 代码 | `data/hiro/` 是 AGPL-3.0，**只做参考/对照，不要拷进本项目** |

---

## 七、今天的提交记录

```
436b6a8 docs(master): 记录 seed 在流量里的发现与待验证项
02c20f2 feat(seed): seed 提取 + xorshift32 重放工具
7230370 docs(master): 主数据库构建（286 表）
8583ace feat(policy): PERFECT 线改用验证档位
d7db974 feat(sim): 初模式验证数值模块
ebabcd4 docs: hiro 视频要点
7bb05e2 feat(sim): 初评价公式 + 4 局实机回归
c9c2751 docs: QQ 群讨论记录
7e58b4b fix(click): 点击坐标按实际客户区缩放
9bd3551 fix(click): click_force 不再被用户门限拦截
f6b99c0 fix(produce): 外出事件识别 + 领卡坐标
eb59057 docs(capture): 采集链路文档
8b6dc49 docs(runs): 首次完整采集局
b80cc05 feat(ground-truth): extract_exams 工具
add71dc docs(reverse): 元数据解包验证
```

**测试状态**：`pytest tests/ -q` 全绿（773+ 条），`ruff check` 通过。
