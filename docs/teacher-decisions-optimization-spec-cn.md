# Rapid Process Design：老师待确认的优化规范

> 状态：`PENDING TEACHER DECISION`  
> 本文只收集待确认决策。在老师确认前，代码不得把空白项、临时值或示例范围当成正式优化规范。明确标注、配置独立、可追溯且不冒充正式结论的 Demo Mission 可以运行；Demo 结果不改变任何待确认项的状态。

## 一页决策摘要（讨论入口）

> 下表只压缩需要老师拍板的正式问题。`mission_demo_v1` 仍可独立运行，用来验证程序是否正确执行当前公开假设；它不是正式优化定义，也不把本页任何 `Pending` 项自动改为已确认。

| 决策主题 | 当前 Demo 用什么 | 为什么需要确认 | 老师决定什么 | 对应配置或接口 |
|---|---|---|---|---|
| 优化目标与优先级 | 可行候选优先；其后按“归一化起飞质量 + 已接入约束违约惩罚”的 objective 升序；固定 seed 的有限预算内返回最多 3 个有差异候选 | 这是便于演示的单一标量排序，不等于项目真正要最轻、最省油、最长航程或做多目标权衡 | 正式目标的数学定义、主次顺序、权重或 Pareto/字典序规则，以及无可行解时的选取规则 | `configs/rapid_design/mission_demo_v1.yaml` 的 `optimizer`；Mission Demo 结果中的 `ranking_rule`、`score_breakdown` |
| 可优化变量、固定参数、设计范围及是否跨构型 | 用户先固定一个 `conventional_v2` preset；搜索 8 个原生几何变量和燃油质量；边界来自独立 Demo profile；不跨 family | 当前范围只证明参数能被传递、评价和复现，不能证明变量集合、固定项或边界有工程依据 | 哪些量连续/离散/固定，各自上下界与来源，发动机/材料/翼型/尾型是否固定，以及是否允许跨 preset/family 搜索 | `mission_demo_v1.yaml` 的 `geometry_variables`、`sizing_variables`；family manifest 与 Analyze request |
| 工程约束及阈值 | 检查航程、最大 L/D、起飞质量、燃油上限和 Analyze 声明域；几何合法性是候选进入排名前的必要条件 | 配平、稳定性、容积、结构、推进匹配、起降性能等仍未接入；Demo 阈值只是临时输入范围 | 正式 hard/soft 约束、阈值、裕量定义、违约处理，以及“可行”和“工程验证通过”的判据 | `mission_demo_v1.yaml` 的 `inputs`、`metric_coverage`；结果中的 `constraints`、`domain_status` |
| 气动、质量、推进、航程模型与适用范围 | 当前 family 的低阶整机 polar；透明系数质量式；固定等效 TSFC 的 Breguet-style 航程；推进仅以数量质量项部分接入；另显示参考起飞质量下的巡航 CL/L/D 一致性诊断，但暂不计分 | 现模型没有完整配平、稳定性、推进匹配、任务积分或高保真验证；max L/D 航程假设不能代替指定巡航状态验证 | 每个学科的正式模型、数据/权重来源、有效域、误差标准、巡航参考重量与速度、任务积分方法和推进耦合方式 | `mission_demo_v1.yaml` 的 `mission_model`、`metric_coverage`；family Analyze；结果中的 `cruise_consistency` 与 provenance |
| 优化算法、预算、停止条件及多候选规则 | 固定 seed `2711` 的 seeded uniform search，3 × 8 次评价；feasible-first；用归一化设计向量距离去重并最多返回 3 个 | 有限随机搜索只用于可重复 Demo，不能证明收敛、全局最优、计算预算合理或候选差异具有正式意义 | 正式算法、初始化/并行策略、评价预算、停止与收敛准则、复现要求、Top-K/Pareto 数量及去重规则 | `mission_demo_v1.yaml` 的 `optimizer`、`candidate_count`、`diversity_threshold`；搜索结果中的 `search`、`selection` |
| 不确定性处理和验证标准 | 展示模型来源、版本、profile hash、domain status、约束余量和未接入项；不生成虚假的置信区间；Demo 测试验证程序响应与前后端一致性 | 程序可复现不等于模型准确，域内也不等于工程可信；论文或工程使用需要独立基准和误差证据 | 不确定性类型与校准数据、OOD/robust/chance-constraint 用法、验证数据集、允许误差，以及 Demo/研究原型/论文/工程各级验收门槛 | `mission_demo_v1.yaml` 的 `metric_coverage`；Analyze provenance/domain；第 8、9、11 节签署项 |

讨论时请直接在后续对应章节填写结论与来源，并在第 11 节签署；摘要本身不替代正式数学定义。

## 1. 项目术语与第一版范围

### 1.1 “O 开头”的术语

- [ ] Overall Aircraft Design (OAD)
- [ ] Aircraft Optimization / Overall Optimization
- [ ] OpenMDAO
- [ ] OpenVSP
- [ ] 其他：____________________

老师原话、来源和本项目中的准确含义：

> 

### 1.2 第一版研究对象与 family

- [ ] 固定翼无人机
- [ ] 小型通航飞机
- [ ] 常规有人运输机
- [ ] 多个固定翼类别
- [ ] 其他：____________________

| Family | 必须支持 | 仅几何 | Analyze | Optimize | 备注 |
|---|---:|---:|---:|---:|---|
| `conventional_v2` |  |  |  |  |  |
| `bwb_v1` |  |  |  |  |  |
| canard |  |  |  |  |  |
| twin-boom |  |  |  |  |  |
| flying-wing |  |  |  |  |  |
| 其他 |  |  |  |  |  |

系统应自动跨 family 选择，还是必须由用户先选 family：

> 

## 2. 优化目标

### 2.1 主目标

- [ ] 最小起飞质量 MTOW
- [ ] 最小空重
- [ ] 最小燃油质量
- [ ] 最大航程
- [ ] 最大续航时间
- [ ] 最大 L/D
- [ ] 最小成本
- [ ] 多目标 Pareto
- [ ] 其他：____________________

正式数学定义：

```text
Objective =
```

### 2.2 多目标与候选

- [ ] 加权和
- [ ] Pareto front
- [ ] lexicographic / 优先级
- [ ] epsilon-constraint
- [ ] 其他：____________________

返回候选数量、排序规则，以及“候选明显不同”的正式定义：

> 

## 3. 用户输入、固定条件与设计变量

### 3.1 Mission requirements

| 名称 | 单位 | 默认值 | 最小值 | 最大值 | Requirement / Constraint / Fixed | 来源 |
|---|---|---:|---:|---:|---|---|
| 航程 | km |  |  |  |  |  |
| 载荷 | kg |  |  |  |  |  |
| 巡航速度 | km/h 或 Mach |  |  |  |  |  |
| 巡航高度 | m |  |  |  |  |  |
| 续航时间 | h |  |  |  |  |  |
| 起飞距离 | m |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |

必须固定的发动机、材料、翼型族、尾翼类型和推进架构：

> 

### 3.2 `conventional_v2` 可优化变量

| 变量 | 是否优化 | 连续/离散/整数 | 单位 | 下界 | 上界 | 来源/理由 |
|---|---:|---|---|---:|---:|---|
| 翼面积或翼展 |  |  |  |  |  |  |
| 展弦比 |  |  |  |  |  |  |
| 内外翼后掠 |  |  |  |  |  |  |
| taper / kink |  |  |  |  |  |  |
| 扭转 |  |  |  |  |  |  |
| 机身长度及截面/容积 |  |  |  |  |  |  |
| 尾臂和平尾/垂尾尺寸 |  |  |  |  |  |  |
| 发动机数量和位置 |  |  |  |  |  |  |
| 燃油质量 |  |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |

### 3.3 `bwb_v1` 可优化变量

| 变量 | 是否优化 | 连续/离散/整数 | 单位 | 下界 | 上界 | 来源/理由 |
|---|---:|---|---|---:|---:|---|
| c1 |  |  |  |  |  |  |
| c2/c1、c3/c1、c4/c1 |  |  |  |  |  |  |
| b1/c1、b2/c1、b3/c1 |  |  |  |  |  |  |
| 内外翼后掠 |  |  |  |  |  |  |
| 厚度、扭转 |  |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |

## 4. 正式约束

| 约束 | 关系 | 阈值/范围 | 计算模型 | Hard / Soft | 来源 |
|---|---|---|---|---|---|
| 航程 | >= |  |  |  |  |
| L/D | >= |  |  |  |  |
| MTOW | <= |  |  |  |  |
| 燃油质量 | <= |  |  |  |  |
| 失速速度、起飞距离 | <= |  |  |  |  |
| 静稳定裕度、配平 |  |  |  |  |  |
| 尾容积 |  |  |  |  |  |
| 载荷/燃油容积 | >= |  |  |  |  |
| 结构/应力 |  |  |  |  |  |
| 推重比/功重比 | >= |  |  |  |  |
| 几何合法性 |  |  |  | Hard |  |
| 其他 |  |  |  |  |  |

违约处理：拒绝 / penalty / repair / 返回最小违约方案 / 其他：__________

## 5. 评价模型与 surrogate

| Discipline | 模型/代码 | 输入 | 输出 | 权重位置 | 许可 | 有效域 | 验证误差 |
|---|---|---|---|---|---|---|---|
| Aerodynamics |  |  |  |  |  |  |  |
| Structure / mass |  |  |  |  |  |  |  |
| Propulsion |  |  |  |  |  |  |  |
| Mission |  |  |  |  |  |  |  |
| Stability |  |  |  |  |  |  |  |

NeuralFoil 的角色：二维翼型 / 经验整机修正 / 不进入最终 optimizer / 其他：__________

OpenVSP/VSPAERO 的角色：不使用 / 几何导出 / 候选复核 / DOE 与 surrogate 训练 / 优化环内 / 其他：__________

## 6. 优化算法、预算和停止条件

候选算法：differential evolution / SLSQP 或 IPOPT / NSGA-II / Bayesian optimization / mixed-integer / 分层 family 优化 / 其他：__________

选择理由：

> 

| 项目 | 目标 |
|---|---|
| 单次模型推理时间 |  |
| 单次 Analyze 响应 |  |
| 单 family 优化总时间 |  |
| 跨 family 总时间 |  |
| 最大 evaluation 数 |  |
| 是否要求确定性复现 |  |
| 并行数量 |  |

停止条件：

> 

## 7. 多候选与结果展示

- [ ] 单一最优解
- [ ] top-3 / top-5 近优解
- [ ] Pareto front
- [ ] 每个 family 至少一个候选

候选去重依据：design-vector distance / silhouette distance / topology difference / performance distance / 其他：__________

必须展示：3D 外形 / baseline / CL、CD、CM、L/D / 航程 / 重量分解 / 约束余量 / Pareto / 模型来源与版本 / uncertainty。

## 8. 不确定性、置信区间与 OOD

输出类型：point prediction / ensemble variance / GP interval / conformal interval / epistemic 与 aleatoric / OOD score / 其他：__________

优化中的使用方式：仅 UI 警告 / robust constraint / chance constraint / confidence bound / uncertainty penalty / 超域拒绝 / 其他：__________

置信水平与校准数据：

> 

## 9. 验证与论文标准

第一版 demo、工程研究原型、论文 baseline 和需要复刻的公开系统分别如何验收：

> 

## 10. Legacy demo 临时值声明

`configs/rapid_design/demo.yaml` 中的 mission inputs、变量边界、SciPy differential evolution、population、iterations、penalty、质量模型、NeuralFoil 配置和低阶整机修正均为 legacy demo 临时设定，不代表老师已批准。

老师同意沿用的部分：

> 

必须废弃或修改的部分：

> 

## 11. 决策签署

| 决策项 | 状态 | 老师结论 | 日期 | 实现负责人 |
|---|---|---|---|---|
| 项目术语与范围 | Pending |  |  |  |
| 第一版 family | Pending |  |  |  |
| 主目标 | Pending |  |  |  |
| 变量与边界 | Pending |  |  |  |
| 约束 | Pending |  |  |  |
| surrogate/model | Pending |  |  |  |
| optimizer | Pending |  |  |  |
| uncertainty | Pending |  |  |  |
| validation | Pending |  |  |  |

## 12. 对实现的约束

在关键项确认前：

1. 不调整生产 optimizer 的目标、权重、边界、population、iterations 或 uncertainty 逻辑；
2. 不把经验公式描述成老师批准或高保真模型；
3. 不把任何 family 自动声明为最优；
4. 可以重构接口、GeometryState、renderer、registry 和测试；
5. legacy demo 必须清楚标注；
6. 新 Mission Design 必须把 `Demo Search` 与 `Formal Optimization` 明确分区：Formal 继续显示 `optimization_spec_pending`，Demo 仅可使用独立、版本化、标注 `demo_only` 的配置运行；
7. Demo 只能按已接入指标排序，未接入指标必须显式标记且不得进入分数；
8. Demo 结果不得称为正式最优、老师认可方案或工程验证结论；
9. 老师确认后再实施正式优化规范。
