# Rapid Process Design 当前状态、理论基础与多外形路线评估

> 日期：2026-09-03
> 范围：RapidProcessDesign 当前实现、`MIT/official_hackathon` 参考项目，以及 University of Michigan Webfoil 方法。
> 本文是现状审计和技术建议；本轮没有修改现有功能，也没有把新的模型或数据直接复制进仓库。

## 0. 结论先行

用户真正想要的是：调整航程、载荷、燃油、重量、速度、L/D 等任务输入后，系统不只是改变同一架飞机的尺寸，而是能够生成、比较并展示**明显不同且工程上自洽的整机外形**；交互体验接近 Webfoil，但对象从二维翼型扩大到完整飞机。

当前 Rapid Design 还不是这个系统。它现在是：

```text
任务需求与约束
  → 在一个固定的“常规上单翼、常规尾翼、机头单发”模板内优化 10 个连续参数
  → 用二维 NeuralFoil 加低阶整机公式估算性能
  → 只返回一个最轻可行点
  → 用胶囊、平板和圆柱组成参数预览
```

因此，数值确实会变化，但拓扑、部件组合和主要轮廓不会变化，视觉上必然像同一架粗糙飞机。

“V0 只做 conventional tube-and-wing”只是早期实施时主动设定的范围，不是理论或项目的必要条件。用户已经明确不需要这个限制，下一阶段应把项目目标改为：

> **多构型、可连续变形、可即时分析、可比较的整机逆向概念设计平台。**

推荐路线不是再寻找一个“神奇的飞机生成模型”，而是采用混合架构：

1. 把常规、鸭翼、飞翼/BWB、双尾撑等**构型家族作为离散变量**；
2. 每个家族内部使用自己的多截面连续参数化和高质量曲面生成器；
3. 用布局感知的整机物理模型/代理模型评价，而不是让 NeuralFoil 跨构型工作；
4. 每次返回 3–5 个有差异的候选和 Pareto 权衡，而不是永远只返回一个最优点；
5. 浏览器先即时更新轻量几何和代理结果，后台再生成 OpenVSP CAD 并做更高层复核。

## 1. 2711 目录与仓库现状

### 1.1 目录角色

| 内容 | 当前角色 | 是否应直接混入 Rapid 源码 |
|---|---|---|
| `RapidProcessDesign/` | 当前主项目；独立 Git 仓库 | 是，后续开发在这里进行 |
| `MIT/official_hackathon/` | nTop × MIT DeCoDE Lab 的 BWB 数据、代理模型和 nTop 文件参考 | 否；先核对许可，再通过适配器引用或重实现 |
| `MIT/mdao_experiment/`、`MIT/mdao_experiment_v2/` | 已有本地优化实验和结果 | 可作为研究证据，不应无整理地复制到产品代码 |
| `MIT/paper/` | 优化、约束和不确定性相关论文集合 | 文献资料，不是运行依赖 |
| 提案、PPT、会议材料 | 项目背景与汇报材料 | 保持在 2711 上层，避免污染代码仓库 |

### 1.2 Rapid Git 状态

- 代码仓库：RapidProcessDesign 仓库根目录
- 分支：`main`
- 当前基线提交：`8115933 feat: add mission-driven rapid design workflow`
- 项目远端：<https://github.com/hongyi-lab/RapidProcessDesign>
- 上游来源：<https://github.com/zweien/aero-spec-agent>
- 本报告创建前，代码与 `origin/main` 同步且工作区无其他改动。

此前交付检查中，Python 测试为 642 passed、9 skipped，前端测试为 177/177，生产构建通过。但这只能说明软件回归通过；它不能证明外形质量或工程有效性。特别是 Rapid 的多数优化/API 测试使用快速解析测试模型，尚没有多布局优化、真实 OpenVSP 联调和系统性视觉敏感性测试。

## 2. 当前 Rapid 已经实现了什么

### 2.1 用户输入

当前 7 个输入来自 [`configs/rapid_design/demo.yaml`](../configs/rapid_design/demo.yaml)：

| 输入 | 含义 | 当前范围 |
|---|---|---:|
| 目标航程 | 任务需求 | 300–3000 km |
| 有效载荷 | 任务需求 | 20–300 kg |
| 巡航速度 | 任务需求 | 100–320 km/h |
| 巡航高度 | 任务需求 | 500–9000 m |
| 最大燃油质量 | 上限约束 | 50–900 kg |
| 最大起飞质量 | 上限约束 | 300–2500 kg |
| 目标 L/D | 下限约束 | 8–24 |

这部分与用户所说的“我可以调整一段输入范围，再生成结果”是一致的。

### 2.2 当前优化器真正控制的变量

优化器控制 10 个连续变量：

- 机翼面积、展弦比、梢根比、后掠角；
- 机身长度、机身直径；
- NACA 四位数风格的最大弯度、弯度位置、厚度；
- 实际装油量。

采用 SciPy `differential_evolution`，策略为 `best1bin`，固定随机种子 2711，当前仅运行 9 代、较小种群，并只输出 `best_feasible` 或最小违约点。它目前没有：

- 构型类别变量；
- 多目标 Pareto 前沿；
- 候选多样性/新颖度约束；
- top-K 方案集合；
- 用户锁定或排除某一构型的能力。

### 2.3 当前理论与计算链

#### 几何关系

当前仅使用梯形主翼的低维关系：

```text
b = sqrt(S × AR)
c_root = 2S / [b(1 + taper)]
c_tip = taper × c_root
```

其中 `S` 为翼面积，`AR` 为展弦比。机身湿表面积近似为 `πDL × 0.88`。这足以做初步尺寸估算，但不能描述多折点翼、翼身融合、双尾撑、鸭翼、翼尖形状或光滑机身截面变化。

#### 二维翼型代理：NeuralFoil 0.3.3

[`model_adapter.py`](../services/api/app/services/rapid_design/model_adapter.py) 根据三个 NACA 风格参数生成二维坐标，在攻角 -3° 至 14°之间取 18 个点，并调用公开的 [NeuralFoil](https://github.com/peterdsharpe/NeuralFoil) `medium` 模型，得到：

- 二维翼型 `CL`、`CD`、`CM`；
- `analysis_confidence`；
- 当前所需升力系数对应的攻角和剖面阻力。

NeuralFoil 是有用且可保留的二维翼型模型，但它的输入里没有整机布局、尾翼、发动机、翼身干扰或三维拓扑。它**不会生成飞机形状，也不能判断常规布局和飞翼谁更好**。

#### 整机阻力近似

[`evaluator.py`](../services/api/app/services/rapid_design/evaluator.py) 使用：

```text
CD_total = CD_NeuralFoil
         + CL² / (π AR e)
         + CD_body
         + CD_sweep
```

其中 Oswald 效率固定为 0.82，机身和后掠使用经验修正。当前没有显式计算：三维升力分布、尾翼配平阻力、多翼面相互作用、翼身干扰、发动机/吊舱阻力、压缩性、静稳定性或操稳。

#### 质量模型

当前质量是可配置的经验部件累加：机翼面积/翼展项、机身湿面积项、固定系统质量、载荷相关系统质量、固定推进质量和起落架比例。它便于演示和以后校准，但目前没有尾翼、多翼面、材料、结构载荷、燃油/载荷容积、重心或具体发动机选型模型。

#### 航程模型

采用带 15% 储备油的 Breguet 风格关系：

```text
R = V / c × (L/D) × ln(m_takeoff / m_final)
```

其中等效耗油率 `c = 0.00017 s⁻¹` 为固定概念级参数，不是具体发动机 map。当前没有起飞、爬升、盘旋、下降和备降等分段任务。

#### 目标与约束

当前检查 6 项：航程、L/D、MTOW、燃油、巡航升力能力和 NeuralFoil 置信度。优化目标为：

```text
J = m_takeoff / m_takeoff,max
  + 1500 × Σ(归一化负约束余量)²
```

也就是在固定模板内优先找最轻的可行点。由于没有形状多样性项，同一任务附近重复得到相似边界设计是算法的自然结果，并非随机偶然。

## 3. 为什么现在只有一种飞机，而且看起来粗糙

### 3.1 构型被明确写死

[`geometry_mapper.py`](../services/api/app/services/rapid_design/geometry_mapper.py) 当前直接输出：

- `layout = conventional`；
- 上单翼；
- 梯形主翼；
- 3° 固定上反角；
- 常规尾翼；
- 单台机头发动机。

因此，无论航程、重量和燃油怎么变化，都不可能得到鸭翼、飞翼、BWB、双尾撑、双翼或多机身。早期规划文档也明确把 V0 限为常规筒状机身布局，但这只是当时的交付边界，应当废除，而不应继续作为产品定义。

### 3.2 已优化的参数没有完整进入画面

Rapid 页面只把 `aircraft_spec` 交给 `CadViewer`，没有触发 CAD worker，也没有返回真实 GLB/OBJ 地址。于是页面走的是 Three.js 参数预览：

- 机身：`CapsuleGeometry`；
- 主翼：8 个平面点拉伸出的恒厚板，厚度固定 0.08；
- 平尾/垂尾：恒厚 `BoxGeometry`；
- 发动机：仅在数量不少于 2 时用 `CylinderGeometry` 绘制；当前 mapper 输出的单发在这个 fallback 中甚至不会被画出来。

这个 3D 数据模型甚至没有读取 `layout`、`sweep`、`dihedral`、`airfoil` 和真实翼面截面。当前优化出的后掠、翼型弯度与厚度，即使数值改变，也不会被完整画出来。所以截图中“像积木、形状死板”是实现结构决定的，不是简单换颜色或材质就能解决。

### 3.3 页面只给一个答案

当前标题就是“当前最优可行构型”，优化结束后只显示一个模型、4 个指标卡、约束列表和 MTOW 收敛曲线。没有方案画廊、基准/候选叠加、CL/CD/CM polar、布局筛选或 Pareto 对比。即使后台以后生成了很多点，现有 UI 也没有把“多样性”呈现出来。

## 4. 项目里其实已有、但 Rapid 没接上的能力

上游 AeroSpec 已经不是单一布局仓库。它的 [`layout_plan.py`](../services/workers/cad_worker/openvsp_generator/layout_plan.py) 定义了 11 类：

1. conventional；
2. twin-boom；
3. flying-wing；
4. blended-wing-body；
5. canard；
6. three-surface；
7. tandem-wing；
8. biplane；
9. joined-wing；
10. box-wing；
11. multi-fuselage。

仓库已经有相应 AircraftSpec 字段、OpenVSP builder、二维布局预览、GLB 导出路径和布局感知的 VSPAERO 面选择。详见 [`layout-maturity-matrix.md`](layout-maturity-matrix.md)。

但要准确理解“已有”：

- 这些能力目前属于主 AeroSpec CAD/聊天流程，Rapid 的任务优化链没有调用它们；
- 文档中的“pipeline stable”只表示能生成文件，不表示外形已经人工审美检查或工程验证；
- 很多布局默认尺寸仍是低置信度启发式；
- 当前机器检测不到 OpenVSP executable 和 Python bindings，默认后端仍是 fake；
- 所以直接“把 layout 字段打开”可以很快看到不同拓扑，但还不能得到用户要求的平滑、高质量、可信优化结果。

这意味着我们不需要推倒重来；最合理的是复用 11 布局的 schema、builder 和工件链，同时重建 Rapid 的多构型设计空间、几何质量层和布局感知评价层。

## 5. MIT GitHub Demo 到底做了什么

参考仓库：<https://github.com/nicksungg/nTop---ASME-IDETC-CIE-Student-Hackathon>

本地材料：[`MIT/official_hackathon/README.md`](../../MIT/official_hackathon/README.md)

### 5.1 用户的观察是对的，但要区分两种“不同”

MIT README 中的不同形状来自同一个 BWB（翼身融合）参数化母型在不同连续参数下的变形。它能形成宽体、窄体、大/小后掠、不同折点和翼尖轮廓，所以视觉差别远大于当前 Rapid。

但它并不在常规布局、鸭翼、双尾撑、飞翼之间切换；它只有一个 BWB 拓扑家族。

| 能力 | MIT 仓库 |
|---|---|
| 同一 BWB 母型产生大量不同轮廓 | 支持 |
| 内部肋、梁、翼盒随外形变化 | 支持 |
| 常规 ↔ 鸭翼 ↔ 双尾撑等拓扑切换 | 不支持 |
| 网页实时交互 | 不支持 |
| GitHub 上的可视化 | 预渲染 GIF，不是交互网页 |

### 5.2 为什么它的变化明显

它不是只给一片梯形翼设置面积、AR 和一个后掠角，而是用 10 个分布式平面参数控制 BWB：

- `C1`：总体尺度/根弦；
- `C2/C1`、`C3/C1`、`C4/C1`：多个展向站的弦长比；
- `B1/C1`、`B2/C1`、`B3/C1`：控制站展向位置；
- `S1`、`S3`：内外翼段不同后掠角；
- `X3/C1`：外翼折点纵向位置。

nTop 的二进制参数化隐式模型再把这些控制站重建成光顺外模线，并用另外 11 个变量改变蒙皮、肋、梁和翼盒。其关键经验是：**先定义一个丰富、合法且连续的几何空间，代理和优化器才有值得搜索的形状。**

### 5.3 MIT 提供的模型与限制

仓库的 L/D 模型是轻量 NumPy MLP：

```text
10 个 BWB 平面参数 + 高度/KCAS/AoA
  → 大气与飞行状态换算
  → MLP
  → CL、CD、L/D
```

结构 CSV 有 13,720 行；实际包含 24 个输入和 4 个输出。顶层 README 和 `data/README.md` 对列数、输出数量有不一致，复用前必须以实际 schema 为准。该 MLP 只在其 BWB 参数域内有效，不能拿来给常规布局或鸭翼打分。

更重要的是，仓库根目录没有标准开源 `LICENSE`。数据的“Approved for public release”分发声明不等于 MIT/BSD/Apache 再利用许可，说明中还提示当前数据会更新且不应据此发表。因此在得到作者明确许可前：

- 可以学习参数化、代理和逆向优化方法；
- 不应把 CSV、模型权重、源码、GIF 或 `.ntop` 文件直接复制进公开的 Rapid 仓库。

## 6. Michigan Webfoil 值得借鉴的真正核心

在线页面：<https://webfoil.engin.umich.edu/>

方法论文：[Li et al., Data-based Approach for Fast Airfoil Analysis and Optimization](https://www.umich.edu/~mdolaboratory/pdf/Li2019b.pdf)

后续论文：[Du, He and Martins, Rapid Airfoil Design Optimization via Neural Networks-based Parameterization and Surrogate Modeling](https://mdolab.engin.umich.edu/bibliography/Du2021a)

Webfoil 不是“代理模型直接画翼型”，而是以下闭环：

```text
低维且受约束的翼型几何空间
  → 快速气动代理
  → 约束优化
  → 原始/候选几何与 CL/CD/CM 曲线同步显示
```

早期方法从约 1,172 个 UIUC 翼型和 NASA SC(2) 翼型中用 SVD 分离提取弯度/厚度模态，并通过边界策略过滤畸形形状；再用 ADflow RANS 数据训练 GE-KPLS + mixture-of-experts 代理。论文列出的数据规模为 81,000 个亚声速样本和 32,400 个跨声速样本，并报告桌面单核上的优化约 2 秒。后续方法使用 B-spline GAN 学习更平滑、更接近有效翼型分布的生成空间。

目前没有找到 Webfoil 完整网页源码、训练权重和全量训练数据的公开仓库。因此可直接复用的是公开论文方法、UIUC 翼型数据和相关开源基础工具，而不是“把 Webfoil 模型搬过来”。

对 Rapid 最重要的迁移结论是：

> Webfoil 的体验来自“合法而丰富的几何流形 + 快速代理 + 优化 + 即时对比”，不是来自一张漂亮的翼型图，也不是只靠换 surrogate。

## 7. 从翼型扩展到整机时，必须分清三层设计空间

### 7.1 连续形状变化

同一部件连接关系下改变翼展、弦长分布、后掠、扭转、上反、翼型、机身截面和尾翼尺寸。MIT BWB Demo 主要属于这一层。

### 7.2 离散构型/拓扑变化

决定是否有机身、尾翼、鸭翼、第二片机翼、尾撑，以及发动机数量和位置。常规、鸭翼、飞翼/BWB、双尾撑之间属于这一层。

### 7.3 自由曲面或学习式生成

使用 CST、B-spline、FFD、隐式曲面、VAE/flow/diffusion 等表达更自由的表面。这一层提高形状丰富度，但不能替代拓扑相容规则、稳定性和几何合法性检查。

一个统一连续向量很难自然跨越拓扑变化。更稳妥的数学形式是分层混合设计：

```text
u     = 用户任务与约束
z     = 离散构型家族
x_z   = 该构型专属的连续/整数变量
f_z   = 该构型适用的性能模型及不确定性

对每个 z：在有效域内优化 x_z
再把各构型候选按统一目标和约束比较，输出 top-K / Pareto
```

## 8. 推荐目标架构

```text
任务输入 u
  │
  ├─ 构型注册表 / Configuration Registry
  │    ├─ 常规布局：专属 schema + geometry builder + model adapter
  │    ├─ 鸭翼布局：专属 schema + geometry builder + model adapter
  │    ├─ 飞翼/BWB：专属 schema + geometry builder + model adapter
  │    ├─ 双尾撑：专属 schema + geometry builder + model adapter
  │    └─ 后续布局……
  │
  ├─ 每个构型内部连续优化（可并行）
  │    ├─ 几何合法性/碰撞/包装
  │    ├─ NeuralFoil 截面层
  │    ├─ VLM/VSPAERO 整机层
  │    ├─ 质量/结构/推进/任务模型
  │    └─ 不确定性与超域检查
  │
  ├─ 跨构型统一约束、Pareto 与多样性筛选
  │
  └─ 返回 3–5 个候选
       ├─ 浏览器实时低模
       ├─ 性能曲线和约束余量
       └─ 后台 OpenVSP GLB/STEP 高质量工件与复核结果
```

### 8.1 几何层

同一个 `GeometryState` 应同时驱动即时 Web mesh 和最终 CAD，避免“优化参数是一套、屏幕画的是另一套”。至少需要：

- 主翼多展向站：弦长、前/后缘位置、后掠、上反、扭转；
- 展向真实翼型截面，使用 NACA/CST/B-spline loft，而非固定厚度平板；
- 机身多截面 spline/loft：宽、高、圆角、机头和尾锥；
- 尾翼/鸭翼完整参数；
- 发动机数量、位置、吊舱和推进类型；
- BWB、尾撑、第二翼面等构型专属几何；
- 法向、封闭性、自交、碰撞和部件连接检查。

短期最合适的最终 CAD 内核仍是 [OpenVSP](https://github.com/OpenVSP/OpenVSP)，因为它本身就是开源参数化飞机几何工具，当前仓库也已有适配层。浏览器低模不应每次等待 OpenVSP，而应自行 loft 并在后台 CAD 完成后替换为 GLB。

### 8.2 评价模型层

建议保留 NeuralFoil，但只作为二维黏性翼型层。整机层需要：

- VLM/VSPAERO：翼面、尾翼、多翼面和近似配平；
- 构型感知的寄生/干扰阻力；
- 静稳定裕度、CG 和配平约束；
- 失速速度、翼载、推重/功重；
- 载荷和燃油容积、结构与包装；
- 分段任务和推进效率/耗油率 map；
- 分构型校准的重量模型。

快速 surrogate 应学习 `设计 + 工况 → 性能`，而不是负责生成 CAD。每个公开模型只有在同时具备推理代码、权重、明确许可、训练域、验证误差和不确定性定义时才适合接入。

### 8.3 优化与结果层

推荐先让每个构型独立并行优化，再统一比较，这比一开始使用一个混合变量 DE 更稳妥。结果需要：

- top-3/top-5 不重复候选；
- 质量、航程、效率、风险的 Pareto 视图；
- 布局/轮廓距离阈值，避免五张卡其实是同一形状；
- 允许用户锁定、排除某个构型或锁定某个参数；
- 明确区分“代理预测”“低阶求解器复核”和“尚未验证”。

### 8.4 UI 交互层

建议借鉴 Webfoil 的两种节奏：

- **Analyze**：用户直接调整几何和工况，几何在 100–200 ms 内变化；代理结果短延迟更新，显示 CL/CD/CM、L/D、航程、重量和约束曲线；
- **Optimize**：用户填写任务目标和约束，后台搜索多个构型并返回候选画廊。

应支持基准/候选几何叠加、曲线叠加、方案固定、并排对比、置信度/超域警告，而不是只显示一张“最优飞机”。

## 9. 为达到该效果，需要获得什么

### 9.1 必需的软件与运行环境

1. OpenVSP executable 和匹配的 Python bindings；当前电脑尚未检测到。
2. 可在浏览器中生成 loft mesh 的几何模块，或把现有 Three.js 预览重写为真实截面网格。
3. 自动化 DOE、求解器运行、数据版本和工件存储环境。
4. 若以后使用 nTop，需要单独取得教育/商业许可；它不能直接在浏览器运行。

### 9.2 必需的数据

1. 每个目标构型的参数范围和相容规则；
2. 有明确许可的翼型坐标与 polar 数据；
3. 参考飞机的尺寸、重量分解、任务和航程，用于外部校准；
4. 发动机/电机/螺旋桨随高度、速度、功率变化的数据；
5. OpenVSP/VSPAERO/VLM 生成的版本化 DOE 数据；
6. 少量更高保真 CFD、结构分析或公开试验数据，用于偏差校正和最终验证。

可研究 [AircraftVerse](https://github.com/SRI-CSL/AircraftVerse)：其公开说明包含 27,714 个多样化电动飞行器设计、设计树、几何和性能结果，也提供概率生成器。但它的设计域、动力形式、数据许可和我们的固定翼任务并不完全等价，必须先完成许可与适用性审查，不能把它当成即插即用的整机模型。

University of Michigan 的 [FAST](https://github.com/ideas-um/FAST) 也值得参考：它是 Apache-2.0 的 MATLAB 飞机尺寸工具，覆盖任务、气动、重量、推进和可视化模块。更适合借鉴系统架构与校准方式，而不是直接作为 Web 前端。

### 9.3 必需的工程知识

- 5–11 类构型各自的稳定性、尾容积、布局和包装先验；
- 多翼面气动与配平；
- 质量和推进系统校准；
- 几何合法性、网格质量和自动修复；
- 超出训练域时拒绝预测，而不是静默外推。

## 10. 三条实现路线与取舍

| 路线 | 做法 | 优点 | 主要问题 |
|---|---|---|---|
| A. 参数模板优先 | 复用现有多布局 schema/OpenVSP，为每类写高质量连续参数化 | 最快可控、工程解释强 | 初期新颖度由模板决定 |
| B. 纯学习式生成 | 用 AircraftVerse/自建数据训练条件 VAE、flow 或 diffusion | 外形多样、展示效果强 | 数据/许可/有效性/约束难，容易生成“看着像但不能飞”的形状 |
| C. 混合路线（推荐） | 生成/检索提出多样候选，参数化规则修复，代理筛选，求解器复核 | 兼顾多样性、可控性和可信度 | 系统工程工作量最大，但适合最终目标 |

推荐先做 A 的可靠骨架，再逐步演进到 C。现阶段直接做 B 风险最高，因为当前缺的首先是整机几何定义、跨构型评价和验证闭环，而不是神经网络类型。

## 11. 建议实施顺序

### P0：先让“不同形状”真实出现

- 去掉 Rapid 的 conventional 硬编码；
- 先接 5 个差异明显且相对成熟的布局：常规、鸭翼、飞翼/BWB、双尾撑、双翼/串列翼择一；
- 外层逐布局并行优化，返回 3–5 个候选；
- 让 sweep、dihedral、airfoil、twist、engine count 等变量确实改变 mesh；
- Rapid 接入已有 layout preview 和 CAD artifact URL。

估计：在不做工程级校准的前提下，1–2 周可形成“多构型可看、可比较”的第一版；若只做已有构型接线，数天可看到雏形，但外观仍会比较粗。

### P1：做到 Webfoil 式交互

- Analyze / Optimize 双模式；
- 实时 loft mesh；
- 原始/候选叠加；
- CL/CD/CM polar、L/D、航程、重量、约束和置信度曲线；
- 参数锁定、方案画廊和 Pareto 比较。

估计：在 P0 基础上约 2–4 周，取决于曲面质量要求。

### P2：补工程可信度

- 安装并接通 OpenVSP/VSPAERO；
- 增加多任务段、推进 map、重量校准、静稳定/配平、结构和容积约束；
- 建立参考飞机和高保真复核集。

估计：约 1–2 个月形成可信的研究原型，数据准备常比界面编码更耗时。

### P3：数据驱动加速与生成

- 对各构型做 Sobol/LHS DOE；
- 训练每构型 forward surrogate 和 uncertainty；
- 加主动学习、多保真偏差校正和多样性生成；
- 数据足够后再研究 topology-aware 条件生成模型。

估计：研究级工作，通常需要 2–6 个月持续迭代，取决于求解成本、可用数据与目标构型数量。以上均为初步工程估计，不是承诺工期。

## 12. 建议验收标准

### 外形与交互

- 首阶段至少 5 个真正不同拓扑；自动模式每次返回至少 3 个有效候选；
- 每个几何变量必须通过 sensitivity test：变量变化时，对应顶点/轮廓确实变化；
- 参数预览 P95 < 200 ms，快速分析 P95 < 1 s，多布局搜索第一阶段 P95 < 30 s；
- 最终展示不再以胶囊和固定厚度平板作为正式几何；
- 网格无 NaN、明显翻面、自交或部件脱离，部件数量与 spec 一致；
- 俯视、侧视、前视、等轴测均有 golden screenshot 回归。

### 多样性与优化

- top-K 不重复，布局或轮廓距离达到预设阈值；
- 固定 seed 可复现；
- 建立 20–50 个 mission 回归案例并统计可行率、超时率和约束违约；
- 未找到可行方案时，明确指出最紧约束和最小违约量；
- 展示 Pareto，而不是只用最小重量把所有方案挤到同一形态。

### 工程可信度

- 二维翼型结果对 XFOIL/公开实验基准；
- 整机 surrogate 对 VSPAERO/VLM 基准，按 CL、CD、CM 分别定义误差阈值；
- 质量和航程对参考飞机校准并显示区间；
- UI 标为“可行”的最终候选必须经过较高层求解器复核全部约束；
- 每个模型记录来源、版本、许可、训练域、误差和置信度；超域时拒绝或降级，不静默给出精确数字。

## 13. 最终建议

下一步不应继续打磨当前那一架积木式飞机，也不应先花时间更换 NeuralFoil。最有效的顺序是：

1. 重新定义 Rapid 的产品目标为多构型逆向设计；
2. 利用仓库已有的 11 布局基础，先选 5 个构型建立 `Configuration Registry`；
3. 为每个构型建立更丰富的连续几何变量和真实 loft 预览；
4. 逐构型优化并返回多候选；
5. 接通 OpenVSP/VSPAERO 和高层约束；
6. 再基于自建/获许可数据训练整机 surrogate 与生成模型。

一句话概括：**MIT 告诉我们怎样让一个构型内部变化丰富，Webfoil 告诉我们怎样把几何、代理、优化和交互连成闭环；Rapid 还需要在这两者之间补上“多整机构型 + 高质量曲面 + 布局感知物理”这一层。**

## 参考资料

- [Rapid 当前技术说明](rapid-design.md)
- [Rapid 早期 Demo Master Plan](../Rapid_Aircraft_Design_Demo_Master_Plan.md)
- [Rapid Technical Spec](../Rapid_Aircraft_Design_Technical_Spec.md)
- [NeuralFoil 代码](https://github.com/peterdsharpe/NeuralFoil)；[论文](https://arxiv.org/abs/2503.16323)
- [OpenVSP](https://github.com/OpenVSP/OpenVSP)
- [MIT/nTop BWB Hackathon 仓库](https://github.com/nicksungg/nTop---ASME-IDETC-CIE-Student-Hackathon)
- [Michigan Webfoil](https://webfoil.engin.umich.edu/)
- [Li et al. 2019 Webfoil 方法论文](https://www.umich.edu/~mdolaboratory/pdf/Li2019b.pdf)
- [Du, He and Martins 2021 方法页](https://mdolab.engin.umich.edu/bibliography/Du2021a)
- [UIUC Airfoil Coordinates Database](https://m-selig.ae.illinois.edu/ads/coord_database.html)
- [AircraftVerse](https://github.com/SRI-CSL/AircraftVerse)
- [University of Michigan FAST](https://github.com/ideas-um/FAST)
