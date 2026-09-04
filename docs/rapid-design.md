# Rapid Design 技术说明

## 目标与边界

Rapid Design 是 AeroSpec 之上的独立概念设计入口，当前明确分成两个模式：

- **Analyze / `bwb_v1`**：直接调整 12 个翼身融合（BWB）几何参数及飞行工况，约 200 ms 防抖后更新连续三维外形、派生几何量和整机纵向极曲线。
- **Optimize / conventional**：保留原有常规固定翼任务优化，根据航程、载荷、速度和质量约束搜索可行方案。它尚未迁移到 BWB 参数族。

当前版本用于概念探索与方案比较，不是认证级、适航级或制造级分析。它不替代 CFD、结构有限元、稳定性/操稳、推进系统匹配或试验验证。

## BWB Analyze 输入与输出

`bwb_v1` 的输入向量包括中心弦长，三段弦长比与展向长度比，外段后移量，内/外翼后掠角，相对厚度和翼尖扭转。飞行工况包括高度、真空速和迎角扫描区间。API 对输入范围以及 `c2 > c3 > c4` 的最小间隔进行严格校验。

同一组输入通过版本化的 `clean-room-bwb-loft/1.0.0` 解码器生成光顺 Hermite 平面形与闭合三维 loft。前端网格和后端面积、平均气动弦、湿面积、容积代理量共享相同曲线及固定 Gauss 积分定义；模型与解码器版本同时进入 `design_hash`，避免数值与图形静默漂移。

Analyze 返回：设计身份、模型适用域检查、几何量、`CL/CD/L/D` 迎角曲线、采样区间内最大 L/D、警告和来源信息。当前 `clean-room-bwb-low-order/1.0.0` 是本项目独立编写的确定性低阶整机比较模型，不是从 MIT demo 复制的模型，也没有使用其数据、权重、源码或 nTop 文件。

派生适用域目前检查 `2 ≤ AR ≤ 12`、`0.05 ≤ Mach ≤ 0.55`、`5×10⁴ ≤ Re ≤ 10⁸`。超域时仍返回结果供探索，但状态为 `out_of_domain`，并附警告；结果只能用于概念级趋势比较。

## Conventional Optimize 输入与输出

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

### Conventional Optimize

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
| POST | `/api/rapid-design/analyze` | 即时分析一个 `bwb_v1` 几何与工况 |
| GET | `/api/rapid-design/config` | 读取输入和变量范围 |
| POST | `/api/rapid-design/jobs` | 创建异步优化任务 |
| GET | `/api/rapid-design/jobs/{id}` | 查询状态 |
| GET | `/api/rapid-design/jobs/{id}/events` | SSE 进度事件 |
| GET | `/api/rapid-design/jobs/{id}/result` | 读取结果 |
| POST | `/api/rapid-design/jobs/{id}/cancel` | 请求停止 |

每个任务写入 `storage/rapid_design/jobs/{job_id}/request.json`、`config.json`、`status.json` 和成功后的 `result.json`。`storage/` 已被 Git 忽略，不会污染源码提交。

## 本地启动

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

进入页面后默认打开 Analyze。修改滑块或数值框会自动分析；“设为 Baseline”可冻结当前方案，用灰色轮廓和灰色曲线对照后续参数变化。Optimize 标签页仍是常规固定翼旧流程，两类结果不会混用。

## 测试

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest -q tests/api/test_rapid_design.py
.\.venv\Scripts\python.exe -m pytest -q tests/api/test_bwb_analyze.py
Set-Location apps/web
npm test
npm run build
```

上游完整 Python 测试在 Windows 需要 `PYTHONUTF8=1`；另有一个既有测试把输出路径硬编码为 `/tmp`，只能在类 Unix 环境直接通过。
