# Codex 第四轮执行任务书

## 目标

基于当前 `hongyi-lab/RapidProcessDesign` HEAD，将 Rapid Design 从“BWB Analyze + 旧 conventional Optimize”重构为 family-neutral 的整机设计工作台。当前轮只解决产品定位、family registry、统一 GeometryState、通用渲染和高质量 `conventional_v2`；不自行决定正式优化参数。

## 开工前

1. 读取并总结以下文件的当前行为：
   - `apps/web/src/app/rapid-design/page.tsx`
   - `apps/web/src/app/rapid-design/rapidDesignModel.ts`
   - `apps/web/src/components/rapid-design/BwbThreePreview.tsx`
   - `apps/web/src/components/rapid-design/bwbGeometry.ts`
   - `services/api/app/schemas/rapid_design.py`
   - `services/api/app/routers/rapid_design.py`
   - `services/api/app/services/rapid_design/bwb_analysis.py`
   - `services/api/app/services/rapid_design/geometry_mapper.py`
   - `configs/rapid_design/demo.yaml`
2. 记录 HEAD、工作区状态和现有测试基线。
3. 创建 `docs/teacher-decisions-optimization-spec-cn.md`，内容参照本任务书同目录提供的模板。
4. 不修改任何正式优化目标、penalty、变量边界、population、iterations 或 uncertainty 逻辑。

## 必做修改

### 1. Family-neutral API

- 新增最小 family registry；
- 注册 `bwb_v1` 和 `conventional_v2`；
- 新增 family discovery endpoint；
- `/analyze` 根据 `family_id` dispatch；
- 返回统一 envelope，其中包含 `geometry_state`、metrics、analysis、domain、warnings 和 provenance；
- BWB 当前分析功能不得退化。

### 2. Canonical GeometryState

至少支持三类 component：

- `loft_body`
- `lifting_surface`
- `nacelle`

family decoder 负责把高层参数展开为 stations/sections；前端通用 renderer 只消费 GeometryState，不读取 BWB 或 conventional 的原始参数。

### 3. Generic Three.js renderer

- body cross-section loft；
- lifting-surface section loft；
- symmetry；
- top/bottom surfaces；
- normals；
- tip/root closure；
- baseline overlay；
- perspective/top/side/front views；
- dispose geometry/material correctly。

正式新路径禁止使用 CapsuleGeometry、固定厚度 BoxGeometry 或一块梯形板作为最终飞机。

### 4. conventional_v2

实现三个 presets：

- `long_endurance_uav`
- `fast_cruise_recon`
- `payload_utility`

实现：

- 8+ 机身截面；
- 4+ 主翼站位；
- 水平和垂直尾翼 loft；
- 可选 preset-defined nacelle placement；
- 几何合法性检查；
- 手动 Analyze controls。

本轮只需概念级 analysis adapter，并在 UI 清楚标注 fidelity。不得自行声称结果经过高保真验证。

### 5. UI

- 删除产品级 BWB 硬编码；
- 增加 family 和 preset selector；
- 控件由 manifest 动态生成；
- Analyze 使用通用 renderer；
- 保留 baseline/current 比较；
- 旧 Optimize 改为 `Legacy Conventional Demo` 或移到独立路径；
- 新 Mission Design 显示 `optimization_spec_pending`，链接到老师决策文档。

## 不做

- 不接 11 个布局；
- 不做跨 family 自动优化；
- 不改变 legacy optimizer 数值；
- 不设计 Pareto 权重；
- 不实现 conformal；
- 不复制无明确许可的外部模型、数据和权重；
- 不为了视觉差异随机扭曲几何。

## 测试

1. registry dispatch tests；
2. schema validation tests；
3. BWB regression；
4. conventional 每个 preset 的 geometry invariant tests；
5. parameter sensitivity tests；
6. renderer unit tests；
7. golden screenshots：四视图 × 三个 conventional presets + BWB；
8. existing backend/frontend tests；
9. production build。

## 验收

- 同一个 Analyze 页面可切换 BWB 与 conventional；
- conventional 三个 presets 轮廓明显不同且仍像可制造的常规飞机；
- 所有几何来自 GeometryState；
- 页面不误导用户认为旧 optimizer 优化了当前 family；
- 老师待确认项全部单独记录，代码未自行拍板；
- 测试和 build 通过；
- 输出一份变更报告，列出新文件、修改文件、测试结果、已知限制和下一步依赖老师的决定。
