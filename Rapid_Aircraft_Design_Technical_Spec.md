# Rapid Aircraft Design Demo：技术规格

**对应总体计划：** V0.1  
**用途：** 作为开发时的接口合同与验收依据。  
**原则：** 优先完成 end-to-end vertical slice；任何高级能力都不得阻塞 V0。

---

## 1. 推荐技术栈

### Frontend

- Next.js
- React
- TypeScript
- 复用 AeroSpec Agent 的 Three.js / GLB viewer
- 使用 SSE 接收运行进度

### Backend

- Python 3.11
- FastAPI
- Pydantic
- PyYAML
- NumPy
- SciPy
- 复用 AeroSpec Agent 的 job/event/storage 结构

### Geometry

优先级：

1. 现有 parameter-driven Three.js preview
2. `trimesh` 生成简单 mesh / GLB
3. Optional OpenVSP backend

### Optimization

V0：

- `scipy.optimize.differential_evolution`
- optional SLSQP polishing
- penalty-based handling for generic black-box constraints

未来：

- AeroSandbox / CasADi / IPOPT
- OpenMDAO driver
- multi-objective solver

---

## 2. 推荐新增目录

在 AeroSpec Agent fork 中新增：

```text
apps/web/src/app/rapid-design/
└── page.tsx

apps/web/src/components/rapid-design/
├── MissionForm.tsx
├── OptimizationProgress.tsx
├── ResultSummary.tsx
├── ConstraintTable.tsx
├── DesignVariableTable.tsx
├── ConvergenceChart.tsx
├── ModelProvenance.tsx
└── RapidDesignWorkspace.tsx

services/api/app/routers/
└── rapid_design.py

services/api/app/schemas/
└── rapid_design.py

services/api/app/services/rapid_design/
├── config_loader.py
├── model_adapter.py
├── model_registry.py
├── evaluator.py
├── optimizer.py
├── geometry_mapper.py
├── result_store.py
└── job_runner.py

configs/rapid_design/
├── demo.yaml
└── local_models.yaml

services/api/app/services/rapid_design/models/
├── demo_aero.py
├── demo_structure.py
└── demo_mission.py

tests/api/
├── test_rapid_design_config.py
├── test_rapid_design_adapter.py
├── test_rapid_design_optimizer.py
├── test_rapid_design_api.py
└── test_rapid_design_e2e.py

THIRD_PARTY_MODELS.md
```

不要在 V0 中重构整个上游仓库。新增功能与原功能尽量隔离。

---

## 3. 核心数据对象

## 3.1 MissionRequirements

```python
from pydantic import BaseModel, Field


class MissionRequirements(BaseModel):
    payload_kg: float = Field(gt=0)
    required_range_m: float = Field(gt=0)
    cruise_speed_mps: float = Field(gt=0)
    cruise_altitude_m: float = Field(ge=0)
    required_endurance_s: float | None = Field(default=None, gt=0)
    max_takeoff_distance_m: float | None = Field(default=None, gt=0)
```

实际字段由老师确认；schema 可允许 optional fields，但名称和单位一旦确定必须稳定。

## 3.2 DesignVariableDefinition

```python
from typing import Literal
from pydantic import BaseModel


class DesignVariableDefinition(BaseModel):
    name: str
    label: str
    unit: str | None = None
    lower: float
    upper: float
    initial: float | None = None
    transform: Literal["linear", "log"] = "linear"
```

前端不硬编码 design variables，而是从 `/config` 动态读取。

## 3.3 ConstraintDefinition

```python
class ConstraintDefinition(BaseModel):
    name: str
    label: str
    output: str
    operator: Literal[">=", "<="]
    target: float | None = None
    target_from: str | None = None
    unit: str | None = None
    scale: float | None = None
```

`target` 与 `target_from` 二选一。

## 3.4 RunStatus

```python
RunStatus = Literal[
    "queued",
    "loading_models",
    "optimizing",
    "generating_geometry",
    "completed",
    "no_feasible_solution_found",
    "failed",
    "cancelled",
]
```

---

## 4. 配置文件规范

示例：

```yaml
schema_version: "0.1"
project_name: rapid-aircraft-design-demo

mission_fields:
  - name: payload_kg
    label: Payload
    unit: kg
    default: 1000.0
    lower: 1.0
    upper: 100000.0

  - name: required_range_m
    label: Required range
    display_unit: km
    unit: m
    default: 1000000.0
    lower: 1000.0
    upper: 20000000.0

variables:
  - name: wing_area_m2
    label: Wing area
    unit: m^2
    lower: 10.0
    upper: 40.0
    initial: 22.0

  - name: aspect_ratio
    label: Aspect ratio
    unit: null
    lower: 6.0
    upper: 16.0
    initial: 10.0

  - name: taper_ratio
    label: Taper ratio
    unit: null
    lower: 0.25
    upper: 1.0
    initial: 0.55

  - name: wing_sweep_deg
    label: Wing sweep
    unit: deg
    lower: 0.0
    upper: 35.0
    initial: 8.0

models:
  aero:
    adapter: python_callable
    entrypoint: services.api.app.services.rapid_design.models.demo_aero:predict
    version: demo-0.1
    source: internal-demo
    license: internal-demo-only
    inputs:
      - wing_area_m2
      - aspect_ratio
      - taper_ratio
      - wing_sweep_deg
      - cruise_speed_mps
      - cruise_altitude_m
    outputs:
      - cl_cruise
      - cd_cruise
      - cm_cruise
    load_at_startup: true

  structure:
    adapter: python_callable
    entrypoint: services.api.app.services.rapid_design.models.demo_structure:predict
    version: demo-0.1
    source: internal-demo
    license: internal-demo-only
    inputs:
      - wing_area_m2
      - aspect_ratio
      - payload_kg
    outputs:
      - wing_mass_kg
      - max_stress_pa
      - payload_volume_m3
      - fuel_volume_capacity_m3
    load_at_startup: true

objective:
  output: mtow_kg
  sense: min
  scale: 10000.0

constraints:
  - name: range_requirement
    label: Required range
    output: achieved_range_m
    operator: ">="
    target_from: mission.required_range_m
    unit: m
    scale: 1000000.0

  - name: stress_limit
    label: Structural stress limit
    output: max_stress_pa
    operator: "<="
    target: 250000000.0
    unit: Pa
    scale: 250000000.0

optimizer:
  method: differential_evolution
  seed: 42
  max_iterations: 15
  population_size: 6
  polish: true
  penalty_weight: 1000.0
  progress_every_evaluations: 5

geometry:
  layout: conventional
  mapper: conventional_tube_and_wing
  default_fuselage_length_m: 12.0
  default_fuselage_diameter_m: 1.6
  default_tail_type: conventional
  backend: preview

uncertainty:
  enabled: false
  method: null
```

这些 bounds 和目标均为占位示例，不代表最终飞机设计要求。

---

## 5. Surrogate Adapter 合同

## 5.1 Python interface

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    version: str
    source: str
    license: str | None
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    model_hash: str | None = None


class SurrogateAdapter(Protocol):
    @property
    def metadata(self) -> ModelMetadata:
        ...

    def load(self) -> None:
        ...

    def predict(self, inputs: dict[str, float]) -> dict[str, float]:
        ...
```

## 5.2 Adapter 的责任

adapter 必须负责：

- 模型加载
- input name mapping
- input order
- normalization
- unit conversion
- tensor / NumPy conversion
- device selection
- model inference
- output name mapping
- finite-value validation

optimizer 不得知道模型是 PyTorch、sklearn、ONNX 还是普通 Python 函数。

## 5.3 V0 支持策略

第一版只必须实现：

```text
python_callable
```

即每个真实 borrowed model 写一个很薄的 wrapper：

```python
def predict(inputs: dict[str, float]) -> dict[str, float]:
    ...
```

等实际模型格式确定后，再增加：

- `joblib_adapter`
- `torch_adapter`
- `onnx_adapter`

不要在尚不知道模型格式时提前写一堆未使用 adapter。

## 5.4 Model manifest

每个 borrowed model 都必须有 manifest：

```yaml
name: example_aero_surrogate
version: "2026-08-15"
source_repository: "..."
source_paper: "..."
license: "..."
weights_path: "models/example/model.pt"
sha256: "..."
input_order:
  - wing_area_m2
  - aspect_ratio
  - mach
normalization:
  wing_area_m2:
    mean: 20.0
    std: 5.0
valid_ranges:
  wing_area_m2: [10.0, 40.0]
  aspect_ratio: [6.0, 16.0]
outputs:
  - cl
  - cd
  - cm
notes: "..."
```

V0 可只做 hard range warning，不做 uncertainty score。

---

## 6. SystemEvaluator

`SystemEvaluator` 是整个 pipeline 最重要的中间层。

```python
class SystemEvaluator:
    def evaluate(
        self,
        design: dict[str, float],
        mission: MissionRequirements,
    ) -> EvaluationResult:
        ...
```

推荐流程：

```text
1. merge design variables + mission inputs
2. derive shared geometry quantities
3. call aero adapter
4. call structure/weight adapter
5. call mission/propulsion adapter
6. compute remaining derived outputs
7. compute raw objective
8. compute standardized constraint margins
9. validate all values
10. return one EvaluationResult
```

### EvaluationResult

```python
class EvaluationResult(BaseModel):
    design: dict[str, float]
    model_outputs: dict[str, float]
    derived_outputs: dict[str, float]
    objective_raw: float
    objective_minimization_form: float
    constraint_margins: dict[str, float]
    feasible: bool
    warnings: list[str]
    uncertainty: dict
    model_versions: dict[str, str]
```

### 强耦合问题

V0 最好选取可以按顺序计算的模型组合。若出现：

```text
weight depends on fuel
fuel depends on mission
mission depends on weight
```

优先解决顺序：

1. 如果 borrowed model 已将这部分整体封装，直接调用整体模型。
2. 否则增加一个有上限的 fixed-point loop。
3. 若仍不收敛，返回 failed evaluation 和 penalty。
4. 不要在 V0 一开始引入完整 OpenMDAO nonlinear solver。

---

## 7. Objective 与 constraints

### 7.1 统一 minimization form

```python
if sense == "min":
    objective_min = objective_raw
else:
    objective_min = -objective_raw
```

### 7.2 统一 margin

```python
def constraint_margin(actual: float, operator: str, target: float) -> float:
    if operator == ">=":
        return actual - target
    if operator == "<=":
        return target - actual
    raise ValueError(f"Unsupported operator: {operator}")
```

### 7.3 Penalty objective

```text
J_penalized
=
J_normalized
+
rho × sum(max(0, -margin_i / scale_i)^2)
```

保存并展示 raw objective 与 raw margins，penalized objective 只用于 optimizer 内部。

### 7.4 Candidate failure

以下情况 candidate 判定为 invalid：

- model exception
- missing output
- NaN / Inf
- complex value
- shape mismatch
- denominator near zero
- fixed-point not converged

invalid candidate 返回大 penalty，并记录原因；不能让整个 optimization job 因一次 candidate 失败而终止。

---

## 8. Optimizer interface

```python
class OptimizationEngine:
    def run(
        self,
        mission: MissionRequirements,
        config: RapidDesignConfig,
        evaluator: SystemEvaluator,
        progress_callback,
        cancel_check,
    ) -> OptimizationResult:
        ...
```

### OptimizationResult

```python
class OptimizationResult(BaseModel):
    status: str
    best_design: dict[str, float]
    best_evaluation: EvaluationResult
    best_feasible_design: dict[str, float] | None
    best_feasible_evaluation: EvaluationResult | None
    evaluations: int
    iterations: int
    runtime_s: float
    seed: int
    convergence: list[dict]
    failure_counts: dict[str, int]
```

### 进度

进度不能只由墙钟时间估计。至少包含：

- iteration / max_iterations
- evaluation count
- current best penalized objective
- current best feasible objective
- feasible candidate count
- current stage

---

## 9. API 规范

## 9.1 获取页面配置

```http
GET /api/rapid-design/config
```

Response：

```json
{
  "schema_version": "0.1",
  "mission_fields": [],
  "variables": [],
  "objective": {},
  "constraints": [],
  "optimizer_summary": {},
  "models": [
    {
      "name": "aero",
      "version": "demo-0.1",
      "status": "ready"
    }
  ]
}
```

## 9.2 创建 job

```http
POST /api/rapid-design/jobs
Content-Type: application/json
```

Request：

```json
{
  "mission": {
    "payload_kg": 1000.0,
    "required_range_m": 1000000.0,
    "cruise_speed_mps": 120.0,
    "cruise_altitude_m": 8000.0
  },
  "config_name": "demo",
  "seed_override": null
}
```

Response：

```json
{
  "job_id": "rd-20260903-001",
  "status": "queued",
  "events_url": "/api/rapid-design/jobs/rd-20260903-001/events",
  "result_url": "/api/rapid-design/jobs/rd-20260903-001/result"
}
```

## 9.3 SSE events

```http
GET /api/rapid-design/jobs/{job_id}/events
Accept: text/event-stream
```

示例：

```text
event: job_started
data: {"job_id":"rd-001","stage":"loading_models","progress":0.02}

event: optimization_progress
data: {
  "iteration":4,
  "max_iterations":15,
  "evaluations":126,
  "best_objective":8420.1,
  "best_feasible_objective":8612.4,
  "feasible_count":18,
  "progress":0.31
}

event: geometry_started
data: {"progress":0.92}

event: job_completed
data: {"progress":1.0,"result_url":"/api/rapid-design/jobs/rd-001/result"}
```

SSE 断开后应允许前端重新连接；已完成 job 应能 replay 最终状态。

## 9.4 获取结果

```http
GET /api/rapid-design/jobs/{job_id}/result
```

结果至少包含：

```json
{
  "job_id": "rd-001",
  "status": "completed",
  "message": "Best feasible design found under current configuration.",
  "mission": {},
  "best_design": {},
  "objective": {
    "name": "mtow_kg",
    "value": 8612.4,
    "sense": "min"
  },
  "constraints": [
    {
      "name": "range_requirement",
      "actual": 1030000.0,
      "target": 1000000.0,
      "operator": ">=",
      "margin": 30000.0,
      "feasible": true
    }
  ],
  "model_outputs": {},
  "derived_outputs": {},
  "geometry": {
    "aircraft_spec": {},
    "glb_url": null,
    "backend": "preview"
  },
  "optimization": {
    "runtime_s": 12.8,
    "evaluations": 405,
    "iterations": 15,
    "seed": 42,
    "convergence": []
  },
  "provenance": {
    "config_hash": "...",
    "code_commit": "...",
    "models": {}
  },
  "uncertainty": {
    "status": "not_implemented",
    "method": null,
    "lower": null,
    "upper": null
  },
  "warnings": []
}
```

## 9.5 Cancel

可选但建议：

```http
POST /api/rapid-design/jobs/{job_id}/cancel
```

optimizer 每隔若干 evaluations 检查 cancel flag。

---

## 10. GeometryMapper

### 输入

- best design variables
- derived geometry values
- mission information
- geometry config

### 输出

- AeroSpec `AircraftSpec`
- list of defaulted/derived fields

### 常规机翼映射

```python
span_m = (aspect_ratio * wing_area_m2) ** 0.5
root_chord_m = 2 * wing_area_m2 / (span_m * (1 + taper_ratio))
tip_chord_m = taper_ratio * root_chord_m
```

### 设计要求

- 所有几何量必须 finite 且大于零
- 映射失败时仍返回数值结果，但 geometry status 为 failed
- geometry failure 不应删除已完成的 optimization result
- V0 默认只生成 conventional layout
- frontend preview 应在没有 GLB 时用 `AircraftSpec` fallback

---

## 11. 前端页面规格

```text
┌────────────────────────────────────────────────────────────┐
│ Rapid Aircraft Design                                      │
├────────────────┬─────────────────────────┬─────────────────┤
│ Mission Input  │ Interactive 3D Aircraft │ Best Result     │
│                │                         │ Objective       │
│ [payload]      │                         │ Feasible?       │
│ [range]        │                         │ Runtime         │
│ [speed]        │                         │ Model versions  │
│ [altitude]     │                         │                 │
│                │                         │                 │
│ [Run] [Cancel] │                         │                 │
├────────────────┴─────────────────────────┴─────────────────┤
│ Progress / convergence chart                               │
├─────────────────────────────┬──────────────────────────────┤
│ Design variables            │ Constraints and margins      │
├─────────────────────────────┴──────────────────────────────┤
│ Warnings · UQ not evaluated · export JSON / MD             │
└────────────────────────────────────────────────────────────┘
```

### UI 状态

- idle
- validating
- queued
- loading_models
- optimizing
- generating_geometry
- completed
- infeasible
- failed
- cancelled

### 语言

第一版英文参数名可保留，但所有错误必须是可理解的信息，不展示 Python stack trace 给普通用户。

---

## 12. 运行数据与可复现性

每个 job 保存：

```text
storage/rapid_design/{job_id}/
├── request.json
├── resolved_config.yaml
├── config_hash.txt
├── model_manifest.json
├── status.json
├── convergence.json
├── result.json
├── aircraft_spec.json
├── aircraft.glb
└── run.log
```

`aircraft.glb` 只有在对应 backend 成功时才存在。

必须记录：

- git commit
- config hash
- seed
- model name/version/hash
- start/end timestamps
- package versions
- evaluation count

页面刷新不应丢失 job；前端应按 `job_id` 恢复状态。

---

## 13. Performance 要求

目标不是实时控制，而是交互式 design demo。

### V0 目标

- 页面加载：小于 3 秒
- 创建 job 后 0.5 秒内出现进度状态
- mock-model full optimization：小于 60 秒
- 完成后 preview geometry：小于 2 秒
- UI 操作过程中不冻结

总时间近似为：

```text
T_total ≈ N_evaluations × T_system_evaluation + T_final_geometry
```

因此：

- 模型只加载一次
- 复用相同 candidate 的缓存
- 几何只生成最终一次
- 在 model 支持时批量预测
- search budget 完全配置化

若某组 borrowed models 每次推理需要 1 秒，而 optimizer 调用数百次，那么分钟级是客观结果，服务器也不会从根本上解决接口设计问题。

---

## 14. UQ / conformal 预留

所有 model output 可使用如下扩展 schema：

```python
class PredictionValue(BaseModel):
    value: float
    unit: str | None = None
    uncertainty_status: Literal[
        "not_implemented",
        "not_available",
        "available",
    ] = "not_implemented"
    lower: float | None = None
    upper: float | None = None
    validity_score: float | None = None
```

V0 optimizer 使用 `value`，忽略其他字段。未来可增加：

- robust constraint
- chance constraint
- conformal lower/upper bound
- OOD rejection
- uncertainty penalty

但 V0 UI 必须明确显示未评估，而不是留一个容易误解的空白 confidence badge。

---

## 15. Tests

### Unit tests

- config validation
- units / name mapping
- adapter output validation
- constraint margin signs
- penalty calculation
- geometry mapping
- deterministic seed
- invalid model output
- infeasible optimization

### Integration tests

- mock models → optimizer → result
- API job lifecycle
- SSE event order
- result persistence
- browser refresh recovery
- geometry fallback

### End-to-end test

输入固定 mission，验证：

1. job completes
2. result contains best design
3. constraints are present
4. convergence is non-empty
5. aircraft spec can be rendered
6. same seed gives same result within tolerance

---

## 16. 推荐开发顺序

严格按以下顺序开发，避免局部模块都“很完整”但系统无法运行：

```text
1. Mock model + evaluator
2. API job
3. Very small optimizer
4. Result JSON
5. AircraftSpec mapping
6. Frontend form + progress + preview
7. Persistence
8. First borrowed model adapter
9. Error handling and tests
10. Optional OpenVSP export
```

第一天结束时必须已经能完成第 1–6 步中的最小版本。

---

## 17. 验收命令

建议在项目根目录提供：

```bash
./scripts/run_rapid_design_demo.sh
```

或明确的两个终端命令：

```bash
# Backend
CAD_BACKEND=fake .venv/bin/python -m uvicorn \
  services.api.app.main:app --host 127.0.0.1 --port 8900

# Frontend
cd apps/web && npm run dev
```

另提供：

```bash
pytest -q tests/api/test_rapid_design_*.py
```

和一个 smoke request：

```bash
python scripts/smoke_test_rapid_design.py
```

验收页面：

```text
http://localhost:3900/rapid-design
```
