# Round 6：Mission Demo 闭环变更与验收报告

日期：2026-09-05

分支：`codex/round6-mission-demo`

基线：`codex/round5-geometry-redesign@909cd20`（`main` 仍为 `4096144`）

## 验收结论

本轮保留 Round 5 的三套构型几何，不再增加 archetype 或装饰；主要目标已经从“手动调形状”收回到一条真正运行的任务闭环：

```text
选定已有 conventional preset + 输入 Demo 任务
    → 固定 seed 的 24 次原生参数评价
    → 当前 family registry Analyze
    → 透明 Demo 质量/航程计算
    → 可行优先、仅几何变量去重的 Top 3
    → 精确 GeometryState 预览
    → 候选原样送入 Analyze 复核
```

Formal Optimization 仍为 `optimization_spec_pending`。Demo profile、API、任务存储、文案和结果 provenance 均与 Formal/Legacy 隔离；临时边界、权重和任务模型没有被写成老师认可的工程结论。

## 实际修改

### 1. 独立、版本化 Demo profile

- 新增 `configs/rapid_design/mission_demo_v1.yaml`，固定 `mode=demo_only`、`formal_status=pending_teacher_decision`、profile ID/version、seed、预算、搜索变量、任务模型和指标覆盖。
- profile 只允许 `conventional_v2`，并把 7 个 evaluator 必需任务输入锁成精确 schema；缺失或多余输入在配置加载时直接失败。
- 8 个几何变量都是原生 `ConventionalV2Design` 字段；fuel 作为独立 sizing 变量，不会被伪装成几何参数。

### 2. 真实候选搜索与任务生命周期

- 新增 `/api/rapid-design/demo/config` 和独立的 create/status/SSE/result/cancel API。
- 每个候选都调用当前 registry Analyze，结果携带完整 design、sizing、condition、Analyze summary、Canonical `GeometryState`、`design_hash`、domain、constraints、score breakdown、warnings 和 provenance。
- 固定 seed 下执行 3 × 8 次评价；排序为 feasible-first、objective、stable candidate hash。
- Top 3 多样性只按 8 个几何变量计算，不允许仅靠燃油量不同占据多个候选位；测试要求三个 `design_hash` 唯一。
- 无可行点时返回明确的最小违约候选。BWB 和未知 preset 返回结构化 422，不做静默构型转换。
- 任务文件原子写入 `storage/rapid_design/demo_jobs/{job_id}/`，与 Legacy jobs 隔离。

### 3. Mission UI 与 Analyze 交接

- Mission 页面新增 `DEMO / NOT FORMAL / UNAPPROVED` 运行区，同时保留独立 Formal pending 卡和老师决策链接。
- 支持单任务创建、命名 SSE、轮询降级、协作式取消、失败展示、结果重试和 run token/sequence 旧响应隔离。
- Top 3 按后端 rank 展示，使用同一米制参考尺寸，预览不可单独拖动；卡片公开可行性、score、约束、指标、模型覆盖和 design hash。
- `constraint_penalty` 明确显示为“违约权重”，并另算“实际违约贡献”，避免把权重误读成已经扣除的分数。
- Mission 面板在切换 tab 后仍保持挂载，运行、SSE、取消和结果不会丢失。
- 当前 family/preset 或输入草稿改变时，旧任务仍按自身归属显示，并明确提示“下一次运行才使用当前选择”，不会把旧 Top 3 误标为新构型结果。
- 点击“在 Analyze 中检查”会写入候选完整 design 和结果工况，并只触发一次现有 Analyze 请求。

## 真实浏览器验收

验收任务：`9597b23b76444e3fbe52676dece669ef`

| 项目 | 实际结果 |
| --- | --- |
| Family / preset | `conventional_v2 / long_endurance_uav` |
| Profile | `mission_demo_v1 / 1.0.0` |
| Profile hash | `e66c3889d771f8c211fa468bc4e3228c72a96124df7d80661da40f60322a046b` |
| 搜索预算 | 24 次真实 Analyze 评价 |
| 无效评价 | 0 |
| Top 3 | 3 个可行候选、3 个不同 `design_hash` |
| 最小两两几何归一化距离 | `0.860716`（门槛 `0.18`） |
| 指标覆盖 | 10 connected / 6 partial / 6 not_connected |

候选结果摘要：

| Rank | 翼展 | 翼面积 | 后掠 | 概念起飞质量 | 概念航程 | 最大 L/D | Design hash |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 20.2 m | 22 m² | 3° | 1008.3 kg | 1738 km | 24.82 | `afc9ccb7d5…` |
| 2 | 15.0 m | 17 m² | 15° | 1057.9 kg | 1946 km | 19.26 | `777b751fd2…` |
| 3 | 18.7 m | 38 m² | 0° | 1476.8 kg | 1578 km | 18.62 | `54002134c1…` |

浏览器中选择了非 preset 默认几何的 Rank 2。Analyze 中 8 个搜索几何字段与候选逐项一致，工况仍为 2000 m / 220 km/h，页面显示 `分析已更新 · 777b751f`，与候选完整 hash `777b751fd2770622c011da5a84ac77499fa382b53d1f411c3d24ede476ce7521` 一致。随后切回 Mission，原任务与 Top 3 仍保留；切到 BWB 时页面明确显示“尚未接入”，并继续把旧结果标为 conventional/long_endurance_uav。

## 视觉与原始证据

- [Demo 输入与 Formal 分区](round6-visual-validation/mission-demo-input.png)
- [模型覆盖与三架同尺度候选](round6-visual-validation/mission-demo-top3.png)
- [最终可交互 Top 3 画面](round6-visual-validation/mission-demo-interactive-final.png)
- [候选约束、warnings 与 Analyze 操作](round6-visual-validation/mission-demo-candidate-actions.png)
- [Rank 2 进入 Analyze 的几何与参数](round6-visual-validation/mission-demo-candidate2-analyze.png)
- [Analyze hash 与派生几何量](round6-visual-validation/mission-demo-candidate2-analyze-hash.png)
- [BWB 未接入与旧结果归属提示](round6-visual-validation/mission-demo-bwb-not-connected.png)
- [浏览器 handoff 核对记录](round6-visual-validation/handoff-verification.json)
- [原始 request](round6-visual-validation/request.json)、[profile](round6-visual-validation/profile.json)、[status](round6-visual-validation/status.json)、[result](round6-visual-validation/result.json)

## 自动化验收

| 检查 | 结果 |
| --- | --- |
| 全量 Python 测试（UTF-8 模式） | `689 passed, 9 skipped` |
| 前端测试 | `212 passed, 0 failed` |
| Next.js production build + lint/typecheck | 通过 |
| 本轮 Python 文件 Ruff | 通过 |
| Git whitespace 检查 | 通过 |
| 只读交叉审查 | 无剩余 P0/P1/P2 |

新增测试覆盖 profile/Formal/Legacy 隔离、三 preset 的确定性 Top 3、多样性和有限 GeometryState、候选重新 Analyze 的 hash/geometry/summary 一致、not-connected 不入 score、无可行解、固定燃油端点、首评价前取消、API lifecycle/SSE/result/cancel/failure/文件归档、BWB/未知 preset 拒绝、前端真实结果解析、旧 run 隔离、共享尺度、handoff 和运行归属变化。

## 明确保留的模型边界

- 本轮接通的是透明、可替换的概念级 Demo evaluator，不是新的预训练整机 surrogate，也不是高保真 CFD。
- 翼型弯度分布、V-tail/T-tail 配平与操稳、静稳定裕度、推进匹配、螺旋桨/短舱/吊架干扰、结构应力、起降和噪声仍未完整接入；其中 `not_connected` 项绝不进入排序。
- Demo objective 当前在可行解中优先降低概念起飞质量；正式目标、范围、权重、Pareto、uncertainty 和验证标准仍待老师确认。
- 文件证据会保留，但当前 API runner 不在服务重启后重建内存 job 索引；旧 job ID 重启后不能继续查询。这不影响本轮搜索结果归档，但不是完整的跨重启任务恢复。
- 浏览器中的三架候选证明参数搜索、几何显示和 Analyze 交接闭环成立，不代表工程最优、认证可用或制造可行。

## 分阶段提交

1. `091f4d1` — `docs(rapid-design): define round 6 mission demo contract`
2. `1602906` — `feat(rapid-design): add mission demo candidate search`
3. `250498d` — `test(rapid-design): cover fixed demo sizing bounds`
4. `c311f06` — `fix(rapid-design): enforce geometric candidate diversity`
5. `f036c36` — `fix(rapid-design): validate demo evaluator inputs`
6. `143a889` — `feat(rapid-design): connect mission demo candidate workflow`
7. 本报告、技术说明和最终浏览器证据单独提交。
