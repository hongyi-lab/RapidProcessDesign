# Rapid Design 技术说明

## 目标与边界

Rapid Design 是 AeroSpec 之上的 family-neutral 整机概念设计入口，当前分成三个明确隔离的模式：

- **Analyze**：同一页面切换 `conventional_v2` 与 `bwb_v1`。family manifest 提供 preset、参数范围和能力；约 220 ms 防抖后返回统一 `GeometryState`、派生几何量和概念级纵向极曲线。
- **Mission Design**：包含可运行的 `Demo Search` 与保持阻断的 `Formal Optimization`。Demo 使用独立版本化 profile 对用户选定的 `conventional_v2` preset 做确定性候选搜索；正式目标、变量、约束、surrogate 与算法仍为 `optimization_spec_pending`。
- **Legacy Conventional Demo**：保留原有任务优化与回归能力，但它不读取或优化 Analyze 当前选中的飞机。

当前版本用于概念探索与方案比较，不是认证级、适航级或制造级分析。它不替代 CFD、结构有限元、稳定性/操稳、推进系统匹配或试验验证。

## Family Registry 与统一 GeometryState

`GET /api/rapid-design/families` 返回两个 family 的 manifest。高层设计参数由各 family decoder 展开成 Canonical `GeometryState`；通用 renderer 只消费 `loft_body`、`lifting_surface`、`nacelle` 和 `propeller` 等 canonical component，不认识 `BwbV1Design` 或 `ConventionalV2Design`。

```text
family + preset + design parameters
              ↓
       family geometry decoder
              ↓
        Canonical GeometryState
        ├── generic Three.js renderer
        ├── family analysis adapter
        └── future exporter / optimizer
```

`AircraftSpec` 和旧 `geometry_mapper.py` 继续服务于 legacy pipeline，不再是新高质量预览的几何真相。

## BWB V1 输入与输出

`bwb_v1` 的输入向量包括中心弦长，三段弦长比与展向长度比，外段后移量，内/外翼后掠角，相对厚度和翼尖扭转。飞行工况包括高度、真空速和迎角扫描区间。API 对输入范围以及 `c2 > c3 > c4` 的最小间隔进行严格校验。

同一组输入通过版本化的 `clean-room-bwb-loft/1.0.0` 解码器生成光顺 Hermite 平面形与闭合三维 loft。前端网格和后端面积、平均气动弦、湿面积、容积代理量共享相同曲线及固定 Gauss 积分定义；模型与解码器版本同时进入 `design_hash`，避免数值与图形静默漂移。

Analyze 返回：设计身份、模型适用域检查、几何量、`CL/CD/L/D` 迎角曲线、采样区间内最大 L/D、警告和来源信息。当前 `clean-room-bwb-low-order/1.0.0` 是本项目独立编写的确定性低阶整机比较模型，不是从 MIT demo 复制的模型，也没有使用其数据、权重、源码或 nTop 文件。

派生适用域目前检查 `2 ≤ AR ≤ 12`、`0.05 ≤ Mach ≤ 0.55`、`5×10⁴ ≤ Re ≤ 10⁸`。超域时仍返回结果供探索，但状态为 `out_of_domain`，并附警告；结果只能用于概念级趋势比较。

## Conventional V2 输入与输出

`conventional_v2` 提供三个合法的几何起点：`long_endurance_uav`、`fast_cruise_recon` 与 `payload_utility`。它们分别采用修长高展弦比/后推、尖细后掠/机头牵引、饱满高翼/双翼下短舱语法，不代表优化结论。

高层滑块由 decoder 展开成 9 个机身截面、4 个主翼半展向 section、三段平尾、三段垂尾及 preset-defined nacelle。分析 adapter 使用透明的概念级有限翼和阻力关系，只用于交互趋势比较，不声称经过 CFD、VSPAERO 或试验验证。

## Mission Demo Search 输入与输出

Mission Demo v1 固定用户当前选择的一个 `conventional_v2` preset，不跨 family 挑选“最优构型”。用户输入目标航程、载荷、巡航速度/高度、最大燃油、最大起飞质量和目标 L/D；独立的 `mission_demo_v1` profile 决定临时演示边界、固定 seed、24 次评价预算、质量/航程系数和惩罚权重。

搜索变量是 8 个原生 `ConventionalV2Design` 几何字段（机身长度与细长比、翼展、翼面积、后掠、梢根比、厚度比、尾翼尺度）和独立 fuel sizing。每一次评价都调用当前 family registry 的 Analyze，先得到同一候选的 Canonical `GeometryState`、几何指标、极曲线摘要和 `design_hash`，再通过透明的 Demo 质量构建与 Breguet 风格关系计算任务指标。

结果按“可行优先 → Demo objective → 稳定 candidate hash”排序，并仅按 8 个几何变量的归一化距离筛选三个外形不同的候选。无可行点时仍返回最小违约候选，不把失败静默包装成可行。每个候选携带完整原生设计、fuel sizing、工况、评分分解、逐项约束、Analyze 摘要、精确 `GeometryState`、`design_hash`、domain 状态、warnings 与 provenance；点击候选会以同一设计和工况重新进入 Analyze。

指标覆盖按 `connected`、`partial`、`not_connected` 显式公开。尾翼配平/操稳、推进匹配、结构、起降与噪声等未接入项不进入 Demo score；当前尾翼湿面积、低阶整机极曲线等只标为部分接入。Demo profile、API、存储与 Legacy/Formal 完全隔离，所有页面和结果均标注 `DEMO / NOT FORMAL / UNAPPROVED ASSUMPTIONS`。

## Legacy Conventional Demo 输入与输出

用户输入定义“要什么”和“不能超过什么”：

| 输入 | 类型 | 默认范围 |
|---|---|---:|
| 目标航程 | 需求 | 300–3000 km |
| 有效载荷 | 需求 | 20–300 kg |
| 巡航速度 | 需求 | 100–320 km/h |
| 巡航高度 | 需求 | 500–9000 m |
| 最大燃油质量 | 约束 | 50–900 kg |
| 最大起飞质量 | 约束 | 300–2500 kg |
| 目标 L/D | 约束 | 8–24 |

优化器决定机翼面积、展弦比、梢根比、后掠角、机身长/直径、NACA 四位数风格的弯度/位置/厚度参数，以及实际装油量。常规构型优化的默认范围位于 `configs/rapid_design/demo.yaml`。

每次运行返回：设计变量、质量分解、气动/航程指标、逐项约束余量、收敛历史、代理模型来源、警告和可供 AeroSpec 预览的 `AircraftSpec`。

## 计算链路

### Mission Demo Search

```text
选定 conventional_v2 preset + Demo 任务输入
    ↓ 独立 profile 校验与固定 seed
24 次原生几何 + fuel sizing 采样
    ↓ 每个点调用当前 registry Analyze
Canonical GeometryState + 概念极曲线 + design_hash
    ↓ 透明 Demo 质量构建 + Breguet 风格航程
可行性、约束违约与 Demo objective
    ↓ feasible-first 排序 + 仅几何变量多样性筛选
Top 3 候选 → 共享尺度预览 → 精确交给 Analyze 复核
```

### BWB Analyze

```text
12 个 BWB 几何参数 + 飞行工况
    ↓ 输入关系与范围校验
版本化光顺几何解码器 ── 连续闭合 3D loft + 几何积分量
    ↓
ISA 大气 + 有限翼升力斜率 + 摩阻/诱导阻力/经验分离修正
    ↓
整机 CL / CD / L/D 迎角曲线
    ↓
模型域检查 + provenance + 可复现 design_hash
```

### Legacy Conventional Demo

```text
可调任务输入
    ↓ 范围校验
差分进化优化器 ── 调整 10 个设计变量
    ↓
ISA 大气 + 质量构建
    ↓
NeuralFoil 公开代理模型 ── 翼型 CL / CD / CM / confidence
    ↓
有限翼与机身低阶修正 + Breguet 风格航程
    ↓
航程 / L/D / MTOW / 燃油 / 升力 / 模型置信度约束
    ↓
最优可行点（或明确标记的最小违约点）
    ↓
JSON 结果 + AeroSpec 3D 参数预览
```

### 气动

NeuralFoil 在给定翼型坐标、迎角和雷诺数下预测二维 `CL`、`CD`、`CM` 及 `analysis_confidence`。当前配置使用 `medium` 网络以平衡交互速度和精度。整机阻力由翼型剖面阻力、有限翼诱导阻力、机身寄生阻力和小后掠修正组成：

```text
CD_total = CD_NeuralFoil + CL² / (π AR e) + CD_body + CD_sweep
```

NeuralFoil 论文和源码分别位于 <https://arxiv.org/abs/2503.16323> 与 <https://github.com/peterdsharpe/NeuralFoil>。

### 质量与航程

空机质量采用可配置的部件构建：机翼面积/翼展项、机身湿表面积项、系统基础质量、载荷相关系统质量、推进质量和起落架比例。系数集中在 YAML 中，便于换成真实历史数据后的校准。

航程采用带储备燃油比例的 Breguet 风格关系：

```text
R = V / c × (L/D) × ln(m_takeoff / m_final)
```

`c` 是概念级等效耗油率，不代表某一台具体发动机。任何工程使用都应先用目标推进系统数据校准。

## API 与持久化

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/rapid-design/families` | 发现所有 family、preset、参数和能力 |
| GET | `/api/rapid-design/families/{family_id}` | 读取一个完整 family manifest |
| POST | `/api/rapid-design/analyze` | 按 `family_id` 分发并返回统一分析 envelope |
| GET | `/api/rapid-design/config` | 读取输入和变量范围 |
| POST | `/api/rapid-design/jobs` | 创建异步优化任务 |
| GET | `/api/rapid-design/jobs/{id}` | 查询状态 |
| GET | `/api/rapid-design/jobs/{id}/events` | SSE 进度事件 |
| GET | `/api/rapid-design/jobs/{id}/result` | 读取结果 |
| POST | `/api/rapid-design/jobs/{id}/cancel` | 请求停止 |
| GET | `/api/rapid-design/demo/config` | 读取版本化、非正式 Mission Demo profile |
| POST | `/api/rapid-design/demo/jobs` | 为固定 conventional preset 创建 Demo 搜索任务 |
| GET | `/api/rapid-design/demo/jobs/{id}` | 查询 Demo 状态与评价进度 |
| GET | `/api/rapid-design/demo/jobs/{id}/events` | 读取 Demo SSE 事件 |
| GET | `/api/rapid-design/demo/jobs/{id}/result` | 读取 Top 3、覆盖声明与搜索证据 |
| POST | `/api/rapid-design/demo/jobs/{id}/cancel` | 协作式停止 Demo 搜索 |

Legacy 任务写入 `storage/rapid_design/jobs/{job_id}/`；Mission Demo 独立写入 `storage/rapid_design/demo_jobs/{job_id}/request.json`、`profile.json`、`status.json` 和成功后的 `result.json`。写入采用临时文件替换，便于保留可追溯证据。当前 runner 不在 API 重启后恢复内存任务索引，因此历史文件会保留，但重启前的 job ID 不能继续通过状态 API 查询。`storage/` 已被 Git 忽略，不会污染源码提交。

## 本地启动

### Windows 一键启动（推荐）

在仓库根目录双击 `Start-RapidDesign.cmd`。启动器会自动检查本地构建：代码没有变化时直接启动；首次运行或前端源码更新后自动重新构建。页面准备完成后会在默认浏览器打开：

<http://localhost:3900/rapid-design>

使用结束后双击 `Stop-RapidDesign.cmd`。运行日志保存在被 Git 忽略的 `.rapid-local/` 中。这个方式仍然是在本机运行，但不需要手动打开两个终端或记忆启动命令。

### 手动启动（开发者）

PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:CAD_BACKEND="fake"
.\.venv\Scripts\python.exe -m uvicorn services.api.app.main:app --port 8900
```

另开一个 PowerShell：

```powershell
Set-Location apps/web
npm ci
npm run dev
```

访问 <http://localhost:3900/rapid-design>。

进入页面后默认打开 Analyze 和 `conventional_v2`。可直接切换三个 conventional preset 或 `bwb_v1`；修改滑块会自动分析，“设为 Baseline”可冻结当前方案并叠加比较。Mission Design 中可对当前 conventional preset 运行 Demo Search、比较 Top 3 并送回 Analyze；BWB 会明确显示未接入。Formal Optimization 仍保持阻断，原有流程继续位于 Legacy Conventional Demo。

## 测试

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest -q tests/api/test_rapid_design.py
.\.venv\Scripts\python.exe -m pytest -q tests/api/test_rapid_design_demo.py
.\.venv\Scripts\python.exe -m pytest -q tests/api/test_bwb_analyze.py
Set-Location apps/web
npm test
npm run build
```

上游完整 Python 测试在 Windows 需要 `PYTHONUTF8=1`；另有一个既有测试把输出路径硬编码为 `/tmp`，只能在类 Unix 环境直接通过。
