# Rapid Process Design 第四轮实施记录

## 基线

- 基线提交：`72b26a9c4c7a16de42802eb938870140f9e4c1b8`
- 基线能力：`bwb_v1` Analyze 与 legacy conventional Optimize 为两条独立路径。
- 前端基线：185 项测试通过。
- 后端基线：Windows 默认 GBK 环境下 546 项通过，9 项失败、99 项 setup error；失败集中在历史测试用系统默认编码读取 UTF-8 YAML，并非 Round 4 功能失败。后续验收统一启用 UTF-8 模式。
- 工作区：开工前已有本地启动器、字体/说明文档修改以及未跟踪的 `Round4/` 文件；这些改动予以保留。

## 本轮边界

本轮实现 family-neutral 整机工作台、`bwb_v1`、`conventional_v2`、Canonical `GeometryState`、通用 loft renderer 和统一 Analyze 页面。

本轮明确不修改 `configs/rapid_design/demo.yaml` 中的目标、边界、penalty、population、iterations、质量模型、NeuralFoil 配置或 uncertainty 逻辑；正式优化规范统一记录在 [老师待确认文档](teacher-decisions-optimization-spec-cn.md)。

## 目标数据流

```text
Family manifest + preset + high-level parameters
                         |
                         v
              family geometry decoder
                         |
                         v
              Canonical GeometryState
              /          |            \
     Three.js renderer  analysis   future exporter/optimizer
```

通用 renderer 只读取 `loft_body`、`lifting_surface` 和 `nacelle`，不读取 family-specific 设计变量。Legacy Optimize 保留为独立演示，不再表示它优化了 Analyze 页面当前选中的飞机。

## 实施顺序

1. family registry、discovery API 和 dispatch；
2. GeometryState schema 与 BWB adapter；
3. `conventional_v2` 三个 preset 和概念级 analysis；
4. 通用 renderer、动态 controls、baseline；
5. Analyze / Mission Design / Legacy Conventional Demo 信息架构；
6. 后端、前端、build 和本地浏览器验收。
