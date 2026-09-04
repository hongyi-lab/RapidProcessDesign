# Rapid Process Design 第四轮变更报告

## 结果

Rapid Design 已从“BWB Analyze + 旧 conventional Optimize”改为 family-neutral 的整机设计工作台。`conventional_v2` 与 `bwb_v1` 现在通过同一个 family registry、Analyze API、Canonical `GeometryState` 和 Three.js renderer 工作；legacy optimizer 仍保留，但与新主路径明确隔离。

## 完成内容

### Family-neutral 后端

- 新增最小 Family Registry，只注册 `conventional_v2` 与 `bwb_v1`；
- 新增 family discovery 和 detail endpoints；
- `/analyze` 按 `family_id` 分发；
- 请求支持 preset defaults 加少量 override；
- 响应统一包含 `geometry_state`、`geometry_metrics`、`analysis`、`domain_status`、`warnings`、`provenance` 和 `fidelity`；
- 迁移期保留旧 `geometry`、`polar`、`summary` aliases，避免 BWB 客户端回归。

### Canonical GeometryState 与 renderer

- 支持 `loft_body`、`lifting_surface`、`nacelle`；
- 支持水平翼、垂尾、Y 对称和双短舱；
- 截面 loft 包含上下表面、翼根/翼尖和 body/nacelle 端盖；
- 支持 current/baseline、3D、顶视、侧视、前视；
- renderer 只读取 GeometryState，不读取任何 family-specific design vector；
- 更新和卸载时释放 Three.js geometry、material、texture 和 WebGL context。

### `conventional_v2`

| Preset | 主要几何语法 | 推进布局 |
|---|---|---|
| `long_endurance_uav` | 修长机身、高展弦比、低后掠、长尾臂 | rear pusher |
| `fast_cruise_recon` | 尖细机头、中等后掠、薄翼、紧凑尾部 | nose tractor |
| `payload_utility` | 饱满载荷舱、高翼、较大尾翼 | twin wing-mounted |

每个方案由 9 个机身截面、4 个主翼 section、三段平尾、三段垂尾及 preset-defined nacelle 组成。概念级 analysis adapter 清楚标注为低阶趋势模型，不声称经过 CFD、VSPAERO 或试验验证。

### UI

- 默认进入 `conventional_v2`，可无刷新切换三个 preset 或 `bwb_v1`；
- 参数控件、范围、单位、默认值均来自 family manifest；
- 参数变化后自动请求统一 Analyze endpoint；
- 显示几何合法性、派生指标、极曲线、适用域、模型、保真度和 provenance；
- 页面分为 `Analyze`、`Mission Design`、`Legacy Conventional Demo`；
- Mission Design 显示 `optimization_spec_pending` 并链接老师决策文档；
- Legacy 页面明确说明它不优化 Analyze 当前 family。

## 主要新文件

```text
services/api/app/services/rapid_design/families/
  base.py
  registry.py
  bwb_v1/
  conventional_v2/

apps/web/src/components/rapid-design/geometry/
  types.ts
  geometrySurfaces.ts
  threeGeometry.ts
  ParametricAircraftPreview.tsx

tests/api/test_rapid_design_families.py
apps/web/src/app/rapid-design/rapidDesignModel.test.ts
docs/teacher-decisions-optimization-spec-cn.md
```

## 验证

- Python 全量：`664 passed, 9 skipped`；
- Round 4 / BWB / legacy Rapid scoped：`28 passed`；
- 前端全量：`197 passed`；
- 通用 renderer 专项：`7 passed`；
- Ruff：通过；
- Next.js production build：通过；
- API 实测：两个 family、四个 preset 均返回 `geometry_status=valid`；
- 浏览器实测：family/preset 切换、参数修改后 design hash/面积更新、baseline、四视图、Mission pending 和 Legacy 隔离提示均正常；
- 视觉实测：三个 conventional preset 的机身饱满度、翼展、后掠、尾部和推进布局肉眼可区分。

Windows 运行完整 Python 测试时需要 `PYTHONUTF8=1`，否则仓库既有测试会用系统 GBK 打开 UTF-8 YAML；这不是本轮引入的失败。

## 未修改内容

`configs/rapid_design/demo.yaml` 中的优化目标、变量边界、penalty、population、iterations、质量模型、NeuralFoil 配置和 uncertainty 逻辑均未改动。

## 已知限制

- `conventional_v2` 和 `bwb_v1` 的 Analyze 均为概念级低阶比较模型；
- `conventional_v2` 的发动机数量与位置由 preset 决定，尚未进入 optimizer；
- 尚未实现跨 family 优化、top-K/Pareto、conformal/OOD 校准或 OpenVSP 导出；
- 当前只实现两个 family，没有扩展到 11 种布局；
- API 暂时保留旧 BWB aliases，待所有客户端迁移后再删除。

## 下一步依赖

老师需要先完成 [优化规范决策文档](teacher-decisions-optimization-spec-cn.md)，确认项目术语、第一版 family、目标、变量、边界、约束、surrogate、OpenVSP/VSPAERO 角色、算法预算、不确定性和论文验证标准。确认前不应把 Mission Design 接到正式 optimizer。
