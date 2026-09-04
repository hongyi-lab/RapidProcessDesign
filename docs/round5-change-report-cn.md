# Round 5 变更与验收报告

日期：2026-09-05

分支：`codex/round5-geometry-redesign`

对照基线：`main@4096144`

## 验收结论

本轮没有再把“参数不同”当成“构型不同”。三个 `conventional_v2` preset 已改为三套可识别的构型语法，并在同一画幅中完成 3D、顶视、侧视和前视对比：

| Preset | 构型语法 | 可见识别特征 | 公开比例锚点 |
| --- | --- | --- | --- |
| Long-endurance UAV | 长航时 MALE UAV | 高展弦比直翼、细长机身、上扬尾锥、V-tail、尾推螺旋桨 | USAF MQ-9 factsheet |
| Fast-cruise reconnaissance | 快速巡航单发侦察机 | 尖细机鼻、后掠翼、低翼、T-tail、前拉螺旋桨 | Daher TBM 960 |
| Payload utility | 载荷运输平台 | 宽深机身、高翼、双短舱/吊架/前拉螺旋桨、大常规尾翼 | Cessna SkyCourier |

公开资料只用于长度、翼展和构型语义的量级锚定；本项目没有复制任何 CAD、专有曲面或品牌外形。详细来源和基线根因见 [Round 5 几何红队审计](round5-geometry-audit-cn.md)。

## 实际修改

### 1. 参数与 archetype decoder

- 为三个 preset 分别定义机身站位、截面丰满度、鼻段、尾锥、翼面站位和尾翼布局，不再共用一套归一化母版。
- 将 `airfoil_id`、camber、局部 thickness、dihedral、twist、垂直面的 `y_m`、螺旋桨及吊架写入 family-neutral `GeometryState`。
- 为后推、前拉和双发推进系统生成显式 hub 与 blade；utility 构型增加左右对称的 engine pylon。
- manifest 升级到 `0.2.0`，为 preset 增加 archetype 和 reference provenance。

### 2. 通用 renderer

- 机身采用纵向单调 Hermite 重采样，减少原始站位之间的折段感。
- 翼面按展向重采样，并把局部翼型弯度、厚度、四分之一弦扭转和上反角真正作用到顶点坐标。
- 修复 V-tail 根部镜像、离中垂直面定位、螺旋桨绕序/闭合和资源释放问题。
- Three.js 场景更新改为事务式替换；异常和卸载路径都会释放 geometry、material 与 texture。

### 3. 相机与比较 UI

- 主预览提供透视 3D 与真实正交顶/侧/前视。
- 新增 `自动适配`、`统一米制`、`同机身长` 三种尺度模式；统一模式共享同一个参考画幅。
- 三个 conventional preset 在同一联动画布中并排显示，迷你预览禁用独立拖动，避免“共享视角”在交互后失真。
- 新增 17 个 manifest 几何参数的 Min / Default / Max 敏感性检查器；切换参数时先清空旧结果，并忽略与几何无关的飞行工况变化。
- 相机参考尺寸直接来自当前实际 `GeometryState`；无独立机身的 BWB 使用 canonical 纵向包络，因此归一化时不再被裁切或缩到不可见。
- 主预览中的 baseline 与相机取景使用相同的 family-only 显示条件；飞行工况一致性只约束气动指标比较。

### 4. 测试与稳定性

- 后端新增三个 archetype 的推进器数量/方向、吊架安装、组件 ID、有限数值、几何检查和 17 个参数 Min/Default/Max 变形覆盖。
- 前端新增 body loft、camber、dihedral、V-tail、propeller、pylon、资源释放、世界尺度、归一化尺度、正交画幅和 BWB fallback 测试。
- `ConversationIndex` 的更新时间改为严格单调 UTC 时间戳，消除 Windows 粗粒度时钟导致的全量测试偶发排序失败；业务数据格式没有改变。

## 视觉证据

基线证据位于 [`before/`](round5-visual-validation/before/)，其中三个 preset 在 auto-fit 下仍明显像同一母版换比例。

- [三构型 3D](round5-visual-validation/conventional-three-presets-3d.png)
- [三构型顶视](round5-visual-validation/conventional-three-presets-top.png)
- [三构型侧视](round5-visual-validation/conventional-three-presets-side.png)
- [三构型前视](round5-visual-validation/conventional-three-presets-front.png)
- [统一米制对比](round5-visual-validation/same-world-scale-comparison.png)
- [同机身长归一化对比](round5-visual-validation/normalized-silhouette-comparison.png)
- [参数敏感性网格](round5-visual-validation/parameter-sensitivity-grid.png)
- [BWB 回归](round5-visual-validation/bwb-regression.png)

## 自动化验收结果

| 检查 | 结果 |
| --- | --- |
| 全量后端测试（Python UTF-8 模式） | `674 passed, 9 skipped` |
| 前端测试 | `206 passed, 0 failed` |
| Next.js production build + TypeScript | 通过 |
| 本轮变更 Python 文件 Ruff | 通过 |
| Git whitespace 检查 | 通过 |
| 浏览器实际页面 | conventional 三构型、三种尺度、四个视图、敏感性网格和 BWB 均人工复核 |

Windows 默认 GBK 模式会让仓库中若干 UTF-8 YAML 测试夹具在读取阶段报错；使用 Python 的 UTF-8 模式后全量测试通过。前端测试脚本主要覆盖纯 TypeScript 逻辑；React 组件由 production build/typecheck 和本轮浏览器验收补足。

## 明确保留未改的范围

本轮没有修改正式优化器的目标函数、变量选择、上下界、penalty、Differential Evolution、Pareto、conformal、uncertainty，也没有改变 family registry、Legacy Conventional Demo、启动脚本或 BWB decoder。新比较面板只调用既有 family-neutral analyze API。

## 已知边界

- 当前翼型是 NACA 四位数均值线与低阶厚度模型，不支持任意实测翼型坐标。
- 翼根整流、座舱/设备鼓包和吊架仍是相交 loft/component，不是经过布尔融合并满足 C1/C2 连续性的制造级曲面。
- 几何 checks 能覆盖有限值、顺序、连接和基础间隙，不能替代严格自交、曲率、结构或推进安全验证。
- 气动分析仍是项目现有的概念级低阶模型；这些图和指标不可用于认证或详细设计结论。
- 仓库级 `ruff check .` 仍有既存历史告警；本轮只保证所有实际修改的 Python 文件通过 Ruff，避免顺手改动无关模块。

## 分阶段提交

1. `7eaa85f` — `docs(rapid-design): add round 5 red-team audit evidence`
2. `b58fda5` — `feat(rapid-design): add distinct conventional archetype grammars`
3. `833dbda` — `feat(rapid-design): upgrade renderer and visual comparison`
4. 本报告与最终视觉验收包单独提交。
