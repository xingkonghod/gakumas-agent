# Gakumas 双模式智能打牌与 MaaFramework 自动化 Demo (`demo/`)

本目录实现了一个保持根目录既有资产（`cards/`、`drinks/`、`reference/`、`gakumas_library.db`、`manifest.json`、`README.md`）**完全只读**的《学园偶像大师》（Gakumas）智能打牌与自动化演示系统。

## 目录结构

```text
demo/
├── app.py                   # CLI、Rich 三面板与 --mode ui 启动入口
├── web/                     # 参考 MFAAvalonia 结构的桌面风格 Web 前端与 HTTP/SSE API
├── schemas.py               # 跨模块数据契约 (ScreenObservation / LegalAction / DecisionResult)
├── requirements.txt         # 运行依赖清单
├── core/                    # 只读知识库查询、状态追踪、费用规则与紧凑 Prompt 构建 (<800 tokens)
├── vision/                  # 本地职业白名单图像识别、ROI/OCR 接口、Mock 合成帧生成器
├── agent/                   # OpenAI 兼容 LLM 客户端、三大流派 SYSTEM_PROMPT、零 Token 跳过与启发式兜底
├── maa_bridge/              # Base/Mock/ADB/Win32 控制器、pipeline.json、CustomRecognition/Action 与 Runner
└── tests/                   # 单元测试、集成测试与端到端闭环测试
```

## 快速运行

在工作区根目录 `c:\Users\josha\Desktop\gakumas` 下执行：

### 0. 启动 MFAAvalonia 风格前端控制台（推荐）

启动基于毛玻璃多实例布局的前端控制界面（含任务队列、实时视图与 BBox/点击准星叠加、多实例监视、只读卡牌图鉴与 ADB/LLM 设置）：

```bash
python demo/app.py --mode ui --ui-port 8765 --open-browser
```

启动后在浏览器访问 `http://127.0.0.1:8765/` 即可一键切换 `Mock 合成帧` / `ADB 模拟器` / `Win32 窗口` 模式。

### 1. Mock 演示模式（无需真机 / 无需 API Key）

自动基于 `cards/` 与 `drinks/` 合成培育日程、三选一加卡、战斗打牌与弹窗画面，并展示 3 个 Rich 实时面板：

```bash
python demo/app.py --mode mock --plan sense --steps 5
```

遍历感性 / 理性 / 异常全部三种职业：

```bash
python demo/app.py --mode mock --plan all --steps 4 --delay 0
```

### 2. 配置真实 LLM（可选）

程序支持任意 OpenAI 兼容接口（DeepSeek / Gemini / OpenAI / Ollama）。未设置 `LLM_API_KEY` 时会自动启用本地启发式规则兜底；仅有 1 个合法动作时自动零 Token 跳过。

```powershell
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_API_KEY  = "your-api-key"
$env:LLM_MODEL    = "gpt-4o-mini"
python demo/app.py --mode mock --plan logic --steps 5
```

### 3. ADB 实机 / Android 模拟器模式

连接位于 `192.168.0.115:5555` 的 Android 模拟器（支持 `root/114514` 与 `MaaFw` / ADB CLI 双通道）：

```bash
python demo/app.py --mode adb --host 192.168.0.115 --port 5555 --root-pwd root/114514 --plan sense --steps 5
```

若目标模拟器暂不可达且希望严格失败（不回退到 Mock 帧），可附加 `--no-fallback-to-mock`：

```bash
python demo/app.py --mode adb --host 192.168.0.115 --port 5555 --no-fallback-to-mock
```

### 4. Win32 桌面窗口模式

```bash
python demo/app.py --mode win32 --window-title "学园偶像大师" --plan sense --steps 5
```

## 运行全部测试

```bash
python -m pytest demo/tests/ -v
```
