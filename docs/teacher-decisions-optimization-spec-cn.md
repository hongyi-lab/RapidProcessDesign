# Rapid Process Design：老师待确认的优化规范

> 状态：`PENDING TEACHER DECISION`  
> 本文只收集待确认决策。在老师确认前，代码不得把空白项、临时值或示例范围当成正式优化规范。明确标注、配置独立、可追溯且不冒充正式结论的 Demo Mission 可以运行；Demo 结果不改变任何待确认项的状态。

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
