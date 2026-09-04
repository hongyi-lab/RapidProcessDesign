# Round 6：Mission Demo 闭环契约

基线：`codex/round5-geometry-redesign@909cd20`。

## 本轮唯一主目标

让用户选择一个现有 `conventional_v2` preset 并输入已经支持的任务参数后，程序真实搜索连续设计参数，返回多个可追溯候选；每个候选必须由当前 Canonical `GeometryState` 显示，并能原样送入 Analyze 复核。

```text
selected preset + demo mission inputs
                ↓
versioned DemoSearchProfile
                ↓
deterministic parameter search
                ↓
replaceable conceptual evaluator
                ↓
ranked and diverse candidate set
                ↓
exact GeometryState preview
                ↓
handoff to Analyze with matching design_hash
```

## Demo 与 Formal 的硬隔离

- `Formal Optimization` 保持 `pending_teacher_decision`，family manifest 的正式 `capabilities.optimize` 仍为 `false`。
- `Demo Search` 使用独立配置、API 命名空间、存储目录、profile ID、版本、hash、模型 provenance 和结果语义。
- 每个 Demo request/result 都必须携带 `mode=demo` 或等价的强类型标记，并显示 `DEMO / NOT FORMAL / UNAPPROVED ASSUMPTIONS`。
- Demo 配置中的目标、边界、penalty、seed、预算、质量和航程系数都不写回老师决策表，不代表老师批准。
- 第一版只支持 `conventional_v2`，且用户先固定一个 preset 后再搜索；不自动跨 family 宣布最优。`bwb_v1` 明确显示未接入，不能静默转换。
- Legacy Conventional Demo 保留用于回归，不作为新候选几何的真相来源。

## 候选与排名契约

每个候选至少包含：稳定 candidate ID、rank、family、preset、完整原生设计向量、额外 sizing 变量、任务工况、可行性、objective、score breakdown、约束余量、模型指标、完整 `GeometryState`、`design_hash`、domain status、warnings 和 provenance。

搜索必须执行多次真实评价并记录 function-evaluation 数；不能从三个 preset 中直接挑一个冒充搜索结果。固定输入、profile 与 seed 时，候选 ID 和排序必须可复现。

排序语义：

1. 可行候选优先；
2. 只使用 Demo profile 中声明为已接入的指标和约束；
3. 无可行点时返回最小违约候选并明确标记；
4. 通过归一化设计向量距离去重，避免 Top-3 只是同一点的小数扰动；
5. UI 使用“Demo 排名”或“当前预算下候选”，不得使用“正式最优”或“全局最优”。

## 指标接入状态

每项指标必须声明为 `connected`、`partial` 或 `not_connected`，并说明原因。

- `connected`：当前 evaluator 实际读取并进入评分的面积、展弦比、后掠、梢根比、机身尺度、燃油、概念质量、概念航程等。
- `partial`：尾翼只通过总湿表面积代理进入阻力/质量，推进只通过低阶数量或固定质量进入，二维翼型结果只作为有限翼修正的一部分等。
- `not_connected`：V-tail/T-tail 对配平与操稳、静稳定裕度、真实推进匹配、螺旋桨/短舱/吊架干扰、结构应力、起降、噪声、热、CFD 级流动细节及未经实现的不确定性。

`partial` 和 `not_connected` 不能被 UI 文案暗示为完整工程模型；`not_connected` 绝不进入排序。

## UI 与状态流

- Mission 页面同时显示可运行的 Demo Search 和不可运行的 Formal Optimization 状态卡。
- Demo 输入保留用户选择；新任务必须清理旧候选、旧错误与旧选择，并忽略迟到事件。
- 状态至少覆盖 `idle → submitting → queued → running → cancelling → succeeded | failed | cancelled`。
- 结果读取失败必须可以重试；任务失败、Demo 结果读取失败和候选 Analyze 失败分别显示。
- 候选小图共享尺度并禁止单独拖动，避免视觉比较失真。
- “在 Analyze 中检查”必须写入候选的精确 family、preset、design 和条件，再由现有 Analyze API 重新计算；新结果的 `design_hash` 必须与候选一致。

## 本轮明确不做

- 不继续增加新构型、装饰、renderer 或相机系统。
- 不创建通用工作流引擎或重写现有 family registry。
- 不填写老师尚未决定的正式目标、范围、权重、Pareto、uncertainty 或论文验证标准。
- 不把 Demo evaluator 称为预训练整机 surrogate、高保真 CFD、认证或制造模型。
- 不破坏 Legacy、BWB 或现有 Analyze 行为。

## 验收门槛

### 自动化

- Demo profile 可加载且与 Formal 状态隔离；正式 optimize 仍不可用。
- 同输入与 seed 的 Top-3 可复现、ID 稳定且设计向量满足多样性阈值。
- 每个候选严格通过 family schema，`GeometryState` 有限且 `geometry_status=valid`。
- 未接入指标不出现在 score breakdown。
- 候选按同一条件重新调用 Analyze 后，family、preset、design 和 `design_hash` 完全一致。
- create/events/result/cancel、失败、无可行解和持久化有测试。
- Legacy jobs、BWB、Analyze、前端测试与 production build 全部回归通过。

### 浏览器端到端

- 选择 preset 并输入任务后，页面显示真实搜索进度和评价次数。
- 返回至少三个可见差异候选，使用相同尺度显示。
- 每个候选展示排名依据、可行/违约状态、profile、模型 provenance 和指标接入状态。
- 点击候选进入 Analyze，滑块、3D 几何和 `design_hash` 与候选一致。
- BWB、取消、无可行点和失败场景都有明确而不误导的状态。
- 保存最终页面截图以及对应 request、profile 和 result 证据。
