# Round 5 几何红队审计

审计基线：`main@4096144`。本报告先把自动测试、接口有效性与视觉质量分开；`geometry_status=valid` 只说明数据满足当前 schema 和少量顺序检查，不代表飞机外形成熟。

## 结论

用户仍然认为三个 conventional preset 是同一架飞机，判断是正确的。三个 preset 在基线实现中共享同一套机身归一化轮廓、四站位机翼公式、平尾公式和垂尾公式。`preset_id` 唯一直接参与的几何分支是短舱位置。因此当前结果是“一个母版的连续缩放与推进位置切换”，不是三个有独立设计语法的 archetype。

根因同时存在于参数、decoder、renderer 和 camera：

1. 参数值虽不同，但大多进入同一公式；拓扑、站位分布和归一化轮廓不变。
2. decoder 把三个 archetype 都展开为同一套组件；机身全站共用一个 `shape_exponent`，翼面固定四个展向站位，尾翼固定普通尾翼。
3. renderer 只在输入站位之间直线连接；`airfoil_id` 完全不参与顶点生成，`dihedral_deg` 字段也不参与顶点生成，垂尾的 `y_m` 只用于排序而不用于定位。
4. 每次换飞机后相机按该飞机自身 bounding box 重新适配，使最大尺寸总是占据近似相同画幅，掩盖了绝对尺度和长宽比差异。
5. 翼身、尾身和推进系统只有几何相交，没有翼根整流、尾根过渡、吊舱或推进器安装关系；tractor / pusher / twin-engine 只表现为位置不同的封闭短舱。

## 代码链路证据

- `conventional_v2/presets.py`：三个 preset 只有 17 个连续数值不同，另由 `PRESET_PROPULSION` 指定短舱位置。
- `conventional_v2/geometry.py::_body_stations`：三者共用固定 `width_scales`、`height_scales` 和 9 个相对站位，所有 `z_offset_m=0`。
- `conventional_v2/geometry.py::_wing_sections`：三者共用 `[0, 0.28, 0.68, 1]` 半翼展站位、同一 chord ratio 公式和同一 sweep factor。
- `conventional_v2/geometry.py::_tail_components`：三者都只有相同公式生成的普通平尾与单垂尾。
- `geometrySurfaces.ts::buildRingLoft`：只对输入站位逐圈建点并直接连三角形，法线平滑不能消除轮廓折段。
- `geometrySurfaces.ts::sampleLiftingPoint`：只使用 twist 与 thickness；`airfoil_id` 和 `dihedral_deg` 是渲染死字段。
- `ParametricAircraftPreview.tsx::applyViewPreset`：相机距离始终取当前包围盒最大尺寸的固定倍数；没有统一世界尺度或归一化比较模式。
- `test_rapid_design_families.py::test_conventional_presets_are_geometrically_distinct`：基线测试只比较 span、aspect ratio 和 nacelle id，同模板缩放也会通过。
- 基线 Round 4 变更没有提交任何新截图；既有 `docs/qa-screenshots` 图片来自更早版本，无法证明三个新 preset 的视觉结论。

## 参数有效性分级

| 参数 | 基线分级 | 原因 |
| --- | --- | --- |
| fuselage_length_m | 有效 | 改变整机纵向尺度，也间接改变机身截面尺度 |
| fineness_ratio | 有效 | 改变机身宽高，但相机自动适配会削弱感知 |
| nose_length_ratio | 弱 | 只移动共享鼻段站位，鼻部归一化曲线不变 |
| cabin_fullness | 有效 | 改变机身宽高及截面指数 |
| tailcone_length_ratio | 弱 | 只移动共享尾段站位，尾锥语法不变 |
| section_ovality | 弱 | 仅统一缩放全机身高度 |
| wing_span_m | 有效 | 改变翼展；自动适配会掩盖绝对尺度 |
| wing_area_m2 | 有效 | 通过根弦长改变机翼面积 |
| wing_root_x_ratio | 弱 | 只平移主翼，不改变平面形 |
| wing_vertical_ratio | 有效 | 改变高翼/低翼位置，但没有翼根过渡 |
| wing_sweep_deg | 有效 | 改变前缘位置，但仍使用同一折线公式 |
| wing_taper_ratio | 有效 | 改变弦长分布，但仍使用同一四站位公式 |
| wing_dihedral_deg | 弱 | decoder 预先写入 `leading_edge_z_m`；字段本身不生效 |
| wing_twist_tip_deg | 弱 | mesh 会变化，但默认远景和前缘转轴使肉眼变化很小 |
| wing_thickness_ratio | 弱 | mesh 会变化，但远景中不明显 |
| tail_arm_ratio | 弱 | 只平移同一套尾翼 |
| tail_scale | 有效 | 改变同一套尾翼的面积，不改变尾型 |
| airfoil_id（GeometryState） | 视觉死字段 | renderer 完全忽略 |
| lifting-surface dihedral_deg（GeometryState） | 视觉死字段 | renderer 完全忽略 |
| vertical section y_m（GeometryState） | 视觉死字段 | 垂尾定位固定在 y=0 |

这里的“有效”只表示基线下能看出连续几何变化，不表示参数有足够的设计语义或已经通过工程验证。

## 比例参考与使用边界

基线仓库没有给三个 preset 的尺寸来源或 provenance，因此只能判为未溯源的 clean-room 手工数值。本轮只借用公开整机尺寸形成比例锚点，不复制任何 CAD 或专有曲面：

- 长航时 archetype：美国空军 MQ-9 factsheet 给出 20.1 m 翼展、11 m 机长，翼展/机长约 1.83，作为高展弦比后推式 UAV 的量级参考：<https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104470/mq9-reaper/mq-9-reaper/>
- 快速巡航 archetype：Daher TBM 960 页面给出 12.83 m 翼展、10.74 m 机长，翼展/机长约 1.19，作为高速单发 tractor 概念的比例参考：<https://www.tbm.aero/page/tbm960>
- 载荷运输 archetype：Cessna SkyCourier 官方页面给出 22.02 m 翼展、16.8 m 机长和 40.97 m² 机翼面积，翼展/机长约 1.31，作为高翼双发 utility 概念的比例参考：<https://cessna.txtav.com/en/turboprop/skycourier-freighter>

这些来源只约束量级和构型语义；最终几何仍为本项目独立构造的低阶概念模型，不能被描述为真实飞机复刻或气动认证模型。

## 距离“真实概念设计”仍缺什么

- archetype-specific 的机身站位、截面曲线、机头/舱段/尾锥语法；
- 可控 kink、前后缘曲线、翼根积分和 station-specific airfoil/camber/thickness；
- V-tail、T-tail、普通/双垂尾等 preset-defined 尾型；
- 可识别的 spinner、propeller、nacelle、pylon 与安装关系；
- 翼根和尾根的连续过渡；
- 正交四视图、统一世界尺度和同机身长归一化比较；
- 对每个控制量的语义敏感性测试，而不是只比较整份 JSON 是否不同；
- 自交、穿透、局部曲率和推进间隙的更严格几何检查。

## 本轮实施范围

1. 保留 family-neutral API、registry、BWB、Legacy optimizer 和启动脚本。
2. 在 `conventional_v2` 内引入三个独立 archetype decoder；优化目标、变量选择、上下界、penalty、DE、Pareto、conformal 和 uncertainty 逻辑保持不变。
3. 扩展 Canonical GeometryState，使 airfoil camber、局部 loft feature、propeller 和安装结构能被通用 renderer 消费。
4. 对 body 和 lifting surface 做平滑重采样，并提供 auto-fit、统一世界尺度、同机身长归一化三种尺度模式。
5. 增加三 archetype 联动比较和参数敏感性视图，生成版本化视觉验收包；BWB 单独回归。

## 基线视觉证据

基线实际运行 `main@4096144` 后，从 `/rapid-design` 逐一选择三个 conventional preset 并点击 3D、顶视、侧视、前视得到原始截图，位于 `docs/round5-visual-validation/before/`。汇总图为 `conventional-presets-four-view-grid.png`。这些截图同时保留了当时的 auto-fit 行为，直接显示比例差异被重新取景削弱的问题。
