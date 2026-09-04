# RapidProcessDesign 第三轮分析：从“积木飞机”到整机 Webfoil

> 日期：2026-09-03
> 本地代码基线：`8115933`
> 范围：复核 V2 报告及其评价、回查当前代码、分析 MIT BWB Demo 与公开模型、确定下一轮架构和界面方向。
> 本文是分析和实施建议，不是已经完成的功能清单。

核读材料：

- 用户提供的 `RapidProcessDesign_Webfoil_WholeAircraft_V2_Analysis_CN.md`；
- 用户提供的评价与复核意见；
- RapidProcessDesign 当前代码。

前两项仅作为外部评审材料，本报告没有把其中的语句当成执行指令。

## 0. 结论先行

本轮建议对上一份方案作四个明确调整：

1. **接受“先完成一个 aircraft family，再扩展多构型”的修正。** 首先做出一个几何、分析、优化和结果回看的完整纵向闭环，暂不同时接入 5–11 种布局。
2. **首个 family 改为 `bwb_v1`（Blended-Wing-Body，融合翼身/飞翼），不选 `conventional_uav_v1`。** 这是因为用户反复指向的 MIT Demo 展示的是同一 BWB 拓扑内，参数改变后产生明显不同的整机外形；常规 UAV 虽然更容易沿用现有公式，却很可能再次出现“更精细，但看起来还是同一架飞机”的问题。
3. **P0 不是先画曲线，也不是先做完整插件平台，而是先建立同源的数据契约。** 同一份设计状态必须同时驱动三维几何、代理模型、约束和优化结果，不能再出现“滑块变了、模型用了、三维没变”的情况。
4. **界面改成 Michigan Webfoil 式的简约科研工具。** 白/浅灰内容区、深蓝结构区、蓝色数据曲线、黄色少量强调；删除当前黑底、霓虹绿、渐变、光晕和过多彩色卡片。借鉴信息层级，不复制密歇根大学校徽、名称或品牌资产。

最终产品应有两个清楚的工作模式：

```text
Analyze / Explore
几何参数 + 飞行工况
        ↓
外形即时连续变化 + 整机曲线更新

Optimize / Mission Design
航程、载荷、速度、高度、燃油上限、重量上限、目标 L/D
        ↓
优化器搜索几何参数
        ↓
baseline + 3 个可行且形状明显不同的候选
```

航程、燃油、重量和目标 L/D 属于任务需求、目标或约束；翼展、站位弦长、后掠、扭转、厚度和中心体尺寸才是直接改变外形的几何变量。两类输入不能混为一组滑块。

---

## 1. 对外部评价的判断

### 1.1 总体评价

外部评价的核心修正是正确的：**不要为了快速出现很多轮廓，就先把多个拓扑接到同一套未经校准的低阶公式上；先把一个 family 做成真正一致的闭环。**

但材料中的长报告和粘贴评价实质上是同一套观点的长、短版本，不是两份独立证据。它们不能因为重复出现而增加证据权重，仍需逐项与代码和外部模型核对。

### 1.2 逐项裁决

| V2 主张 | 本轮裁决 | 原因 |
|---|---|---|
| 先做一个 family 的完整闭环 | 接受 | 能先解决几何、模型、约束不一致的根因 |
| 用 `DesignFamilyPackage` 隔离不同布局 | 接受，但首版做薄 | 先定义最小接口；第二个 family 到来时再抽取完整 registry，避免过度架构 |
| 第一个 family 选常规 UAV | 不接受 | 与用户指定的 MIT BWB 形态变化效果不一致，视觉验收风险高 |
| 先加 Analyze/polar，再定义 `GeometryState` | 调整顺序 | 数据契约必须先于新接口，否则会把旧的不一致继续扩散 |
| 把 NeuralFoil 四张曲线作为整机分析 | 不接受 | NeuralFoil 是二维翼型层，不能被标成整机 CL/CD/CM |
| 优化结果显示 top-3 | 接受，但重定义 | 必须明确是“同一目标的三个多样近优解”，还是三个不同目标；不能混写 |
| 发动机数量作为第一版连续变量 | 不接受 | 它会改变拓扑，首版应固定或作为离散预设 |
| 4–7 个工作日完成 MVP | 仅适用于视觉原型 | 含模型边界、网格稳健性、测试和复核的工程 MVP 更接近 2–3 周 |
| OpenVSP 可以后置 | 部分接受 | 不用于实时拖动，但应在候选复核和导出阶段进入，且做几何一致性检查 |
| 保留现有 job/SSE/cancel/store | 接受 | 这些基础设施可继续使用，不需要重写 |

### 1.3 V2 最有价值的部分

V2 正确指出了三个问题：

- 不同飞机拓扑需要不同的变量、约束、有效域和性能模型；不能把它们硬塞进一条通用向量。
- 优化器会主动利用代理模型的外推误差，因此模型域检查必须是硬边界，而不是界面上的轻提示。
- 三维、性能和优化必须由同一个设计状态驱动。

### 1.4 V2 仍缺少的内容

V2 没有充分解决以下事项：

- 为什么第一 family 必须是常规 UAV，而不是用户明确参考的 BWB；
- MIT Demo 的变量、权重、几何 decoder、nTop 文件和许可到底能否直接使用；
- 哪些“公开模型”真的同时具备论文、代码、权重、输入定义、训练域和可再分发许可；
- 二维翼型曲线与整机曲线如何分开；
- top-3 的目标和多样性如何定义；
- 代理模型如何与 VSPAERO、VLM、公开基准或实验数据校准；
- 静稳定、配平、结构、容积和推进匹配等整机约束；
- 简约界面的设计规范和可验收标准。

---

## 2. 当前代码事实：为什么现在只有一架粗糙飞机

本轮对 `8115933` 代码进行了只读回查，V2 对现状的主要判断成立。

| 现状 | 代码证据 | 影响 |
|---|---|---|
| Rapid 写死常规布局 | `geometry_mapper.py:43-45, 68-91` | 固定上单翼、常规尾翼、3° 上反角、单机头发动机 |
| Three.js 只画简单积木 | `AircraftThreePreview.tsx:50-75, 111-171` | 机身是 Capsule，机翼是定厚挤出，尾翼是 Box，发动机是圆柱 |
| 预览模型忽略多个设计变量 | `threePreviewModel.ts:58-124` | layout、sweep、dihedral、airfoil 等改变后，三维可能完全不变 |
| NeuralFoil 角色是二维翼型 | `model_adapter.py:78-88` | 不能直接支持“整机代理模型”的产品表述 |
| 整机性能来自经验修正 | `evaluator.py:86-100` | 航程、阻力和重量是低阶概念估算，不能冒充高保真结果 |
| 已计算攻角数组但仅返回单点 | `model_adapter.py:105-123, 141-156` | 现有结果丢失了可画曲线的数据 |
| 优化器只保留一个解 | `optimizer.py:40-56, 111-133` | 无 archive，也没有 top-3 多样候选 |
| 现有任务外壳较完整 | `routers/rapid_design.py:23-89`、`job_runner.py:40-65, 136-169` | config、job、SSE、结果、取消和持久化可保留 |
| 上游布局不等于可信模型 | `layout-maturity-matrix.md:139-153` | 多布局 builder 只证明几何管线存在，不代表气动和工程可信 |

因此，当前问题不是“优化器只碰巧选中了同一架飞机”，而是：

```text
一个被写死的布局
+ 一个丢失大量变量的预览映射
+ 一个积木式 renderer
+ 一个只返回单个最优解的优化器
= 无论输入怎么变，都像同一架粗糙飞机
```

换颜色、扩大滑块范围或随机摆放部件都不能从根本上解决问题。

---

## 3. 首个 family 的选择：`bwb_v1`

### 3.1 为什么不是先做常规 UAV

常规 UAV 的优势是能较多复用现有 `AircraftSpec`、经验公式和 OpenVSP builder；但它的主要风险正好击中用户当前不满意之处：在单一梯形翼、筒状机身、常规尾翼的语法下，即使翼展、弦长和后掠变化，结果仍容易像“同一架飞机做了缩放”。

如果项目目标只是尽快得到一个较可信的工程 sizing 工具，常规 UAV 是稳妥选项；但目前的首要验收是 **参数改变后能生成肉眼明显不同、仍然连续光顺的整机外形，并接近 MIT Demo 的体验**。因此首个展示 family 应选 BWB。

### 3.2 BWB 为什么更匹配

MIT Hackathon 仓库描述的外部设计空间由 10 个 BWB 平面形变量组成，包括根弦、多个弦长比、多个展向段比例、内外翼后掠和外段折点位置。它展示的“不同飞机”本质上不是在常规、鸭翼和飞翼之间跳转，而是 **同一 BWB 拓扑内的连续形状变化**。

这与 Webfoil 的核心体验一致：

- 合法、连续且低维的形状空间；
- 拖动参数即可看到平滑几何变化；
- 同一设计状态同步更新性能；
- 优化在同一个有效域内返回不同候选。

MIT 的仓库和模型说明见 [nTop × MIT BWB Hackathon repository](https://github.com/nicksungg/nTop---ASME-IDETC-CIE-Student-Hackathon)。相关 BWB 数据与场预测论文见 [BlendedNet paper](https://arxiv.org/abs/2509.07209) 和 [BlendedNet repository](https://github.com/nicksungg/clarc_blended_wing_body)。

### 3.3 首版范围

`bwb_v1` 只做连续外形与气动闭环，不把全部结构逆设计一口气搬进来。

建议首版变量：

- `C1`：中心体/根部尺度；
- `C2/C1`、`C3/C1`、`C4/C1`：四个弦长站之间的比例；
- `B1/C1`、`B2/C1`、`B3/C1`：三个展向段比例；
- `S1`、`S3`：内、外段后掠；
- `X3/C1`：外段折点流向位置；
- 统一的厚度/翼型参数和必要的扭转参数，但只有在性能模型也能解释它们时才开放优化；
- 高度、速度/Mach、攻角作为飞行工况。

第一版固定：

- 推进器数量和大体位置；
- 控制面拓扑；
- 内部结构拓扑；
- 材料体系。

发动机数量、尾翼有无、肋/桁条数量等离散变化应等到 mixed-variable 优化和对应模型准备好之后再开放。

### 3.4 开工前的两个硬门槛

1. **许可门槛**：公开可下载不等于开源。当前看到的 MIT Hackathon 和 BlendedNet GitHub 根目录没有清楚的标准开源许可证，不能直接把 CSV、权重、`.ntop` 或源文件提交到本项目公共仓库。应先取得作者和 nTop 对代码、权重、数据、衍生成果与 hosted inference 的明确许可。
2. **几何同源门槛**：MIT 的精确几何逻辑主要在二进制 `.ntop` 工件中。若没有参数到表面坐标的明确定义或成对的参数—网格样本，自己近似画出的 BWB 可以用于视觉原型，但不能声称它与 MIT surrogate 的训练几何严格一致。

在门槛未通过前，可以先写 adapter 和 clean-room 几何原型，但权重保留为本地外部资源，不推入公共仓库，也不在界面中标为“开源整机模型”。

---

## 4. 正确的数据架构

### 4.1 不建议使用单向链条

V2 提出的：

```text
DesignVector → GeometryState → PerformanceBundle
```

容易让人误以为性能模型必须读取前端 renderer 生成的网格。实际上，不同模型可能读取参数向量、翼段、点云或 OpenVSP 几何。更稳妥的架构是：

```text
FamilyManifest + DesignVector
              ↓ validate / normalize / attach units
       CanonicalDesignState
          ↙        ↓         ↘
GeometryDecoder  Constraints  PerformanceAdapter
      ↓                         ↓
GeometryState              PerformanceBundle
      ↓                         ↓
Three.js / export          curves / metrics
```

三条分支共享同一个 `CanonicalDesignState` 和 `design_hash`。性能模型可以声明自己使用其中哪些变量；未支持的变量必须被冻结、拒绝，或明确标为 geometry-only，不能悄悄忽略。

### 4.2 最小对象定义

#### `FamilyManifest`

- `family_id`、版本和显示名称；
- 变量定义、单位、上下界、默认值和是否可优化；
- 几何 decoder 版本；
- 性能 adapter 名称、权重校验值、训练域和 fidelity；
- 约束集；
- 许可和来源元数据；
- 支持的输出和明确不支持的输出。

#### `CanonicalDesignState`

- 物理量和归一化量；
- 明确单位；
- 飞行工况；
- 域检查结果；
- family、decoder、model 版本；
- 可复现的 `design_hash`。

#### `GeometryState`

- 平面形站位、前后缘和弦长；
- 各站截面、扭转和厚度；
- 中心体/机身截面；
- 光顺曲面或可重建网格；
- 面积、展长、体积等几何描述符；
- 顶视和侧视轮廓签名，供候选去重；
- 与 OpenVSP/导出几何的一致性摘要。

#### `PerformanceBundle`

必须把层级分开：

```text
section_polar         # 二维翼型：NeuralFoil
aircraft_polar        # 整机：BWB surrogate / VLM / VSPAERO
mission_metrics       # 航程、燃油、重量等，需要额外任务模型
constraints           # 配平、稳定、容积、结构、域检查等
provenance            # 模型、版本、fidelity、训练域、警告
```

如果模型不输出 `Cm`，界面就不画 `Cm`，而不是用经验值或零值补一张看起来完整的图。

### 4.3 每个变量都要有追踪表

在代码和报告中维护如下矩阵：

| 变量 | 几何使用 | 性能使用 | 约束使用 | 是否可优化 | 域检查 |
|---|---:|---:|---:|---:|---:|
| `C2/C1` | 是 | 是 | 是 | 是 | 硬边界 |
| `twist_tip` | 是 | 取决于模型 | 是 | 仅模型支持时 | 硬边界 |
| `engine_count` | 否/固定 | 否 | 否 | 否 | 预设 |

自动测试应检查：每个开放变量要么在声明的分支产生可测变化，要么明确标为固定/仅显示；不得存在“可拖动但没有任何作用”的变量。

---

## 5. 公开模型调查与使用建议

“published paper 里公开的模型”只有同时满足以下条件，才适合直接放进 RapidProcessDesign：

```text
明确的可使用/可再分发许可
+ 推理代码和实际权重
+ 输入含义、顺序、单位和归一化
+ 几何 decoder 或完全对应的几何数据
+ 训练/验证范围
+ 输出定义和误差
+ 与本项目 family 的语义一致
```

### 5.1 候选矩阵

| 候选 | 能解决什么 | 许可/可用性 | 本项目判断 |
|---|---|---|---|
| [NeuralFoil](https://github.com/peterdsharpe/NeuralFoil) | 二维翼型 CL/CD/CM 和 confidence | MIT，论文、代码和权重可用 | 可继续使用，但只能标为 section-level |
| [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox) | VLM/低阶整机分析、优化和数据生成 | MIT | 不是预训练 surrogate；适合做实时低阶基线或教师数据生成 |
| [OpenAeroStruct](https://github.com/mdolab/OpenAeroStruct) | VLM + 梁结构的气动结构分析 | Apache-2.0 | 可作后续气动结构教师模型，不是即插即用 BWB surrogate |
| [OpenVSP/VSPAERO](https://github.com/OpenVSP/OpenVSP) | 参数化整机、导出和面元/VLM 复核 | NOSA 1.3 | 作为用户单独安装的外部依赖；不阻塞实时拖动 |
| [MIT Hackathon BWB](https://github.com/nicksungg/nTop---ASME-IDETC-CIE-Student-Hackathon) | BWB 几何/工况到 CL、CD、L/D，另有结构数据和 `.ntop` | 公开可见，但未确认标准开源许可；nTop 还有独立条款 | 语义最匹配，但取得书面许可和几何映射前不可 vendoring |
| [BlendedNet](https://github.com/nicksungg/clarc_blended_wing_body) | 999 个 BWB 几何、8,830 个高保真案例；预测表面 `Cp/Cfx/Cfz` | 数据与代码公开可见，但仓库许可需确认 | 研究价值高；集成成本高于直接系数模型，先做法律和权重审计 |
| [AeroTransformer / SuperWing](https://github.com/tum-pbs/AeroTransformer) | 约 30,000 个跨音速三维翼样本与公开预训练模型 | GitHub/Hugging Face 标注 MIT | 是“3D wing family”的强候选，不是 BWB 整机模型，不能错接到 `bwb_v1` |
| [ShapeBench](https://github.com/KrisshChawla6/ShapeBench) | 汇总 NeuralFoil、SuperWing、BWB、VLM 等 103 个优化任务 | 可作为公开研究索引；本轮未确认仓库级许可 | 用来筛选模型和复现实验，不在许可审计前直接复制其内容 |
| [AircraftVerse](https://github.com/SRI-CSL/AircraftVerse) | 27,714 个电动航空器多构型数据 | 代码仓库标注 MIT；数据使用条款仍需逐项核对 | 可用于未来多拓扑研究，不是当前 BWB 即插即用模型 |

Michigan Webfoil 本身证明了“紧凑几何空间 + 预先生成的大量 CFD 数据 + 经过验证的 surrogate + 在线 Analyze/Optimize”的交互路线，而不是证明任意公开神经网络都可以跨几何语义使用。MDO Lab 将其描述为在线翼型分析和优化工具，参见 [MDO Lab software page](https://mdolab.engin.umich.edu/software)；其 B-spline/GAN 参数化和 surrogate 流程见 [BSplineGAN paper](https://www.umich.edu/~mdolaboratory/pdf/Du2020.pdf)。

### 5.2 推荐模型路线

#### A. 许可快速通过

```text
MIT BWB 参数域
→ 精确几何 decoder
→ MIT BWB 系数 surrogate 负责快速 Analyze
→ VSPAERO/AeroSandbox 对最终候选复核
→ 另建重量、容积、任务和结构模型
```

#### B. 许可或 decoder 无法获得

```text
独立定义并冻结 bwb_v1 参数域
→ clean-room B-spline/CST 几何 decoder
→ AeroSandbox/VSPAERO 做 DOE
→ 训练并发布自己的 surrogate
→ 用保留测试集和教师求解器验证
```

不能采取的做法是：画一个“看起来像 BWB”的近似表面，再把 MIT 权重接上去，并把结果称为该几何的整机性能。

### 5.3 结果可信度标签

界面每次分析都应显示：

- `Model` 和版本；
- `Geometry family` 和 decoder 版本；
- `Fidelity`：section surrogate / VLM / panel / CFD-trained surrogate；
- `Domain`：in-domain、near-boundary 或 out-of-domain；
- `Verified`：是否被教师求解器复核；
- 数据和许可来源。

这些信息可以紧凑显示，不需要做成一排发光状态卡。

---

## 6. Analyze 与 Optimize 的产品闭环

### 6.1 Analyze

用户直接调整：

- BWB 几何变量；
- 高度、Mach/速度和攻角；
- 必要的材料或任务预设。

系统响应：

1. 本地立即更新 `GeometryState` 和 Three.js 光顺曲面；
2. 停止拖动约 150–250 ms 后调用 `/api/rapid-design/analyze`；
3. 在模型有效域内批量扫描攻角；
4. 返回真实支持的 CL、CD、L/D 曲线和域状态；
5. baseline 使用浅灰线，current 使用蓝线叠加；
6. 点击“设为基准”时才更新 baseline。

二维 NeuralFoil 曲线可以放在“Airfoil section”折叠区，不得与整机 polar 共用同一个含糊图例。

### 6.2 Optimize

用户输入：

- 航程、有效载荷、巡航速度和高度；
- 燃油/能源上限、MTOW 上限；
- 目标或最低 L/D；
- 后续可加入容积、静稳定、配平和结构约束。

现有异步 job、SSE、取消和结果存储继续使用。优化器应新增：

- 可行候选 archive；
- 严格的模型域限制；
- 固定 seed 和可复现记录；
- 候选教师模型复核；
- 无可行解时显示最紧约束和最小违约量。

### 6.3 top-3 的正确定义

第一版建议采用：**同一个主要目标下的三个多样近优可行解**。

筛选逻辑：

1. 按主要目标排序；
2. 只保留距最好目标值不超过预设容差的可行解；
3. 使用轮廓、曲面采样或几何描述符距离做多样性选择；
4. 逐个用教师模型复核；
5. 显示“Best / Balanced / Distinct”角色，但不要把它们误写成三个不同优化目标。

仅用归一化参数向量距离不够，因为参数差得很大时，轮廓仍可能几乎相同。若产品要同时返回“最轻、最大航程、最大 L/D”，那是三个目标或真正的多目标 Pareto 问题，应单独设计。

---

## 7. Michigan Webfoil 式简约 UI 规范

### 7.1 设计原则

目标是“研究人员能快速看懂和操作的科学工具”，不是展示型游戏界面。

- 参考 Michigan Webfoil 的信息组织、密度和克制感；
- 不复制校徽、University of Michigan 字样或其他品牌识别；
- 几何、数值和曲线是视觉主角；
- 一个页面最多使用一个主交互色和一个少量强调色；
- 状态不仅靠颜色表达，还要有文字或图标。

### 7.2 推荐色板

| 用途 | 色值 | 说明 |
|---|---|---|
| 顶栏/左侧结构区 | `#00274C` | 深海军蓝 |
| 当前数据/链接 | `#1B4F8A` | 稳定、清楚的工程蓝 |
| 选中 tab/主要按钮 | `#FFCB05` | 黄色，仅少量使用 |
| 页面背景 | `#F4F6F9` | 浅灰 |
| 面板背景 | `#FFFFFF` | 白色 |
| 主文字 | `#1F2937` | 深灰，不用纯黑 |
| 次文字 | `#5F6B7A` | 辅助信息 |
| 分隔线/坐标网格 | `#D8DEE8` | 细灰线 |
| 失败状态 | 低饱和红 | 只用于真实错误/约束失败 |

这不是要求复刻学校官方色彩，而是建立相近的学术工具视觉语言。

### 7.3 页面结构

```text
┌────────────────────── 深蓝顶栏：项目名 / 模型 / 导出 ──────────────────────┐
│ Reference Aircraft | Custom Aircraft                                     │
├───────────────┬────────────────────────────────────────────────────────────┤
│ Analyze       │                 3D Geometry                                │
│ Optimize      │       baseline + current，白色画布，简洁视角按钮           │
│               ├────────────────────────────────────────────────────────────┤
│ 参数组        │ 指标摘要 / domain / fidelity                              │
│ 滑块 + 数值框 ├──────────────────────┬─────────────────────────────────────┤
│ 单位清楚      │ CL vs α              │ CD vs α                             │
│               ├──────────────────────┼─────────────────────────────────────┤
│               │ L/D vs α             │ mission / constraint summary        │
└───────────────┴──────────────────────┴─────────────────────────────────────┘

Optimize 完成后：在 3D 下方增加紧凑的 baseline + top-3 候选条。
```

桌面端优先采用“左控制 + 右大画布/曲线”的两栏结构。现有三栏响应式骨架可以暂时复用，但 Analyze 模式应收起不必要的结果栏，把空间让给几何和曲线。

### 7.4 图表规范

- baseline：浅灰实线；
- current：蓝色实线；
- selected candidate：深蓝或蓝色虚线；
- 约束线：低饱和红色虚线；
- 每张图都有坐标名、单位、图例和数据来源；
- 相同物理量的颜色在所有图中一致；
- 不使用彩虹色、面积渐变或装饰性动画；
- 若没有模型输出，就不显示空图。

### 7.5 明确禁用

- 黑色大背景；
- 霓虹绿作为主色；
- 径向/彩虹渐变；
- 发光点、光晕、玻璃拟态；
- 大面积圆角卡片和重阴影；
- 01/02/03 等无信息价值的装饰编号；
- 每项指标一个不同颜色；
- 只因“好看”而出现的动画。

### 7.6 UI 验收

- 页面无渐变、无 glow、无 glassmorphism；
- 单个视图不超过两个非语义强调色；
- 所有滑块可键盘操作，数值框有单位和上下界；
- baseline/current 在 3D 和图表中使用一致语义；
- 约束状态有文字，不只靠红绿；
- 1366×768 和 1920×1080 下无需横向滚动即可完成主要流程；
- 加载、空状态、域外警告、无可行解和模型失败均有简短明确文案；
- 使用统一 design tokens，不在组件内散落颜色值。

---

## 8. 修订后的实施顺序

### Gate 0：许可与可行性，先做

目标：回答“MIT 模型和几何是否可以合法、准确地进入公共仓库”。

- 向作者/nTop 确认代码、权重、数据、`.ntop`、衍生作品和 hosted inference 的许可；
- 获取或重建参数到表面坐标的精确规则；
- 复现实例输入输出和公开测试误差；
- 检查几何和飞行工况的完整有效域；
- 若失败，立即切换到 clean-room BWB + 自建 DOE 路线。

**退出条件：** 有书面许可和可复现 decoder，或正式决定不依赖该工件。

### P0：一个最小但真实的纵向切片

- 定义薄版 `FamilyManifest`、`CanonicalDesignState`、`GeometryState` 和 `PerformanceBundle`；
- 先让 1–2 个 BWB 变量贯通几何、分析、约束和 `design_hash`；
- 新增 `/api/rapid-design/analyze`；
- 用一个真实模型输出一条整机曲线；
- 用简约双栏 UI 同时显示几何和曲线；
- 建立变量追踪和一致性测试。

**退出条件：** 改一个参数时，几何与整机曲线都发生符合预期的变化，而且同一状态可以完全复现。

### P1：完成 BWB 连续形状空间

- 扩展到 3–5 个展向控制站和完整的 BWB 平面形变量；
- 用 B-spline/CST 或等价方法生成光顺前后缘和截面 loft；
- 增加 baseline/current 叠加；
- 增加四个合法极端 preset，例如宽中心体、窄高速、大展弦比、紧凑高载荷；
- 做随机域几何稳健性和浏览器性能测试；
- 完成 Michigan Webfoil 式视觉改造。

**退出条件：** 四个 preset 轮廓肉眼明显不同，且随机合法样本不存在 NaN、负厚度、翻面或明显自交。

### P2：Analyze 完整闭环

- 批量攻角扫掠；
- 分开展示 aircraft polar 和 section polar；
- 增加 domain、fidelity、model version 和 provenance；
- 模型实例常驻缓存，避免每次请求重新加载；
- 最终点支持 VLM/VSPAERO 复核。

**退出条件：** 全部结果标明层级和来源，域外输入被拒绝或醒目标记，不再把二维结果写成整机结果。

### P3：Optimize 与 top-3

- 复用现有异步 job/SSE/cancel/store；
- 保存 feasible archive；
- 按目标容差和几何距离选 top-3；
- 候选进入同一个 Analyze 页面继续调整；
- 教师模型复核最终候选；
- 加入配平、静稳定、容积、重量和任务约束的可用子集。

**退出条件：** top-3 均可行、可复现、形状明显不同，并且不是代理模型域外漏洞。

### P4：第二个 family

第二个 family 再考虑 `conventional_uav_v1` 或使用 AeroTransformer 的 `transonic_wing_v1`。此时才抽取完整 registry、family picker 和跨 family 管理。

在不同 family 的模型误差、任务定义和 fidelity 没有校准到同等级之前：

- 可以并列展示；
- 可以各自在 family 内优化；
- **不可以宣称跨 family 的数值排名公平。**

---

## 9. 时间判断

时间必须分成三个层级，不能统一写成“4–7 天完成 MVP”。

| 层级 | 内容 | 合理估计 |
|---|---|---:|
| 视觉证明 | clean-room BWB 滑块、光顺 3D、简约界面、假/低阶曲线并明确标注 | 4–7 个工作日 |
| 测试过的单 family 研究 MVP | 同源契约、真实 Analyze、模型域、top-3、自动测试、候选复核 | 10–15 个工作日 |
| 自建 BWB surrogate | DOE、批量求解、训练、验证、版本化和部署 | 在上项基础上增加约 2–6 周，取决于求解器和计算资源 |

许可等待时间不应计入开发工时承诺。若必须逆向猜测 `.ntop` 里的几何逻辑，则不应承诺模型与屏幕几何严格一致。

---

## 10. 验收标准

### 10.1 同源性

- 相同 `family_id + design_hash + model_version` 必须产生同一几何、曲线和约束结果；
- 100% 域外输入被拒绝，或在仅分析场景下明确警告且禁止进入优化；
- 每个开放变量都有几何/性能/约束影响声明和自动测试；
- 浏览器预览与导出模型的翼展、面积、体积、站位和轮廓误差在预设容差内。

### 10.2 几何

- 至少四个 preset 的顶视轮廓明显不同，而不是仅缩放或换颜色；
- 在固定随机种子的有效域样本中，无 NaN、负厚度、脱离部件和翻面；
- 光顺区域无肉眼折痕，前后缘等设计锐边除外；
- top-3 通过轮廓/曲面距离阈值，而非只通过参数距离。

### 10.3 模型

- 复现发布方测试集指标，或给出本项目自己的保留测试集；
- 将“对低阶教师模型的拟合误差”与“对真实飞行/CFD 的误差”分开；
- CL、CD、L/D、Cm、range、weight 等只显示实际被对应模型支持的量；
- 最终优化候选全部经过教师求解器复核；
- 无法验证的量使用 `estimate`，不得使用 `verified`。

### 10.4 交互性能

以下指标必须注明测试机器、浏览器、模型档位、是否预热和缓存状态：

- 三维预览更新 P95 目标 `< 200 ms`；
- 本地/预热后的快速 Analyze P95 目标 `< 1 s`；
- 拖动时几何实时变化，模型请求做 150–250 ms debounce；
- Analyze 模型常驻内存，不按请求重复加载权重。

### 10.5 产品与 UI

- Analyze 和 Optimize 是两个明确 tab；
- 任务参数与几何参数分组清楚；
- 白/浅灰主画布、深蓝结构区、黄色仅作少量强调；
- 无黑底霓虹、渐变、光晕和花哨多色卡片；
- 曲线有单位、图例、来源、fidelity 和域状态；
- 无可行解时给出最紧约束和最小违约量。

---

## 11. 下一轮具体改动边界

在真正实施时，建议保留：

- Rapid 的 config/job/SSE/cancel/result store；
- 现有 Three.js 场景、相机、视角切换、OrbitControls、GLB loader 和资源释放；
- OpenVSP adapter、导出和文件服务；
- 滑块 + 精确数值框的基本交互；
- 输入分组和响应式布局骨架。

建议替换或新增：

- 当前写死常规布局的 `geometry_mapper`；
- 丢失 sweep/airfoil/layout 等变量的 `threePreviewModel`；
- Capsule/Box/定厚挤出的粗糙飞机 renderer；
- 单点、混合层级的结果 schema；
- 只保留单个解的 optimizer 状态；
- 深色霓虹的 Rapid CSS 主题；
- family-specific BWB decoder、domain validator、performance adapter 和测试。

实现过程中不要把 family 逻辑继续塞进一个巨大 `if layout == ...` 文件。首版只需一个薄接口和 `bwb_v1` 实现；第二 family 到来后再稳定抽象。

---

## 12. 最终建议

外部评价应当被采纳，但不能原样执行。正确方向不是“先把常规 V0 做漂亮”，也不是“立刻展示十一种飞机”，而是：

> **以 `bwb_v1` 做第一个整机 Webfoil 纵向闭环；先建立统一的变量—几何—性能—约束契约，再完成光顺几何、整机 Analyze、top-3 Optimize 和教师复核。界面采用 Michigan Webfoil 式的白/浅灰、深蓝、少量黄色的简约科研工具风格。MIT 工件只有在许可和几何同源性得到确认后才能进入公共仓库。**

这条路线既正面解决“外形太死板、太粗糙”，又避免做出几架漂亮但性能数值没有工程含义的模型。
