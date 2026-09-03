# Rapid Aircraft Design Demo：复用与文献调查

**调查日期：** 2026-09-03  
**问题：** 是否已有可复用项目与文献，足以快速搭建“网页输入任务要求 → surrogate-based optimization → 飞机三维形状与最优指标”的本地 Demo？

---

## 1. 调查结论

### 工程结论

**可以做，而且没有必要从零开始。**

最接近本项目 UI 与工程需求的现成 shell 是 **AeroSpec Agent**：它已经具备 Next.js、FastAPI、SSE、Three.js、`AircraftSpec`、fake/OpenVSP geometry backends 和 job/version storage。它不是成熟的工业 aircraft sizing platform，也不应直接把其 LLM-driven “Deep Design”当作严谨 optimizer；但作为几天内完成 HTML demo 的外壳，它是本轮调查中最直接的复用对象。

### 学术结论

Surrogate-assisted conceptual aircraft design、MDO 和快速 structural/aerodynamic optimization 已有充分文献基础。2026 年已有工作明确将 surrogate model generation 与 conceptual aircraft design optimization 集成。因此：

- **“把已有 surrogate 接入优化并显示飞机”本身主要是 engineering integration，不应硬包装成方法创新。**
- 作为后续研究基础设施非常有价值。
- 未来论文 novelty 更可能来自 uncertainty-aware optimization、cross-model coupling、model validity、inverse design、surrogate transfer 或 human-in-the-loop design，而不是网页本身。

---

## 2. 本轮复用候选比较

| 候选 | 已有能力 | V0 是否使用 | 判断 |
|---|---|---:|---|
| AeroSpec Agent | Next.js、FastAPI、SSE、Three.js、AircraftSpec、CAD backends、版本管理 | **是，作为主 shell** | 离最终网页形态最近，改动最少 |
| SciPy Optimize | black-box bounded optimization | **是** | 轻、稳定、无需先引入 MDO framework |
| Three.js | 浏览器 3D | **是，通过 AeroSpec 复用** | 可直接显示参数化概念飞机 |
| trimesh | mesh / GLB 处理 | **是，按需** | 已在 AeroSpec 依赖中，可做 fallback |
| OpenVSP | 参数化 aircraft CAD 和 Python API | Optional | 输出更像真正飞机，但安装不应阻塞 V0 |
| AeroSandbox | aircraft optimization、可微模型、3D/mesh/CAD export | Optional | 可作后续 geometry/optimization helper |
| OpenMDAO | 模块化 MDA/MDO、surrogate components | 暂不 | 架构上正确，但 V0 先用薄 adapter 更快 |
| FAST-OAD | OpenMDAO 上的 overall aircraft design 与插件式 discipline models | 暂不 | 可供未来整体 sizing 参考，V0 太重 |
| NASA Aviary | aircraft sizing、mission、optimization、GASP/FLOPS relations | 暂不 | 适合严谨概念设计升级，不是最快 demo 路径 |
| OpenConcept | 低成本概念 MDO，尤其电推进 | 暂不 | 可作为未来模型来源或结构参考 |
| 自己从零写网页和 CAD | 完全可控 | **否** | 重复造 UI/job/viewer，不能提高 V0 工程价值 |

---

## 3. 最值得复用的项目：AeroSpec Agent

### Repository

- GitHub: <https://github.com/zweien/aero-spec-agent>
- 本轮审阅 commit: `15b3253910741d1e226f8f376a3c2804f16eb3d8`
- README 显示版本：0.3.0
- 主代码许可：MIT
- OpenVSP 为单独的 optional dependency，使用其自身许可证

### 已有功能

README 和代码结构显示其具备：

- Next.js 14 / React 18 前端
- FastAPI 后端
- Three.js 交互式预览
- GLB / OBJ loading
- parameter-driven geometry fallback
- OpenVSP geometry
- VSPAERO optional analysis
- `AircraftSpec` Pydantic schema
- HTTP / SSE workflow
- job replay / progress events
- fake CAD backend
- versioned output storage
- 大量 API tests

### 对本项目最有用的现成路径

```text
apps/web/src/components/cad-viewer/
services/api/app/schemas/aircraft_spec.py
services/api/app/services/job_events.py
services/api/app/services/job_runner.py
services/workers/cad_worker/openvsp_generator/
tests/api/
```

### 不能直接照搬的部分

#### 1. LLM 不是我们的 optimizer

AeroSpec 的自然语言路径可保留，但 rapid-design 必须支持：

```text
normal HTML form → deterministic numerical job
```

并且不需要任何 LLM API key。

#### 2. Deep Design 不是严谨 MDO

它主要是 LLM/graph-driven variant generation and comparison。我们的新路径应由明确的：

- design variables
- bounds
- objective
- constraints
- numerical optimizer
- surrogate outputs

驱动。

#### 3. 现有 performance estimate 只能做 sanity check

代码中包括固定 payload fraction、empty fraction、经验 `CD0`、Oswald efficiency 等简化常数。它们适合演示，不适合作为 borrowed surrogate 的替代物，也不应被用于宣称 engineering-optimal design。

#### 4. 需要 pin commit

该项目规模不大且仍在发展。应：

- fork 到自己的组织或账号
- pin 已审阅 commit
- 保留上游 tests
- 每次升级单独 merge
- 不直接依赖不断变化的 `master`

---

## 4. OpenVSP 的角色

### 能做什么

OpenVSP 是 NASA 发展的参数化飞机几何工具，并提供 Python API。它可以：

- 创建机身、机翼、尾翼和推进器外形
- 修改参数
- 保存 `.vsp3`
- 导出 mesh/CAD 格式
- 通过脚本和 API 自动运行

### 为什么 V0 不应强依赖它

OpenVSP 的 Python bindings 需要与编译时 Python 版本匹配，native environment 可能成为第一天的主要阻碍。

因此推荐：

```text
V0 default: Three.js parameter preview
V1 optional: OpenVSP export
```

这样即使 OpenVSP 安装失败，网页、优化和三维显示仍能演示。

Official documentation:

- <https://openvsp.org/docs.shtml>
- <https://openvsp.org/pyapi_docs/latest/>

---

## 5. AeroSandbox 的角色

AeroSandbox 是 Python aircraft design optimization toolkit，支持：

- custom physics models
- automatic differentiation
- aircraft aerodynamics / structures / propulsion / mission models
- interactive `Airplane.draw(...)`
- Plotly、PyVista、trimesh 等 3D backends
- STEP / OpenVSP script 等输出

它是 MIT license，且内部以 SI units 为主。

### 推荐用法

V0 不必引入它作为主框架，但可在以下情况使用：

- 需要一个比手写 Three.js geometry 更稳定的 geometry object
- borrowed models 能用可微形式重写
- 需要快速增加 physical baseline model
- 需要导出 OpenVSP script 或 STEP

### 不建议的用法

不要同时把 AeroSpec、AeroSandbox、OpenMDAO、FAST-OAD 全塞进 V0。每多一层框架，就多一套变量、单位和生命周期。

References:

- <https://github.com/peterdsharpe/AeroSandbox>
- <https://aerosandbox.readthedocs.io/en/master/>
- `Airplane.draw`: <https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/geometry/>

---

## 6. OpenMDAO / FAST-OAD / Aviary 的角色

这些项目证明了本项目的模块化思想是合理的，但它们不是最快 V0 路径。

### OpenMDAO

OpenMDAO 用 component 连接 multidisciplinary model，并提供 optimization/solver infrastructure。其 `MetaModelUnStructuredComp` 明确用于用低成本 surrogate 替换昂贵 component。

这与本项目的长期结构一致：

```text
same input/output contract
→ analytic model / solver / surrogate can be swapped
```

V0 先用轻量 `SurrogateAdapter` 实现相同思想；等 discipline coupling 和 derivatives 真的复杂后，再迁移到 OpenMDAO。

References:

- <https://openmdao.org/>
- <https://openmdao.org/newdocs/versions/latest/features/building_blocks/components/metamodelunstructured_comp.html>

### FAST-OAD

FAST-OAD 建立在 OpenMDAO 上，目标就是 rapid overall aircraft design，并强调同一 discipline 的 model 可以切换、添加或移除。

它适合未来需要：

- CS-25 / GA / UAV sizing modules
- standardized multidisciplinary workflow
- stronger aircraft-specific formulation

但其 GPL-3.0 license 和较大框架成本意味着 V0 不应直接复制代码进入 MIT 项目。可以运行、调用或参考接口设计，但任何实际代码复用都需要单独核对许可义务。

Reference:

- <https://github.com/fast-aircraft-design/FAST-OAD>

### NASA Aviary

Aviary 是基于 OpenMDAO 的 aircraft analysis/design/optimization tool，包含 GASP/FLOPS sizing relations 和 mission formulations。它适合长期增加：

- validated conceptual sizing relations
- mission analysis
- analytic gradients
- external subsystem integration

但它的设计域和概念较多，V0 直接使用会把“接几组 surrogate 做网页 demo”变成“先学完整 aircraft MDO framework”。

Reference:

- <https://github.com/OpenMDAO/Aviary>
- AIAA paper DOI: <https://doi.org/10.2514/6.2024-4219>

---

## 7. 直接相关文献

## 7.1 Golombek et al., 2026

**H. Golombek et al.**  
“An automated surrogate model generation framework for rapid aeroelastic structural sizing optimizations in conceptual aircraft design.”  
*CEAS Aeronautical Journal*, 2026.  
DOI: <https://doi.org/10.1007/s13272-026-00996-6>

### 与本项目的关系

该工作将 aerodynamic coefficients 和 structural mass 等 surrogate 集成到 conceptual aircraft design optimization 中，证明：

- surrogate 可以作为 discipline-level replacement
- structural/aero outputs 可以进入 overall optimization
- 快速 conceptual optimization 是成熟且活跃的研究方向

### 对我们的判断

它支持项目可行性，但也意味着“把 surrogate 接入优化”本身不是足够强的新颖点。V0 应诚实定位为 infrastructure / engineering prototype。

---

## 7.2 Shen, Needels & Alonso 相关工作，2025–2026

**VortexNet: A Graph Neural Network-Based Multi-Fidelity Surrogate Model for Field Predictions.**  
AIAA SciTech 2025.  
DOI: <https://doi.org/10.2514/6.2025-0494>

以及 2026 年的：

**A multi-fidelity workflow for conceptual design using Graph Neural Network-based field prediction surrogate model.**  
*Computers & Fluids*, 2026.  
DOI: <https://doi.org/10.1016/j.compfluid.2026.107153>

### 与本项目的关系

这些工作表明现代 aerodynamic surrogate 正被直接嵌入 conceptual design workflow，而不仅用于离线预测。

### 对我们的判断

V0 不训练模型，也不做 multi-fidelity；但 adapter 架构应该允许未来把这类模型作为 aero discipline 插入。

---

## 7.3 Inverse Mapping for Airfoil Optimization, 2026

**Inverse Mapping for Airfoil Optimization Using Multifidelity Reduced-Order Neural Networks.**  
*Journal of Aircraft*, 2026.  
DOI: <https://doi.org/10.2514/1.C038635>

### 与本项目的关系

该工作研究从 design requirements 直接预测 optimal airfoil shape，避免 online iterative optimization。

### 对我们的判断

这是未来一种可能的升级：

```text
requirements → direct optimal design prediction
```

但它需要固定 constraint setup 和专门训练数据。我们的 V0 应继续使用通用 online optimizer，因为老师会修改 variables、bounds 和 constraints。

---

## 7.4 Web-based visual analytics for aircraft optimization, 2026

**Visual Analytics Framework for Multi-Objective Optimisation of Aircraft Design.**  
*Engineering Proceedings*, 2026.  
DOI: <https://doi.org/10.3390/engproc2026133167>

### 与本项目的关系

该工作说明 web-based visual analytics、surrogate 和 aircraft optimization 的结合本身是合理交互方向。

### 对我们的判断

我们 V0 先做 single-objective、constraint-aware result display。Pareto front 与 robust multi-objective visualization 留到后续。

---

## 8. 最快可复刻路线

### 选择

```text
Base repo: AeroSpec Agent
Optimizer: SciPy
Model integration: custom Python adapters
Geometry: existing Three.js preview
Optional export: OpenVSP
```

### 不选择

```text
Build frontend from scratch
Start with OpenMDAO
Start with FAST-OAD
Start with Aviary
Require OpenVSP before any demo can run
Train a new unified neural network
Let an LLM invent the optimum
```

### 原因

这条路线把复用集中在“通用软件壳”，而把真正属于老师研究的部分保留为可替换模块：

- objective
- constraints
- design variables
- borrowed surrogates
- coupling logic
- uncertainty treatment

---

## 9. Engineering credibility 的最低边界

即使只是 demo，也必须做到：

1. 所有输入和输出有明确单位。
2. 记录 model source/version/hash。
3. 记录 optimization bounds、constraints 和 seed。
4. 不把 heuristic estimate 冒充 external surrogate。
5. 不将 infeasible candidate 标成最优设计。
6. 不将未实现 UQ 标成 high confidence。
7. UI 明确写 concept-level / research demo。
8. 不在未检查 license 时重新分发第三方 weights。
9. 对 optimizer 搜索到边界的解进行醒目标记。
10. 保存 convergence 与 constraint margins，便于老师判断优化是否可信。

---

## 10. 最终判断

### 能否在个人电脑完成

能。只要不训练模型、不跑 CFD/FEA，主要负载是数百次 surrogate inference、一个轻量 optimizer 和一次三维几何生成。

### 搭建难度

- HTML/3D/job shell：已有项目可复用，难度低。
- optimizer shell：难度低到中等。
- 真正不确定的工作量：第三方 model packaging、units、normalization、coupling 和 geometry mapping。
- 研究级可信度：后续需要 validation/UQ，但不应阻塞 V0。

### 推荐行动

**先用 mock models 在 1 天内做出完整 vertical slice，再逐个替换成老师指定的 borrowed models。**

这比先搜齐所有模型、先讨论最优参数、先做 uncertainty 或先采用大 MDO framework 更快，也更容易暴露真实接口问题。
