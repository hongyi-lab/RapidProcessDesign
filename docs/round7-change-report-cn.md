# RapidProcessDesign Round 7 变更与验证报告

> 主题：任务响应验证、结果可解释性与 Demo 可靠性
> 基线：`codex/round6-mission-demo` / `c0295c0`
> 开发分支：`codex/round7-task-response-reliability`
> 响应审计运行于：`c3f43f5`，运行前工作区干净
> 正式优化规范：仍为 `pending_teacher_decision`

## 1. 本轮结论

Round 7 没有增加飞机构型、优化算法或新的工程模型，而是把第六轮已经跑通的链路做成可重复验证、可恢复和可解释的 Demo：

`任务输入 → 固定 seed 候选搜索 → 当前 Analyze/质量/航程评价 → 约束与 feasible-first 排序 → GeometryState 展示 → Analyze 复核`

任务响应脚本实际完成 12 个案例、共 288 次评价（每例 24 次），没有发现输入未传入或状态串用问题。9 个案例返回 `feasible`，3 个返回 `no_feasible_solution_found`；所有案例都有 24 个有效评价、0 个无效评价。本次真实矩阵均找到了 3 个有差异候选；“仅有 1–2 个候选”和“零有效候选”的行为由定向测试覆盖，不能据此声称真实矩阵出现过这些情形。

原始证据位于 [`round7-task-response-validation`](round7-task-response-validation/)：

- `cases/*.json`：每个案例的完整输入、固定候选复算、搜索结果、候选、约束、评分和选择记录；
- `cases.csv`、`top_candidates.csv`、`evaluations.csv`：案例、Top-K 和逐评价表；
- `fixed_candidate_comparison.csv`：层次 A 对比；
- `input_response_classification.csv`：层次 B 与输入作用分类；
- `manifest.json`、`summary.json`：branch/HEAD、profile、seed、规则和汇总结论。

## 2. 12 案例矩阵

所有案例使用 `mission_demo_v1` v`1.0.0`、profile hash `e66c388…046b`、seed `2711` 和 `3 × 8` 评价预算；没有改变 seed、模型系数、边界或加入“任务到外形”的硬编码规则。

| 案例 | 唯一变化或用途 | 结果 | 有效/无效评价 | 满足 Demo 约束的有效候选 | 返回候选 | 排名变化 |
|---|---|---:|---:|---:|---:|---:|
| `baseline_long_endurance` | 长航时 preset 基准 | feasible | 24 / 0 | 6 | 3 | — |
| `baseline_fast_cruise` | 快速巡航 preset 基准 | feasible | 24 / 0 | 6 | 3 | — |
| `baseline_payload_utility` | 载荷运输 preset 基准 | feasible | 24 / 0 | 1 | 3 | — |
| `vary_required_range` | 航程 1000 → 1800 km | feasible | 24 / 0 | 1 | 3 | 是 |
| `vary_payload_mass` | 载荷 100 → 300 kg | feasible | 24 / 0 | 2 | 3 | 是 |
| `vary_cruise_speed` | 速度 220 → 320 km/h | feasible | 24 / 0 | 8 | 3 | 是 |
| `vary_cruise_altitude` | 高度 2000 → 6000 m | feasible | 24 / 0 | 6 | 3 | 否 |
| `vary_max_fuel` | 燃油上限 400 → 200 kg | no feasible | 24 / 0 | 0 | 3 | 是 |
| `vary_max_takeoff_mass` | 起飞质量上限 1600 → 900 kg | no feasible | 24 / 0 | 0 | 3 | 是 |
| `vary_target_lift_to_drag` | L/D 阈值 16 → 16.5 | feasible | 24 / 0 | 6 | 3 | 否 |
| `difficult_task` | 配置范围内的困难组合任务 | feasible | 24 / 0 | 2 | 3 | 是 |
| `no_feasible_task` | 配置范围内的刻意无可行解任务 | no feasible | 24 / 0 | 0 | 3 | 是 |

这里的“满足约束候选数”是 24 个有效评价中的数量，不代表已通过工程验证；返回 Top-K 也可能同时包含可行和不可行候选，前端现在逐项标注。

## 3. 两层任务响应观察

### A. 固定同一候选，只改变任务输入

七个单输入案例都使用长航时基准第一名的同一设计和同一 fuel sizing 复算。七例均保持相同 `design`、`sizing`、`GeometryState` 和 `geometry_fingerprint`，说明任务输入没有被偷偷改写成几何规则。

| 输入 | 实际进入的环节 | 固定候选观察 |
|---|---|---|
| `required_range_km` | 约束阈值 | 几何和任务指标不变；航程阈值及余量变化，并从满足变为不满足 |
| `payload_mass_kg` | 模型计算 | systems/empty/takeoff mass 与航程改变；设计和工况不变 |
| `cruise_speed_kmh` | Analyze 工况、气动与航程计算 | `cd0`、max L/D 和航程改变；约束仍满足，因此该固定候选 objective 未变 |
| `cruise_altitude_m` | Analyze 工况、气动与巡航诊断 | `cd0`、max L/D、航程及所需 CL 改变；约束仍满足，因此 objective 未变 |
| `max_fuel_mass_kg` | 约束阈值；完整搜索时也是 sampling 上界 | 固定 sizing 为 210 kg，不随输入改写；燃油约束从满足变为不满足 |
| `max_takeoff_mass_kg` | 约束阈值、质量 objective 归一化和违约惩罚 | 实际质量不变；阈值、余量和 objective 改变并转为不满足 |
| `target_lift_to_drag` | 约束阈值 | max L/D 不变；16 → 16.5 后约束仍未激活，objective 不变 |

`design_hash` 在速度和高度案例中发生变化，但实际几何及 `geometry_fingerprint` 均未变化。这验证了“hash 变化不能单独证明飞机改变”的判断；原有包含工况的 hash 契约没有修改。

### B. 使用相同 profile、算法和 seed 完整重搜

- 只有 `max_fuel_mass_kg` 改变了采样范围，因此只有该单输入案例改变候选池；其余输入在相同 seed 下保持同一采样池，但可以通过模型、约束或 objective 改变可行性和排序。
- 航程、载荷、速度、燃油上限和起飞质量上限触发了 Top-K/排名变化；这符合现有公式和 feasible-first 排序的预期。
- 高度改变了气动、航程和巡航诊断，但本次候选顺序没有改变，原因是模型响应不足以改变当前可行性/objective 顺序，并非传参失败。
- L/D 阈值 16 → 16.5 只改变阈值和余量；固定候选及当前候选池仍满足约束，因此 Top-K 保持不变。这是“约束没有激活”的显式案例，不是强求每次输入都生成不同飞机。
- 七个现有输入都观察到预期下游作用；`unconnected_existing_inputs=[]`，`possible_parameter_or_state_bugs=[]`。

困难任务仍找到 2 个满足已接入 Demo 约束的有效候选，Top-K 第三个候选被单独标为不满足。无可行任务的 24 个有效候选均不满足全部约束，第一名严格解释为“当前评分最优的未满足约束候选”，不声称是最小违约候选。

## 4. 工程问题修复

1. **可变候选数量**：多样性筛选只得到 1–2 个有效候选时返回已有结果和提示，不再为凑足三个而将任务判为异常；零有效候选返回 `no_valid_candidates`，有有效候选但无可行解返回 `no_feasible_solution_found`，未预期程序异常则使 job 进入 `failed / program_error`。
2. **资格与排序解释**：每个候选分别报告“几何有效”“是否满足当前 Demo 已接入约束”“工程验证未执行”。排序仍是 feasible-first，再按包含质量项和违约惩罚的 objective；没有修改算法来迎合文案。
3. **选择和排除证据**：结果记录 requested/returned/valid/feasible 数量、每个有效候选的 ranked position、是否入选、多样性距离及选择/排除原因。
4. **重启恢复**：runner 会校验既有 request/profile/status/result 文件的 job、输入、family/preset 和 profile hash 归属。完整结果可在服务重启后查询；没有结果的旧 queued/running/cancelling 任务转为 `interrupted`，明确 `resumable=false`，不自动重跑。
5. **前端可靠性**：支持 0/1/2/3 候选、混合可行性逐项标签、结构化错误、SSE 失败后的轮询、旧响应 token 隔离和已完成任务恢复入口。候选进入 Analyze 时继续使用该结果所属的 family、preset、原生 design 和运行工况，并校验候选与结果的 family/preset/condition 一致性。

## 5. 巡航一致性诊断

诊断以当前 Demo **起飞质量**为参考质量，使用同一高度、速度、气象密度和机翼参考面积计算所需 CL；只在 Analyze 已有 polar 的采样 CL 区间内寻找工作点并线性插值，不外推。

长航时基准第一名的 max L/D 为 `24.8209`，参考起飞状态匹配 L/D 为 `11.7502`，显示出原航程公式直接使用 max L/D 与指定状态工作点之间的差别。无可行任务第一名所需 CL 为 `9.7552`，而 polar 支持上限为 `0.8313`，因此返回 `unsupported / lift_not_supported`、匹配 L/D 为 `null`；系统没有退回 max L/D 冒充匹配值。

该诊断明确标记 `enters_score=false`、`enters_range_estimate=false`。现有 Breguet-style 航程仍使用 max L/D，以保持第六轮结果和排序可复现。本诊断不是配平、稳定性、推进匹配或任务积分验证。

## 6. 仍未解决的模型缺口

- 正式优化目标、变量范围、工程约束、预算、停止条件和多候选规则仍待老师确认；
- 翼型弯度、尾翼型式等新几何细节尚未被同等完整地纳入气动评价；
- 当前质量模型是透明低阶系数式，不是结构 sizing 或重量数据库模型；
- 推进只通过数量质量项部分接入，没有推力/功率/效率/干扰匹配；
- 航程仍使用固定等效 TSFC 与 max L/D，没有重量变化下的任务积分；
- 未接入完整配平、静/动稳定性、控制、结构、容积、起降和噪声验证；
- 本轮没有训练 surrogate、运行 CFD/FEA，亦不应把 Demo 可重复性表述成工程准确性。

老师待确认问题已压缩到 [`teacher-decisions-optimization-spec-cn.md`](teacher-decisions-optimization-spec-cn.md) 开头的一页摘要；原有项目均保持 pending，临时 Demo 可运行不代表获批。

## 7. 已运行的自动化验证

| 验证 | 实际结果 |
|---|---|
| Round 7 响应脚本 | 12/12 案例完成；288 次评价；`possible_parameter_or_state_bugs=[]` |
| Round 7 后端定向测试 | `19 passed`；覆盖 fingerprint、巡航匹配/不支持、部分/零候选、无可行文案、重启恢复、interrupted、归属和程序异常 |
| Python 全量测试 | `708 passed, 9 skipped` |
| 前端测试 | `216/216 passed` |
| Next.js production build | 通过 |
| Ruff / `git diff --check` | 通过 |

上述自动化通过只证明当前程序契约和回归状态，不证明候选已通过工程验证。

## 8. 真实浏览器验证

2026-09-05 在本地 production build 上使用应用内浏览器完成了完整路径；测试 job 为 `97d7a2fddf8044eaa6e2c33c9b347034`，family/preset 为 `conventional_v2 / payload_utility`。

1. 在 Mission Design 点击运行，界面收到 SSE 实时进度（捕获到 `running / 14% / 评估候选方案`），随后显示 `succeeded / 100%`。实际完成 24 次评价，返回 3 个候选，其中 1 个满足当前 Demo 已接入约束、2 个不满足；三者均明确显示“几何有效”和“工程验证未执行”。
2. 页面逐项展示 objective/评分分解、约束值与余量、选择原因、`design_hash`、`geometry_fingerprint` 和巡航一致性诊断。第一名 `demo-0f8c251c74ce2c421c45` 的 max L/D 为 `17.7105`，参考起飞状态匹配 L/D 为 `11.7804`，诊断明确不进入 score/航程。
3. 点击第一名“在 Analyze 中检查”后，Analyze 显示 `payload_utility`，工况为 `2000 m / 220 km/h / -4…12° / 25 samples`；设计值与结果原始文件一致，例如机身长 `15 m`、翼展 `15 m`、翼面积 `17 m²`、燃油 sizing `305 kg`。Analyze 返回 hash `e5295e74…58bd1`，与候选 `design_hash` 一致，几何可视化正常。
4. 刷新页面后，展开“恢复已完成任务”，可见该 job 及另一已完成任务；点击即可重新取得结果。
5. 使用项目自带脚本停止并重新启动 web/API 服务后，再次刷新并查询同一 job；恢复后的结果仍为 24 次评价、3 个候选、1 个可行候选，没有重新发起搜索。重启前后保存的 status 文件 SHA-256 均为 `DEDB3D9C…BE00B`，结果文件与重启后持久化文件 SHA-256 均为 `9CD272C2…0035`。

浏览器证据位于 [`round7-browser-validation`](round7-browser-validation/)：`01-mission-results.jpg`、`02-candidate-analyze.jpg`、`03-refresh-recovery.jpg`、`04-restart-recovered-result.jpg`，并保存了该 job 的 request/profile/status/result 原始 JSON 和 `browser-qa.json`。本次浏览器路径未发现失败步骤；页面中“Formal Optimization 待老师确认”的隔离提示仍然存在。
