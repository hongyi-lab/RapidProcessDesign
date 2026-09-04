# RapidProcessDesign 第四轮修改建议

## 从“BWB Analyze + 旧 Conventional Optimize”改成通用整机设计工作台

> 日期：2026-09-04  
> 审阅仓库：`hongyi-lab/RapidProcessDesign`  
> 当前基线：`72b26a9 feat: add interactive BWB rapid design analysis`  
> 本轮目标：先解决产品定位、几何表达、模块接口和界面一致性；优化目标、变量边界、约束权重、算法选择及不确定性方法暂不定，由老师确认后再实现。

---

## 0. 本轮结论

当前系统已经证明了两件事：

1. `bwb_v1` 可以用连续参数生成光顺外形，并在 Analyze 页面联动低阶气动曲线；
2. 原有 conventional 流程可以接收任务参数并运行一个后台优化任务。

但这两件事目前没有形成同一套产品：

```text
Analyze  = BWB 几何 + BWB 低阶分析
Optimize = 旧 conventional 模板 + 旧优化器 + 积木式 CAD 预览
```

所以第四轮不应继续分别打磨两个页面，而应先完成以下结构调整：

> **把项目改成 family-neutral 的整机设计工作台；保留 BWB 作为一个 family，新建高质量 `conventional_v2`，让两者共享同一套几何契约、渲染器、Analyze 页面和未来优化接口。**

本轮不需要决定“最优目标到底是什么”“哪些变量该优化”“惩罚系数取多少”。这些问题单独整理为老师决策文档，不阻塞几何和 pipeline 的重构。

---

## 1. 当前仓库最需要修正的四个问题

### 1.1 产品和界面仍被写死成 BWB

当前 Rapid 页面标题、说明和 family 标识均直接写成 BWB；前端的 `toAnalyzePayload()` 固定发送 `family_id: "bwb_v1"`，后端 `RapidAnalyzeRequest` 也只接受这一种 literal，路由则直接调用 `analyze_bwb()`。

这意味着当前代码不是“整机设计平台中已实现了一个 BWB family”，而是“整个 Analyze 功能本身就是 BWB”。继续添加第二个 family 会迫使大量 `if family === ...` 散落在页面和 API 中。

### 1.2 Analyze 和 Optimize 使用不同的飞机

Analyze 操作的是 `BwbDesignVariables`；Optimize 仍读取 `configs/rapid_design/demo.yaml` 中的旧 conventional 变量，并通过 `geometry_mapper.py` 固定输出：

- conventional；
- 上单翼；
- 单一梯形翼；
- 常规尾翼；
- 单台机头发动机；
- 固定上反角。

因此用户在 Analyze 中看到的外形和点击 Optimize 后得到的外形不是同一设计空间。这个问题比“某个参数值不合理”更严重，因为它会让用户误以为系统优化了屏幕上的 BWB，实际上没有。

### 1.3 当前 conventional 的几何 schema 太贫乏

旧 `AircraftSpec` 适合描述一个大致布局，但不足以作为高质量整机几何的唯一真相。它只有机身长度和最大直径、主翼根梢弦长及少量布局字段，无法表达：

- 机头、座舱/载荷舱、后机身和尾锥的连续轮廓；
- 多折点、多站位机翼；
- 展向弦长、后掠、扭转、上反和厚度变化；
- 平尾、垂尾的真实站位、尺寸和轮廓；
- 发动机吊舱和连接整流；
- 部件相交、连接和包装关系。

所以旧 conventional 即使数值变化，外观也只能是圆柱、平板和盒子的重新缩放。

### 1.4 BWB 已经有较好的几何实现，但仍是 family-specific

`bwbGeometry.ts` 已经使用多个控制站、形状保持插值、上下表面厚度分布和真实 mesh loft。这部分应当保留，并作为通用 loft renderer 的技术原型。

但当前前端有一套 BWB decoder，后端 `bwb_analysis.py` 又维护一套与浏览器匹配的几何计算。第二个、第三个 family 到来后继续复制这种结构，会形成跨语言漂移风险。

---

## 2. 第四轮的实施边界

### 2.1 本轮要完成

1. family-neutral 产品结构；
2. 最小 Configuration/Family Registry；
3. 通用 `GeometryState` 数据契约；
4. 通用 loft renderer；
5. 高质量 `conventional_v2` 几何 family；
6. 把现有 `bwb_v1` 迁移进同一套 family 接口；
7. Analyze 页面支持 family、preset、连续参数和 baseline 对比；
8. 将旧 Optimize 明确隔离为 legacy，避免与新 Analyze 混为一体；
9. 新增单独的老师决策文档，记录尚未确定的优化问题。

### 2.2 本轮暂不完成

以下内容不要由 Codex 自行决定：

- 主优化目标及多目标权重；
- 哪些任务量是输入、约束或目标；
- 每个 family 的最终优化变量和上下界；
- 尾容积、稳定裕度、结构、容积等约束阈值；
- differential evolution、gradient-based、Bayesian optimization 或其他算法的最终选择；
- population、iteration、penalty coefficient；
- top-K/Pareto 的正式筛选规则；
- confidence interval、conformal prediction、OOD 阈值；
- 最终采用哪些外部 surrogate、模型权重及校准方法。

这些全部进入 `docs/teacher-decisions-optimization-spec-cn.md`，代码中只能保留清楚的接口或 `pending_teacher_decision` 状态，不能把临时值包装成已确认设计规范。

---

## 3. 推荐的新架构

```text
Rapid Design Web App
│
├── Family Selector
│     ├── conventional_v2
│     └── bwb_v1
│
├── Family Manifest
│     ├── 名称、说明、版本
│     ├── presets
│     ├── 参数定义和单位
│     ├── 几何合法性规则
│     ├── 当前分析模型说明
│     └── optimization_status
│
├── Canonical Design State
│     ├── family_id
│     ├── preset_id
│     ├── design_parameters
│     └── operating_condition
│
├── Family Decoder
│     └── Design State → GeometryState
│
├── Generic Geometry Renderer
│     └── GeometryState → Three.js mesh
│
├── Analyze Adapter
│     └── Design State → performance / polar / warnings
│
└── Future Optimize Adapter
      └── Mission → family-specific candidate set
```

### 3.1 最小 family 目录

不要一开始构造过度复杂的插件系统，但至少应把 family-specific 逻辑集中到固定位置：

```text
services/api/app/services/rapid_design/families/
  registry.py
  base.py
  bwb_v1/
    manifest.py
    geometry.py
    analysis.py
    presets.py
  conventional_v2/
    manifest.py
    geometry.py
    analysis.py
    presets.py

apps/web/src/components/rapid-design/
  geometry/
    types.ts
    LoftBody.ts
    LoftLiftingSurface.ts
    ParametricAircraftPreview.tsx
  families/
    familyTypes.ts
    familyControls.tsx
```

后端 registry 第一版只注册两个 family。不要现在一次接入 11 种布局。

---

## 4. 新的 canonical `GeometryState`

### 4.1 为什么需要它

优化参数、后端分析、浏览器几何和未来 OpenVSP 导出必须描述同一架飞机。不能继续让：

```text
优化器看 design vector A
前端看简化 AircraftSpec B
OpenVSP 再看另一套 defaults C
```

新的 `GeometryState` 应由 family decoder 生成，然后成为几何层的唯一真相。

### 4.2 建议结构

```json
{
  "family_id": "conventional_v2",
  "geometry_version": "0.1.0",
  "components": [
    {
      "id": "fuselage",
      "kind": "loft_body",
      "stations": [
        {
          "x_m": 0.0,
          "width_m": 0.05,
          "height_m": 0.05,
          "z_offset_m": 0.0,
          "shape_exponent": 2.0
        }
      ]
    },
    {
      "id": "main_wing",
      "kind": "lifting_surface",
      "symmetry": "y",
      "sections": [
        {
          "y_m": 0.0,
          "leading_edge_x_m": 2.5,
          "leading_edge_z_m": 0.2,
          "chord_m": 1.5,
          "twist_deg": 1.0,
          "dihedral_deg": 0.0,
          "thickness_ratio": 0.14,
          "airfoil_id": "naca2414"
        }
      ]
    }
  ],
  "derived_metrics": {},
  "geometry_checks": [],
  "provenance": {}
}
```

### 4.3 数据流建议

当前页面已经在参数变化后以 200 ms debounce 请求后端，因此第四轮可以让 `/analyze` 响应直接携带 `geometry_state`。前端不再自己解释各 family 的高层参数，只负责通用 loft。

这样：

- family-specific 参数 → 几何控制站的映射只在后端维护一次；
- 前端 renderer 只认识 `loft_body`、`lifting_surface` 和 `nacelle`；
- BWB 与 conventional 可以共享同一 renderer；
- 后面添加 OpenVSP exporter 时也消费同一 `GeometryState`。

不建议让每个 family 都新写一套完整 Three.js 组件。

---

## 5. `conventional_v2` 应该怎么做

### 5.1 不要把“conventional”理解成只有一种飞机

conventional 只表示主要拓扑仍然是机身、主翼和尾翼，并不意味着外形必须相同。第一版建议提供三个工程 archetype，作为离散 preset，而不是暂时交给 optimizer 决定：

| Preset | 视觉与工程特征 |
|---|---|
| `long_endurance_uav` | 修长机身、高展弦比、低后掠、长尾臂、较小翼载 |
| `fast_cruise_recon` | 尖细机头、中等后掠、较薄机翼、较短机身和尾臂 |
| `payload_utility` | 更饱满的载荷舱、高翼、较低展弦比、较大尾翼、可配置双发吊舱 |

这些 preset 只是几何和初始状态，不是老师尚未确认的优化结论。

### 5.2 机身：多截面 loft

建议至少 8 个标准化站位：

```text
nose tip
nose transition
forward cabin
maximum section
wing carry-through
aft cabin
tail-cone shoulder
tail tip
```

高层参数可以先限制在 5–7 个：

- `fuselage_length_m`
- `fineness_ratio`
- `nose_length_ratio`
- `cabin_fullness`
- `tailcone_length_ratio`
- `section_ovality`
- `vertical_offset_profile`

family decoder 再将其展开为完整截面数组。不要给用户几十个独立截面滑块。

### 5.3 主翼：多站位 lifting-surface loft

建议至少四个半翼站位：

```text
root
inner kink
outer kink
tip
```

高层参数：

- span 或 area + aspect ratio；
- wing root x-position；
- wing vertical position；
- kink span ratios；
- inner/outer taper；
- inner/outer sweep；
- dihedral；
- root/tip twist；
- root/tip thickness ratio。

Renderer 根据每一站的真实 section loft 上下表面，不再使用固定厚度 `ExtrudeGeometry`。

### 5.4 尾翼

本轮先由 preset 和简单几何规则生成，不正式确定优化公式：

- 水平尾翼和垂直尾翼均使用 3 个 section；
- 尾臂、面积、展弦比、后掠和安装位置可显示及手动调整；
- 尾容积系数的正式默认值和约束范围放入老师文档；
- 不允许 Codex自行声称“某个数值最优”。

### 5.5 发动机和布局

发动机数量和位置会改变拓扑。第四轮可作为 preset 属性：

- nose tractor；
- rear pusher；
- twin wing-mounted。

不要把 engine count 做成连续滑块，也暂不让 optimizer 自动决定。

### 5.6 简单但必要的“像飞机”规则

这些属于几何合法性，不需要等待老师确认：

- 所有截面尺寸必须为正；
- 机身宽高沿 x 连续变化；
- 机头和尾端必须闭合；
- 主翼 chord 必须正且展向变化光顺；
- 翼面不得与尾翼明显穿插；
- 发动机不能埋入错误部件；
- 左右对称组件必须严格镜像；
- mesh 不含 NaN、翻面和未闭合尖端；
- 不合法参数返回明确 validation error，而不是悄悄 clamp 成另一架飞机。

---

## 6. BWB 的处理方式

BWB 不应删除，也不应继续代表整个产品。

### 6.1 保留

- 当前 12 个 BWB 设计参数；
- 多控制站 planform；
- shape-preserving interpolation；
- thickness/twist loft；
- baseline 对比；
- 当前 Analyze 曲线与 provenance。

### 6.2 修改

- `BwbThreePreview` 逐步替换为通用 `ParametricAircraftPreview`；
- BWB decoder 输出统一 `GeometryState`；
- 页面不再直接 import `BwbDesignVariables` 作为整个 Rapid 页面的状态类型；
- `RapidAnalyzeRequest` 改为 discriminated union 或 registry dispatch；
- BWB 页面文案变成当前 family 的动态文案，而非产品名称。

### 6.3 不做

当前 `bwb_analysis.py` 是 clean-room low-order model。第四轮不应花时间把它包装成正式 surrogate，也不应擅自调参提高看起来的性能；只保持其“pipeline smoke test / conceptual comparison”定位。

---

## 7. UI 修改建议

### 7.1 顶部

将：

```text
Rapid Process Design
Blended-wing-body concept workspace
bwb_v1
```

改成：

```text
Rapid Process Design
Overall Aircraft Design Workbench
Family: Conventional V2 / BWB V1
```

“OAD”是否为老师原话，需要在老师文档中确认；产品界面暂时可写完整英文，避免把未确认缩写写死。

### 7.2 左侧输入

依次显示：

1. Family selector；
2. Preset selector；
3. Geometry parameters；
4. Flight condition；
5. Reset / Set baseline。

参数列表由 family manifest 动态生成，不再在 `rapidDesignModel.ts` 中硬编码 BWB 数组。

### 7.3 中部几何

- 当前设计实体；
- baseline 轮廓或透明表面；
- 3D、顶视、侧视、前视；
- 可选显示 section stations；
- 显示 `geometry_status: valid/invalid`。

### 7.4 Analyze 与 Optimize

第四轮建议：

- `Analyze`：作为新架构主路径；
- `Mission Design`：暂时显示“优化规范待老师确认”；
- 旧 conventional Optimize 移到 `Legacy Demo` 折叠区或独立路径，不再让它看起来像在优化当前选中的 family。

保留旧功能是为了回归和展示已有 pipeline，不是继续把它作为新架构的正式结果。

---

## 8. API 调整

### 8.1 新增 family discovery

```text
GET /api/rapid-design/families
GET /api/rapid-design/families/{family_id}
```

返回：

- family metadata；
- presets；
- parameter definitions；
- available capabilities：`geometry`, `analyze`, `optimize`；
- model/fidelity/provenance；
- optimization status。

### 8.2 泛化 Analyze

```text
POST /api/rapid-design/analyze
```

请求：

```json
{
  "family_id": "conventional_v2",
  "preset_id": "long_endurance_uav",
  "design": {},
  "condition": {}
}
```

响应：

```json
{
  "family_id": "conventional_v2",
  "design_hash": "...",
  "geometry_state": {},
  "geometry_metrics": {},
  "analysis": {},
  "domain_status": {},
  "warnings": [],
  "provenance": {}
}
```

不同 family 可以暂时返回不同分析字段，但 envelope 必须统一。不要把 `BwbGeometryMetrics` 和 `BwbAircraftPolar` 作为全局 API 名称。

### 8.3 Optimize 暂时不泛化数值逻辑

可以先定义接口形状，但不实现老师尚未确认的优化规范：

```text
POST /api/rapid-design/optimize
→ 409 optimization_spec_pending
```

或者在 UI 中暂时不调用新接口。旧 `/jobs` 路由保留为 legacy。

---

## 9. 代码级修改清单

### 后端

1. `services/api/app/schemas/rapid_design.py`
   - 新增 family-neutral request/response envelope；
   - 新增 `ConventionalV2Design`；
   - 新增通用 `GeometryState` schema；
   - 保留 BWB 类型作为 family internal schema。

2. `services/api/app/routers/rapid_design.py`
   - 不再直接 import/call `analyze_bwb`；
   - 通过 registry dispatch；
   - 新增 family discovery endpoint。

3. 新增 `services/api/app/services/rapid_design/families/`
   - `registry.py`
   - `bwb_v1/`
   - `conventional_v2/`

4. `services/api/app/services/rapid_design/bwb_analysis.py`
   - 拆入 family 目录；
   - 返回统一 envelope 和 `geometry_state`。

5. `services/api/app/services/rapid_design/geometry_mapper.py`
   - 标记为 legacy；
   - 不再作为新 conventional family 的 decoder。

6. `configs/rapid_design/demo.yaml`
   - 改名或注明 `legacy_conventional_v1`；
   - 不再被 family-neutral Analyze 页面当成总配置。

### 前端

1. `apps/web/src/app/rapid-design/page.tsx`
   - 去掉 BWB 产品级硬编码；
   - 增加 family/preset selector；
   - 参数控件从 manifest 动态生成；
   - 新 Analyze 使用 `geometry_state`；
   - 将旧 Optimize 明确标为 Legacy 或暂时隐藏。

2. `apps/web/src/app/rapid-design/rapidDesignModel.ts`
   - 不再 import `BwbDesignVariables` 作为全局设计类型；
   - 新增 `FamilyManifest`, `DesignState`, `GeometryState`, `AnalyzeEnvelope`。

3. `apps/web/src/components/rapid-design/BwbThreePreview.tsx`
   - 保留到通用 renderer 完成；
   - 之后变为薄包装或删除。

4. 新增 generic loft renderer
   - body loft；
   - lifting-surface loft；
   - nacelle loft；
   - component assembly；
   - baseline overlay。

---

## 10. Codex 建议执行顺序

### Phase 0：只读复核和文档

- 确认 HEAD 与工作区；
- 写 `docs/rapid-design-fourth-round-plan-cn.md`；
- 单独写 `docs/teacher-decisions-optimization-spec-cn.md`；
- 不修改优化参数。

### Phase 1：family-neutral contract

- 新增 registry 和 manifest；
- 泛化 Analyze request/response；
- 将现有 BWB 接入 registry；
- 保证 BWB 现有功能和测试不退化。

### Phase 2：通用 GeometryState 和 renderer

- 定义 component schema；
- Analyze 返回 geometry control data；
- renderer 消费通用 component，不读取 family-specific design vector；
- 将 BWB 迁移到通用 renderer。

### Phase 3：`conventional_v2`

- 实现三个 preset；
- 实现机身、主翼、尾翼、吊舱 loft；
- 实现几何合法性检查；
- 暂时使用清楚标注的低阶/placeholder analysis adapter，不擅自确定优化模型。

### Phase 4：UI 一致化

- family/preset selector；
- dynamic controls；
- baseline；
- 视角；
- capability 和 fidelity 标签；
- Legacy Optimize 隔离。

### Phase 5：测试与视觉验收

- 后端 schema/registry/geometry tests；
- 前端 renderer tests；
- 参数 sensitivity tests；
- 三个 preset 的 golden screenshots；
- BWB regression；
- build/test 全部通过。

---

## 11. 验收标准

### 架构

- 页面中不存在产品级写死的 `bwb_v1`；
- `/analyze` 至少支持 `bwb_v1` 与 `conventional_v2`；
- family-specific 参数不进入通用 renderer；
- old conventional optimizer 被明确标为 legacy；
- 新代码没有擅自确定老师未确认的优化设置。

### 几何

- 正式结果不再使用 Capsule + Box + 固定厚度平板；
- conventional 三个 preset 在顶视和侧视上肉眼明显不同；
- 每个暴露参数均有 sensitivity test，修改参数时对应 geometry metric 或顶点必须变化；
- mesh 无 NaN、明显翻面、开裂、部件漂浮和严重穿插；
- baseline/current 可叠加比较。

### 交互

- family 切换不刷新整页；
- 参数改变后 200–500 ms 内更新几何和分析状态；
- 非法参数给出具体原因；
- 清楚展示 family、model、fidelity 和 capability。

### 文档

- 单独存在老师决策文档；
- 所有待确认项标记为 `PENDING TEACHER DECISION`；
- 不把当前临时 demo 数值写成工程规范。

---

## 12. 最终建议

第四轮不要继续在旧 conventional 飞机上加材质、扩大滑块范围或随机改变比例，也不要把项目再次收缩成 BWB 工具。

最合理的方向是：

```text
通用整机工作台
+ 两个 family
  - conventional_v2：真实多截面、多站位、可产生明显不同常规飞机
  - bwb_v1：保留现有连续 BWB 证明
+ 同一 GeometryState
+ 同一 Analyze UI
+ 优化规范单独等待老师确认
```

这轮完成后，项目即使还没有最终优化算法，也已经具备一个可靠的工程骨架：老师只要确认目标、约束、变量范围和 surrogate，后续就能把优化模块插入，而不需要再次推翻几何和前端。
