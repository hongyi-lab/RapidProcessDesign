# 模型接口与离线 UQ：本轮证据边界

核对日期：2026-09-10。这里记录已连接资源和评估入口，不把接口测试称为整机验证。

## 实际可调用的 MIT 模型

`model_adapter.py` 导出 `model_catalog(root=None)`、`predict_mit(payload, root=None)`、`supports_analysis(metadata, required, geometry_decoder_id=None)`，以及 UI 使用的 `MIT_EXAMPLE`、`MIT_INPUT_SCHEMA`。简化整机计算继续使用自己的显式模型；MIT 模式只给原生几何的系数分析，没有用示例 Cm 或椭圆载荷悄悄补齐它。

资源根优先级：服务端显式 `root` → `BWB_MIT_ROOT` → 仓库旁的 `MIT/official_hackathon`。请求 JSON 不接受资源路径。上游源文件、权重和训练数据均留在外部目录，不随本仓库分发。五个源/参数文件按 UTF-8、统一换行后的 SHA256 核对；缺失或内容变化时关闭该调用，返回具体原因。当前核对版本为 `b516d4b3e2e5e34fbd5233eacdf15317a96dc2d9`。不是宣称上游最新 HEAD。

| 证据 ID | 实际依据 | 允许的结论 / 缺口 |
|---|---|---|
| MIT-WRAPPER | [固定版本 predict_ld.py](https://github.com/nicksungg/nTop---ASME-IDETC-CIE-Student-Hackathon/blob/b516d4b3e2e5e34fbd5233eacdf15317a96dc2d9/models/ld_surrogate/predict_ld.py)，已读本地对应源 | 输入十个原生几何数、高度、KCAS、攻角；输出 CL/CD/LD/Re/Mach。无 Cm、舵效、分布载荷或结构响应。 |
| MIT-DOMAIN | 同版本 `flight_conversion.py`、`aero_design_space.json`、根 README 参数表 | 六个长度比例在特征中乘 1000；X3/C1 不乘。C1 通过 Re 起作用。适配器使用原生几何搜索盒、README 的 C1 2500–4000 mm、原始与转换飞行域。 |
| MIT-PAPER-REF | [BlendedNet++ v1 §3](https://arxiv.org/html/2512.03280v1#S3)，在线直接读取 | 论文 CFD 规范模型长 1 m，力系数参考面积 1 m²、力矩参考长 1 m、力矩原点在机鼻。此处是论文规范，不能自行等同于当前 wrapper 标签的完整来源链。 |
| MIT-LABEL-GAP | 同版本 `regressor.py` 的 `_load`、`predict` 与 `reg_full.json`，已读本地源 | 训练器从未随包提供的 NPZ 读 CL/CD，再反标准化输出。缺少构建 NPZ 的标签处理与归一化证明，wrapper 也无参考量字段。因此运行时 S_ref、length_ref、moment_reference 保持 null，L_N/D_N 不可用。 |

盒检查是明确的保守调用边界，**不证明联合训练分布覆盖**；`aero_design_space.json` 自述来自 feasible 子集搜索盒，而 full 权重训练集不同。原 wrapper 的空 warnings 没有检查几何域；本适配器单独执行几何检查。原生 `mit_ntop_ratio_v1` decoder 与 demo 的三段梯形 decoder 不匹配会直接返回 `geometry_decoder_mismatch`，不映射外形、更不换算整机力。

实际样例（原生几何、15 kft、180 KCAS、6°）已调用外部模型：CL ≈ 0.203178284678、CD ≈ 0.016652316320、LD ≈ 12.20120256976。测试还实际经过 18 kft / 249 KCAS 的转换域拒绝。S3=60°、非有限数、错误 decoder、缺失能力、非正 CD 均不能生成有效量。实际模型测试在资源不存在时会明确跳过；跳过不算通过模型验证。

返回 `{model, prediction}`。每个量有 `availability_per_quantity[q]={available,reason}`；条件/状态 ID 与真实输入 hash 同时保存。未调用或失败时 `quantities={}`，不保留伪造数值。`uncertainty_metadata=null`，原因为缺少独立校准/测试数据、预训练样本身份未知。

## UQ 入口与论文核对范围

本轮尝试访问 [Shah–Alonso DOI 页面](https://arc.aiaa.org/doi/10.2514/6.2026-2023) 和出版社 PDF 均未成功，当前附件没有该论文 PDF，**未声称重读或复现论文**。用户审阅书中的七模型、样本数、GRUBS 对比及附录结论在这里仅视为用户提供的审阅背景，未升级为本轮独立核实结果。也未实现 GRUBS、训练或校准器。

作者 [UQRegressors 官方指标说明](https://arjunrs3.github.io/UQRegressors/examples/metrics/)可访问，本轮直接核对其中 RMSE、经验覆盖率、平均区间宽度和 interval score 定义。实现采用这些标准指标定义，但没有安装或调用该库，也没有采纳其演示中的合成区间作为 BWB 的误差条。

`uq_evaluate.py` 只评估用户供应的、冻结的预测和独立参考数据：

```powershell
python uq_evaluate.py --schema-example --output uq-template.json
python uq_evaluate.py --manifest split-manifest.json --reference reference.json --predictions predictions.json --output evaluation.json
python uq_evaluate.py
```

最后一条在无数据时返回 `not_evaluated`、`metrics=null`。模板只有字段形状和空数组，故意不能通过独立评估验收；它不是编造的真实数据集。

输入分为三个文件：

- `manifest`：数据/模型版本及参考保真度；proper_train、validation、calibration、test 的完整 `{sample_id,group_id}` 清单；完整训练/调参暴露清单及证据 ID；先划分再拟合、校准集不参与调参/预处理、测试集不参与训练/校准/选择的保护声明。
- `reference`：精确覆盖整个 test 的参考值及单位、几何/家族 group ID、域内/边界/域外/未知分组、是否为优化选出的候选。
- `predictions`：精确覆盖同一 test 的点预测、模型/数据版本及冻结预测的证据 ID。若供应区间，必须有真实上下界和 `type, nominal_level, distribution_statement, calibration.{method,sample_count,data_version,evidence_id}`；不供应区间就只计算点误差。

评估器拒绝重复样本、样本/几何组跨划分、预训练暴露与校准/测试相交、未知预训练身份、缺失保护声明、遗漏测试行、单位/参考保真度不一致、非有限数和上下界颠倒。对已有 MIT 权重，目前不能拿来源不明的数据重切一个“独立”校准/测试集。

每个输出单独报告 MAE、RMSE、单位和参考保真度；区间存在时另报经验 coverage、mean width、interval score。除总体外，分别报告模型域分组、优化所选样本及两者交集，空分组保持 null。所有输入保存内容 hash。声明一致性可自动检查，声明是否真实仍需外部证据审查，输出明确标注该限制。

当前没有独立 BWB 参考数据，**没有经验 UQ 结果**。15 项 `test_models_uq.py` 测试在本机执行通过，其中指标算术使用手算合成数字，仅核对公式实现和拒绝条件。窄区间不覆盖参考模型的物理偏差；边际覆盖率不是某一优化候选、更不是多工况整机的安全概率；数值残差与这些误差也不是同一回事。
