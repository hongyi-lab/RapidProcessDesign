# Claude Code Build Brief：Rapid Aircraft Design Demo V0

把下面内容作为 Claude Code 的开发任务说明。目标不是讨论，而是在现有仓库中实现一个可运行、可测试、可演示的 vertical slice。

---

## 1. Project objective

在 `zweien/aero-spec-agent` 的 fork 中新增一条 **不依赖 LLM API key** 的 rapid aircraft design 路径：

```text
HTML mission input form
→ local optimization job
→ surrogate model adapters
→ objective and constraints
→ best feasible design
→ AircraftSpec
→ interactive aircraft preview
→ metrics / constraints / convergence
```

V0 是 engineering demo。不要为了“研究创新”增加额外复杂度。

---

## 2. Read before coding

先阅读并遵循仓库中的：

- `README.md`
- `CLAUDE.md`
- existing FastAPI router patterns
- existing SSE/job runner patterns
- `services/api/app/schemas/aircraft_spec.py`
- `apps/web/src/components/cad-viewer/`
- existing tests under `tests/api/`

先在本机跑通 upstream tests 和 fake CAD demo。记录审阅的 upstream commit。

---

## 3. Non-negotiable constraints

1. 保留现有聊天、Deep Design 和 CAD 功能，不做破坏性重构。
2. 新增独立 `/rapid-design` 页面。
3. rapid-design path 不调用 LLM，也不要求 API key。
4. V0 默认使用 fake/preview geometry，不要求 OpenVSP。
5. optimization variables、bounds、objective、constraints 和 solver settings 从 YAML 读取。
6. model access 必须经过 adapter，不允许在 optimizer 中硬编码模型。
7. 后端 canonical units 全部使用 SI。
8. 运行中必须有实时进度；不能让用户盲等。
9. 每次运行必须可复现并保存 seed、config、models 和 results。
10. UQ/conformal 不实现，但 schema 保留明确的 `not_implemented` 状态。
11. 不添加 database、authentication、cloud deployment、OpenMDAO、CPACS 或 multi-objective optimization。
12. 不把 demo heuristic 称为 engineering-validated result。

---

## 4. Implement this vertical slice first

第一阶段必须在最短时间内完成以下闭环：

```text
MissionForm
→ POST /api/rapid-design/jobs
→ background/local job
→ deterministic mock evaluator
→ small bounded optimizer
→ result JSON
→ GeometryMapper
→ AircraftSpec
→ existing Three.js preview
→ result and constraint cards
```

在第一组 borrowed surrogate 尚未准备好时，使用 deterministic mock models。Mock outputs 必须标为 demo-only。

不要先写所有 adapter，不要先接 OpenVSP，不要先优化 UI 细节。

---

## 5. New backend modules

新增：

```text
services/api/app/routers/rapid_design.py

services/api/app/schemas/rapid_design.py

services/api/app/services/rapid_design/
├── config_loader.py
├── model_adapter.py
├── model_registry.py
├── evaluator.py
├── optimizer.py
├── geometry_mapper.py
├── result_store.py
└── job_runner.py
```

### Required API

```text
GET  /api/rapid-design/config
POST /api/rapid-design/jobs
GET  /api/rapid-design/jobs/{job_id}
GET  /api/rapid-design/jobs/{job_id}/events
GET  /api/rapid-design/jobs/{job_id}/result
POST /api/rapid-design/jobs/{job_id}/cancel   # optional but preferred
```

Use existing SSE/event-bus conventions where possible.

---

## 6. New frontend modules

新增：

```text
apps/web/src/app/rapid-design/page.tsx

apps/web/src/components/rapid-design/
├── MissionForm.tsx
├── RapidDesignWorkspace.tsx
├── OptimizationProgress.tsx
├── ResultSummary.tsx
├── ConstraintTable.tsx
├── DesignVariableTable.tsx
├── ConvergenceChart.tsx
└── ModelProvenance.tsx
```

Reuse the existing:

- `CadViewer`
- `AircraftThreePreview`
- GLB/OBJ loading
- parameter-driven preview fallback
- existing visual conventions where practical

---

## 7. Config-driven interface

Create:

```text
configs/rapid_design/demo.yaml
```

It must define:

- mission fields
- design variables
- bounds
- objective
- constraints
- optimizer settings
- model entrypoints
- geometry mapping defaults
- UQ status

Frontend gets form metadata from `GET /api/rapid-design/config`; do not duplicate numerical bounds in TypeScript.

---

## 8. Model adapter

Implement the minimal adapter contract:

```python
class SurrogateAdapter(Protocol):
    @property
    def metadata(self) -> ModelMetadata:
        ...

    def load(self) -> None:
        ...

    def predict(self, inputs: dict[str, float]) -> dict[str, float]:
        ...
```

V0 only needs `python_callable`.

The adapter is responsible for:

- load-once lifecycle
- input order
- normalization
- unit conversion
- tensor/NumPy conversion
- output mapping
- finite-value checks

Do not implement generic PyTorch/joblib/ONNX adapters until an actual model requires them.

---

## 9. Optimizer

Add SciPy as a dependency.

Default V0 method:

```text
scipy.optimize.differential_evolution
```

Requirements:

- fixed seed
- bounded design variables
- config-controlled search budget
- progress callback
- cancellation checks
- cache repeated evaluations
- catch candidate-level model errors
- penalty for violated constraints
- preserve raw objective and constraint values
- keep best feasible candidate separately
- optional local polishing
- return least-violating candidate when no feasible solution is found

Use standardized margin:

```text
margin >= 0 means feasible
```

Do not state that the result is a guaranteed global optimum.

---

## 10. GeometryMapper

V0 only supports conventional tube-and-wing.

At minimum, map:

```python
span_m = sqrt(aspect_ratio * wing_area_m2)
root_chord_m = 2 * wing_area_m2 / (span_m * (1 + taper_ratio))
tip_chord_m = taper_ratio * root_chord_m
```

Build an `AircraftSpec` compatible with the existing viewer.

Important:

- geometry generation runs once after optimization
- if GLB/OpenVSP is unavailable, use parameter preview
- geometry failure must not discard the numerical result
- mark all defaulted/derived geometry fields

---

## 11. Result schema

Return:

- status
- mission input
- best design variables
- raw objective
- objective sense
- surrogate outputs
- derived outputs
- constraints, targets and margins
- feasible state
- runtime
- iterations and evaluations
- convergence history
- seed
- config hash
- model names/versions/hashes
- `AircraftSpec`
- optional GLB URL
- warnings
- uncertainty placeholder

UQ placeholder:

```json
{
  "status": "not_implemented",
  "method": null,
  "lower": null,
  "upper": null
}
```

---

## 12. Persistence

Save every run under:

```text
storage/rapid_design/{job_id}/
```

including:

- `request.json`
- `resolved_config.yaml`
- `status.json`
- `convergence.json`
- `result.json`
- `aircraft_spec.json`
- `model_manifest.json`
- `run.log`

A browser refresh must be able to reconnect to or reload an existing job.

---

## 13. Progress events

Emit stages:

```text
queued
loading_models
initializing_optimizer
optimizing
generating_geometry
saving_result
completed
```

During optimization include:

- current iteration
- max iterations
- evaluation count
- current best objective
- current best feasible objective
- feasible candidate count
- progress fraction

Use a visible progress bar/timeline in the UI.

---

## 14. Tests

Add at least:

```text
test_rapid_design_config.py
test_rapid_design_adapter.py
test_rapid_design_optimizer.py
test_rapid_design_api.py
test_rapid_design_e2e.py
```

Test:

- valid/invalid config
- deterministic results with same seed
- correct constraint margin sign
- invalid model output handling
- feasible and infeasible runs
- SSE event order
- result persistence
- AircraftSpec rendering input
- full mock end-to-end flow

Run existing upstream tests too.

---

## 15. Acceptance criteria

The task is complete only when:

1. A developer can start backend and frontend locally.
2. `/rapid-design` opens without an LLM key.
3. User enters mission values and clicks Run.
4. Progress updates appear immediately.
5. Mock optimization completes within 60 seconds on a normal laptop.
6. An interactive conceptual aircraft is displayed.
7. Objective, variables, constraints and margins are visible.
8. Infeasible runs are clearly labeled.
9. Result JSON and run files are saved.
10. Same config and seed reproduce the same result.
11. Tests pass.
12. A short README section explains how to replace a mock model with a borrowed model.

---

## 16. Development order

Use this order and keep the application runnable after each stage:

```text
A. Run upstream repo with fake backend
B. Add backend config schema
C. Add mock adapter and evaluator
D. Add small optimizer
E. Add rapid-design job API and SSE
F. Add GeometryMapper and AircraftSpec output
G. Add frontend form/progress/result/preview
H. Add persistence and refresh recovery
I. Add tests
J. Integrate the first real borrowed model
K. Add optional OpenVSP export only after V0 works
```

After each stage:

- run tests
- show the exact command used
- report changed files
- keep a concise implementation log
- do not stop at planning; implement and verify

---

## 17. Do not do these things

- Do not rewrite the whole repository.
- Do not use an LLM to choose the optimum.
- Do not put CAD generation inside every objective evaluation.
- Do not hard-code variables and bounds separately in frontend and backend.
- Do not silently convert unknown units.
- Do not swallow infeasibility.
- Do not fabricate confidence.
- Do not build adapters for hypothetical model formats.
- Do not introduce a database for V0.
- Do not block the demo on OpenVSP installation.
- Do not claim global optimality or certification-level accuracy.
