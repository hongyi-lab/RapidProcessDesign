# RapidProcessDesign：老师待确认的优化规范

> 状态：`PENDING TEACHER DECISION`  
> 用途：集中记录优化目标、设计变量、约束、模型、算法和不确定性方案。  
> 原则：在老师确认前，Codex 不得把本文件中的空白项自行补成正式参数，也不得据此修改生产优化逻辑。

---

## 0. 首先确认项目术语与范围

### 0.1 老师所说的 O 开头术语准确是什么？

- [ ] Overall Aircraft Design (OAD)
- [ ] Aircraft Optimization / Overall Optimization
- [ ] OpenMDAO
- [ ] OpenVSP
- [ ] 其他：____________________

老师原话或来源：

> 

该术语在本项目中具体表示：

> 

### 0.2 第一版研究对象

- [ ] 固定翼无人机
- [ ] 小型通航飞机
- [ ] 常规有人运输机
- [ ] 多个固定翼类别
- [ ] 其他：____________________

说明：

> 

---

## 1. 第一版必须支持哪些 aircraft family？

| Family | 必须支持 | 仅展示几何 | 需要 Analyze | 需要 Optimize | 备注 |
|---|---:|---:|---:|---:|---|
| conventional_v2 |  |  |  |  |  |
| bwb_v1 |  |  |  |  |  |
| canard |  |  |  |  |  |
| twin-boom |  |  |  |  |  |
| flying-wing |  |  |  |  |  |
| 其他 |  |  |  |  |  |

是否允许系统自动跨 family 选择：

> 

还是必须由用户先选择 family：

> 

---

## 2. 优化目标

### 2.1 主目标

请选择或填写：

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

### 2.2 多目标时如何比较

- [ ] 加权和
- [ ] Pareto front
- [ ] lexicographic / 优先级
- [ ] ε-constraint
- [ ] 其他：____________________

需要展示多少个候选：

> 

“候选必须明显不同”的正式定义：

> 

---

## 3. 用户输入、固定条件与设计变量

### 3.1 用户输入的 mission requirements

| 名称 | 单位 | 默认值 | 最小值 | 最大值 | Requirement / Constraint / Fixed | 来源 |
|---|---|---:|---:|---:|---|---|
| 航程 | km |  |  |  |  |  |
| 载荷 | kg |  |  |  |  |  |
| 巡航速度 | km/h 或 Mach |  |  |  |  |  |
| 巡航高度 | m |  |  |  |  |  |
| 续航时间 | h |  |  |  |  |  |
| 起飞距离 | m |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |

### 3.2 哪些量必须固定？

例如发动机、材料、翼型族、尾翼类型、推进架构：

> 

### 3.3 哪些量允许 optimizer 改变？

#### conventional_v2

| 变量 | 是否优化 | 连续/离散/整数 | 单位 | 下界 | 上界 | 来源/理由 |
|---|---:|---|---|---:|---:|---|
| 翼面积或翼展 |  |  |  |  |  |  |
| 展弦比 |  |  |  |  |  |  |
| 内外翼后掠 |  |  |  |  |  |  |
| taper / kink |  |  |  |  |  |  |
| 扭转 |  |  |  |  |  |  |
| 机身长度 |  |  |  |  |  |  |
| 机身截面/容积 |  |  |  |  |  |  |
| 尾臂 |  |  |  |  |  |  |
| 平尾/垂尾尺寸 |  |  |  |  |  |  |
| 发动机数量和位置 |  |  |  |  |  |  |
| 燃油质量 |  |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |

#### bwb_v1

| 变量 | 是否优化 | 连续/离散/整数 | 单位 | 下界 | 上界 | 来源/理由 |
|---|---:|---|---|---:|---:|---|
| c1 |  |  |  |  |  |  |
| c2/c1 |  |  |  |  |  |  |
| c3/c1 |  |  |  |  |  |  |
| c4/c1 |  |  |  |  |  |  |
| b1/c1 |  |  |  |  |  |  |
| b2/c1 |  |  |  |  |  |  |
| b3/c1 |  |  |  |  |  |  |
| 内外翼后掠 |  |  |  |  |  |  |
| 厚度/扭转 |  |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |

---

## 4. 必须满足的约束

| 约束 | 关系 | 阈值/范围 | 计算模型 | Hard / Soft | 来源 |
|---|---|---|---|---|---|
| 航程 | ≥ |  |  |  |  |
| L/D | ≥ |  |  |  |  |
| MTOW | ≤ |  |  |  |  |
| 燃油质量 | ≤ |  |  |  |  |
| 失速速度 | ≤ |  |  |  |  |
| 起飞距离 | ≤ |  |  |  |  |
| 静稳定裕度 |  |  |  |  |  |
| 配平 |  |  |  |  |  |
| 尾容积 |  |  |  |  |  |
| 载荷容积 | ≥ |  |  |  |  |
| 燃油容积 | ≥ |  |  |  |  |
| 结构/应力 |  |  |  |  |  |
| 推重比/功重比 | ≥ |  |  |  |  |
| 几何合法性 |  |  |  | Hard |  |
| 其他 |  |  |  |  |  |

约束违约时：

- [ ] 直接拒绝
- [ ] penalty
- [ ] repair
- [ ] 返回最小违约方案
- [ ] 其他：____________________

---

## 5. 评价模型和 surrogate

### 5.1 老师已有或计划提供的模型

| Discipline | 模型/代码名称 | 输入 | 输出 | 权重位置 | 许可 | 有效域 | 验证误差 |
|---|---|---|---|---|---|---|---|
| Aerodynamics |  |  |  |  |  |  |  |
| Structure / mass |  |  |  |  |  |  |  |
| Propulsion |  |  |  |  |  |  |  |
| Mission |  |  |  |  |  |  |  |
| Stability |  |  |  |  |  |  |  |
| 其他 |  |  |  |  |  |  |  |

### 5.2 NeuralFoil 的角色

- [ ] 只用于二维翼型层
- [ ] 用经验修正扩展到整机概念估算
- [ ] 不进入最终 optimizer
- [ ] 其他：____________________

### 5.3 OpenVSP/VSPAERO 的角色

- [ ] 不使用
- [ ] 只用于最终几何导出
- [ ] 用于候选复核
- [ ] 用于 DOE / surrogate 训练
- [ ] 直接位于优化环内
- [ ] 其他：____________________

---

## 6. 优化算法与计算预算

### 6.1 算法

- [ ] differential evolution
- [ ] SLSQP / IPOPT 等梯度方法
- [ ] NSGA-II / 多目标进化算法
- [ ] Bayesian optimization
- [ ] mixed-integer 方法
- [ ] 分层：先 family，再连续优化
- [ ] 其他：____________________

理由：

> 

### 6.2 计算预算

| 项目 | 目标 |
|---|---|
| 单次模型推理时间 |  |
| 单次 Analyze 响应 |  |
| 单 family 优化总时间 |  |
| 跨 family 总时间 |  |
| 最大 evaluation 数 |  |
| 是否要求确定性复现 |  |
| 并行数量 |  |

### 6.3 停止标准

> 

---

## 7. 多候选和结果展示

应返回：

- [ ] 单一最优解
- [ ] top-3 同目标近优解
- [ ] top-5
- [ ] Pareto front
- [ ] 每个 family 至少一个候选
- [ ] 其他：____________________

候选去重依据：

- [ ] design-vector distance
- [ ] planform silhouette distance
- [ ] component/topology difference
- [ ] performance distance
- [ ] 其他：____________________

需要显示的结果：

| 指标/图 | 必须 | 可选 | 备注 |
|---|---:|---:|---|
| 3D 外形 |  |  |  |
| baseline overlay |  |  |  |
| CL/CD/CM polar |  |  |  |
| L/D |  |  |  |
| 航程 |  |  |  |
| 重量分解 |  |  |  |
| 约束余量 |  |  |  |
| Pareto |  |  |  |
| 模型来源/版本 |  |  |  |
| uncertainty |  |  |  |

---

## 8. 不确定性、置信区间与 conformal

本节可以后续填写，但需确认最终需求。

### 8.1 需要哪种输出？

- [ ] point prediction only
- [ ] model ensemble variance
- [ ] Gaussian process interval
- [ ] conformal prediction interval
- [ ] epistemic / aleatoric 分开
- [ ] OOD score
- [ ] 其他：____________________

### 8.2 优化时如何使用不确定性？

- [ ] 只在 UI 警告
- [ ] robust constraint
- [ ] chance constraint
- [ ] lower confidence bound / upper confidence bound
- [ ] 不确定性惩罚
- [ ] 超域直接拒绝
- [ ] 其他：____________________

置信水平：

> 

校准数据：

> 

---

## 9. 验证和论文标准

### 9.1 第一版 demo 的验收

> 

### 9.2 工程研究原型的验收

> 

### 9.3 论文需要的比较基线

> 

### 9.4 需要复刻的公开系统或案例

> 

---

## 10. 当前仓库中的临时值：仅供老师查看，不代表确认

当前 legacy demo 大致使用：

- 目标航程、载荷、巡航速度、巡航高度；
- 最大燃油、最大起飞质量、目标 L/D；
- conventional 单一模板中的翼面积、AR、taper、sweep、机身尺寸、NACA 风格参数和燃油；
- SciPy differential evolution；
- 最小起飞质量倾向的 penalty objective；
- NeuralFoil + 低阶整机修正。

老师是否同意沿用：

> 

必须废弃或修改：

> 

---

## 11. 决策签署表

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

---

## 12. 对 Codex 的约束

在本文件关键项未确认前：

1. 不调整生产 optimizer 的目标、权重和边界；
2. 不把临时经验公式描述为老师批准的模型；
3. 不把 BWB、conventional 或任何 family 自动声明为最优；
4. 可以重构接口、几何、UI、registry 和测试；
5. 可以保留清楚标注的 legacy demo；
6. 可以在代码中增加 `pending_teacher_decision`、TODO 和 capability flag；
7. 老师答复后再另开 implementation PR。
