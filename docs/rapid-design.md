# Rapid Design 技术说明

## 目标与边界

Rapid Design 是 AeroSpec 之上的独立任务驱动入口。它解决的是：给定一组可调整的任务需求和上限，搜索一套满足约束的固定翼无人机概念参数，并马上显示数值结果与 3D 几何。

当前版本用于概念探索与方案比较，不是认证级、适航级或制造级分析。它不替代 CFD、结构有限元、稳定性/操稳、推进系统匹配或试验验证。

## 输入、设计变量与输出

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

优化器决定机翼面积、展弦比、梢根比、后掠角、机身长/直径、NACA 四位数风格的弯度/位置/厚度参数，以及实际装油量。所有默认范围位于 `configs/rapid_design/demo.yaml`，因此新增输入或修改边界不需要改前端布局。

每次运行返回：设计变量、质量分解、气动/航程指标、逐项约束余量、收敛历史、代理模型来源、警告和可供 AeroSpec 预览的 `AircraftSpec`。

## 计算链路

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

## 测试

```powershell
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest -q tests/api/test_rapid_design.py
Set-Location apps/web
npm test
npm run build
```

上游完整 Python 测试在 Windows 需要 `PYTHONUTF8=1`；另有一个既有测试把输出路径硬编码为 `/tmp`，只能在类 Unix 环境直接通过。
