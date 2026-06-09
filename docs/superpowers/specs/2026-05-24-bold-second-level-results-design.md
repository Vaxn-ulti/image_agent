# BOLD Second-Level Results Design / BOLD 二级结果设计

## Goal / 目标

Extend the current BOLD downstream workflow from placeholder ALFF/fALFF handling into a research-grade structured results pipeline with:

将当前 BOLD 下游流程从占位式的 ALFF/fALFF 处理扩展为科研级的结构化结果管线，包含：

- single-subject metric generation  
- 单被试指标生成
- descriptive multi-subject review outputs  
- 描述性多被试审阅输出
- batch fixed-sphere seed connectivity outputs  
- 批量固定球形 seed 连通性输出
- future gated group-level comparison outputs  
- 未来带严格门控的组水平对比输出
- display-ready artifacts suitable for a unified results module  
- 适合统一结果展示模块直接消费的展示级产物

The immediate implementation priority is:

当前立即实施优先级为：

1. single-subject and descriptive outputs first  
1. 先做单被试和 descriptive 输出
2. group comparison second, only under valid statistical guardrails  
2. 再做组间对比，而且必须受有效统计前提约束

## Why This Exists / 设计背景

The repository already supports BOLD preprocessing eligibility and task execution flow, but the local implementation still exposes only a placeholder downstream metric runner in `apps/api/app/workflows/bold_metrics.py`.

当前仓库已经支持 BOLD 预处理资格校验和任务执行流程，但本地实现里，`apps/api/app/workflows/bold_metrics.py` 仍然只是一个占位版下游指标 runner。

Project evidence collected on 2026-05-24 also shows that:

同时，2026-05-24 收集到的项目证据表明：

- real downstream BOLD artifacts already exist in external/runtime evidence  
- 在外部运行证据中，真实的 BOLD 下游产物已经存在
- users want substantially broader BOLD second-level outputs  
- 用户希望显著扩展 BOLD 二级指标能力
- seed-to-ROI should support many seeds  
- `seed-to-ROI` 需要支持尽可能多的 seed
- outputs must be visually reviewable for research use  
- 输出必须在视觉上适合科研审阅
- future comparison figures should resemble SPM12-style scientific statistical review figures rather than generic dashboard charts  
- 未来的对比图应尽量接近 SPM12 风格的科研统计审阅图，而不是普通 dashboard 风格图表

## Scope / 范围

### In Scope: Phase 1 / 第一阶段范围

Phase 1 implements research-grade single-subject and descriptive downstream outputs after completed BOLD preprocessing.

第一阶段在 BOLD 预处理完成后，先实现科研级的单被试和 descriptive 下游输出。

Required metric families:

必须纳入的指标族：

- `ALFF`
- `fALFF`
- `ReHo`
- `tSNR`
- `RSFA`
- mean map  
- 平均图
- standard deviation map  
- 标准差图
- whole-brain timeseries summary  
- 全脑时间序列摘要
- power spectral density summary  
- 功率谱密度摘要
- motion summaries based on FD and DVARS  
- 基于 FD 和 DVARS 的运动摘要
- seed-to-voxel connectivity  
- seed-to-voxel 连通性
- seed-to-ROI connectivity  
- seed-to-ROI 连通性
- network-to-network FC summary where derivable from the ROI layer  
- 在 ROI 层可推导时，输出 network-to-network FC 摘要

Required seed policy:

必须遵守的 seed 策略：

- fixed-coordinate spherical seeds are the default  
- 以固定坐标球形 seed 为默认策略
- no broad fuzzy seed matching  
- 禁止宽泛、模糊匹配 seed
- each seed must have a stable preset id, name, coordinate, radius, and provenance note  
- 每个 seed 必须有稳定的 preset id、名称、坐标、半径和来源说明

Initial preset families should include classic research seeds such as:

第一批 preset 应覆盖经典科研 seed，例如：

- `PCC_DMN`
- `mPFC_DMN`
- `lIPL_DMN`
- `rIPL_DMN`
- `dACC_SN`
- `lAI_SN`
- `rAI_SN`
- `dlPFC_L_ECN`
- `dlPFC_R_ECN`
- `Hippocampus_L`
- `Hippocampus_R`
- `Amygdala_L`
- `Amygdala_R`
- `Thalamus_L`
- `Thalamus_R`

Each preset must define:

每个 preset 必须明确：

- MNI coordinate  
- MNI 坐标
- sphere radius in mm  
- 球半径（毫米）
- human-readable label  
- 可读标签
- network or anatomical family  
- 所属网络或解剖家族
- literature or internal provenance string  
- 文献来源或内部来源说明

### In Scope: Phase 2 / 第二阶段范围

Phase 2 implements gated group-level comparison outputs for research use only when inputs satisfy minimum statistical requirements.

第二阶段实现带严格门控的组水平对比输出，且仅在输入满足最小统计要求时才允许用于科研。

Required rules:

必须满足的规则：

- group analysis is blocked below the minimum sample threshold  
- 低于最小样本阈值时，组分析必须直接阻止
- real brain masks must be used  
- 必须使用真实脑掩膜
- seed definition must be fixed and explicit  
- seed 定义必须固定且明确
- parcel-level metrics must not be misrepresented as voxelwise inference  
- parcel 级指标不能伪装成 voxelwise 推断
- descriptive outputs and inferential outputs must be clearly separated  
- 描述性输出与推断性输出必须清晰分离

Phase 2 figures should target an SPM12-like review style:

第二阶段图像风格应尽量接近 SPM12 审阅风格：

- orthogonal slice statistical overlays  
- 正交切面统计叠加图
- glass-brain style summary figures where appropriate  
- 适当提供 glass-brain 风格总览图
- explicit threshold labeling  
- 清晰标注阈值
- peak tables tied only to truly voxelwise inferential outputs  
- peak 表仅能对应真实 voxelwise 推断输出
- restrained colormap defaults suitable for scientific reading  
- 默认配色要克制，并适合科研阅读

## Out of Scope / 不在本次范围

The following are not part of this subproject unless separately requested:

以下内容除非单独提出，否则不属于本子项目：

- replacing BOLD preprocessing itself  
- 替换 BOLD 预处理本身
- claiming clinical-grade certification  
- 声称达到临床认证级别
- uncontrolled exploratory figures presented as inferential group evidence  
- 将不受控的探索性图像伪装成推断性组结果
- ambiguous network-name seed queries that expand silently to many ROIs  
- 使用模糊网络名并静默扩展成大量 ROI 的 seed 查询方式

## Architecture / 架构设计

The implementation should introduce a unified structured output contract for BOLD downstream results.

实现上应引入统一的 BOLD 下游结构化输出契约。

### Layer 1: Metric Engine / 第一层：指标引擎

`bold_metrics.py` should evolve from a placeholder script into a real downstream metric engine.

`bold_metrics.py` 应从占位脚本演进为真实的下游指标引擎。

Responsibilities:

职责包括：

- discover eligible preprocessed BOLD inputs  
- 发现合格的预处理 BOLD 输入
- compute selected metric families  
- 计算指定指标族
- emit NIfTI maps, summaries, and provenance  
- 输出 NIfTI 图、摘要和 provenance
- support one metric or a batch profile  
- 支持单指标运行或批量 profile 运行
- support single-subject outputs first  
- 优先支持单被试输出

### Layer 2: Seed Preset Registry / 第二层：Seed 预设注册表

Create a seed preset registry in code rather than scattering seed definitions across plotting scripts.

需要在代码中建立 seed preset 注册表，而不是把 seed 定义散落在各类绘图脚本里。

Responsibilities:

职责包括：

- centralize fixed-coordinate spherical seed definitions  
- 集中管理固定坐标球形 seed 定义
- expose stable preset ids  
- 暴露稳定 preset id
- validate seed selection  
- 校验 seed 选择是否合法
- enable batch seed runs for seed-to-voxel and seed-to-ROI outputs  
- 支持 seed-to-voxel 和 seed-to-ROI 的批量 seed 运行

### Layer 3: Structured Result Contract / 第三层：结构化结果契约

Each analysis run should write a stable output package that the frontend can consume without modality-specific guesswork.

每次分析运行都应写出一个稳定的输出包，使前端无需依赖特定指标内部逻辑即可直接消费。

Minimum package elements:

最小结果包元素包括：

- machine-readable summary JSON  
- 机器可读的 summary JSON
- metric-level TSV or CSV tables  
- 指标级 TSV 或 CSV 表格
- plotting-ready data  
- 可直接用于绘图的数据
- provenance and parameter metadata  
- provenance 和参数元数据
- produced NIfTI files  
- 生成的 NIfTI 文件
- produced PNG review figures  
- 生成的 PNG 审阅图
- per-seed output index when seed analyses are requested  
- 当请求 seed 分析时，输出逐 seed 的结果索引

Suggested package structure:

建议输出目录结构：

```text
output/
  summary/
    bold_metrics_summary.json
    provenance.json
    metrics_index.tsv
  maps/
    <metric-or-seed>.nii.gz
  tables/
    seed_to_roi.tsv
    network_fc.tsv
    fd_timeseries.tsv
    dvars_timeseries.tsv
    mean_psd.tsv
  figures/
    <metric>_stat.png
    <seed>_seed_fc_stat.png
    <seed>_roi_heatmap.png
    motion_qc_overlay.png
```

### Layer 4: Descriptive Review Builder / 第四层：Descriptive Review 构建器

The descriptive layer should aggregate valid subject-level outputs into non-inferential review artifacts.

descriptive 层应把有效的单被试输出聚合成非推断性的审阅产物。

Responsibilities:

职责包括：

- compare subjects descriptively  
- 做描述性被试比较
- summarize network FC patterns  
- 汇总 network FC 模式
- summarize motion QC  
- 汇总 motion QC
- summarize per-subject maps and seed outputs  
- 汇总每个被试的 map 和 seed 输出
- avoid inferential language or pseudo-thresholded claims when sample sizes are insufficient  
- 在样本量不足时避免推断性语言或伪阈值结论

### Layer 5: Future Group Comparison Builder / 第五层：未来的组间对比构建器

The group-level builder should exist behind strict validation and should only run when scientific minimums are met.

组水平构建器必须受严格校验保护，只有在满足科研最低要求时才允许运行。

Responsibilities:

职责包括：

- enforce sample-count requirements  
- 强制样本量要求
- distinguish descriptive from inferential outputs  
- 区分 descriptive 和 inferential 输出
- produce SPM12-like scientific comparison figures  
- 生成接近 SPM12 风格的科研对比图
- produce peak tables only when methodologically valid  
- 仅在方法学有效时生成 peak tables

## Output Design Requirements / 输出设计要求

### Scientific Data Reliability / 科学数据可靠性

Every output package must preserve:

每个输出包都必须保留：

- exact input provenance  
- 精确输入 provenance
- seed definitions used  
- 使用的 seed 定义
- metric computation parameters  
- 指标计算参数
- mask source  
- mask 来源
- threshold metadata  
- 阈值元数据
- subject/task identifiers  
- subject/task 标识信息

### Visual Reliability / 视觉可靠性

Every figure intended for research review must include:

每张用于科研审阅的图都必须包含：

- metric name  
- 指标名称
- seed label when applicable  
- 若适用则标注 seed 名称
- threshold or display-stat note  
- 阈值或显示统计说明
- spatial reference note  
- 空间参考说明
- readable intensity scale or colorbar  
- 可读的强度刻度或 colorbar
- non-misleading defaults  
- 不会造成误导的默认设置

### SPM12-Like Comparison Goal / SPM12 风格对比目标

For future group comparisons, figures should visually resemble the practical reading experience of SPM12 statistical review outputs rather than product-dashboard cards.

对于未来的组间对比图，其视觉阅读体验应尽量接近 SPM12 统计审阅输出，而不是产品 dashboard 卡片。

That means:

这意味着：

- brain-first composition  
- 以脑图为中心组织版面
- explicit threshold annotations  
- 明确标注阈值
- slice-based statistical overlays  
- 基于切面的统计叠加图
- restrained, publication-friendly color handling  
- 克制、适合发表与审阅的颜色处理
- support for glass-brain summaries  
- 支持 glass-brain 总览图
- associated peak tables only for valid voxelwise analyses  
- 仅为有效的 voxelwise 分析提供对应 peak 表

## Acceptance Criteria / 验收标准

### Phase 1 Acceptance / 第一阶段验收

Phase 1 is acceptable when:

第一阶段满足以下条件才算通过：

- placeholder ALFF/fALFF outputs are replaced with real structured outputs  
- 占位版 ALFF/fALFF 输出被真实结构化输出取代
- multiple BOLD metric families can be produced from completed BOLD preprocessing  
- 已完成 BOLD 预处理后可以生成多个 BOLD 指标族
- fixed-sphere seed presets are batch-runnable  
- 固定球形 seed preset 可以批量运行
- seed-to-voxel and seed-to-ROI outputs are emitted under a stable contract  
- `seed-to-voxel` 和 `seed-to-ROI` 在稳定契约下输出
- descriptive figures and summaries are display-ready  
- descriptive 图和摘要可直接用于展示
- outputs are suitable for the future BOLD results module  
- 输出适合未来 BOLD 结果展示模块直接消费

### Phase 2 Acceptance / 第二阶段验收

Phase 2 is acceptable when:

第二阶段满足以下条件才算通过：

- invalid small-sample pseudo-group analysis is blocked  
- 无效的小样本伪组分析会被阻止
- valid group inputs produce explicit research-style comparison outputs  
- 合格组输入能生成明确的科研风格对比输出
- figures are visually close to SPM12-style statistical review expectations  
- 图像在视觉上接近 SPM12 风格统计审阅预期
- inferential and descriptive outputs are clearly separated  
- 推断性输出和描述性输出清晰分离

## Local Constraints and Repo Reality / 本地限制与仓库现实

The local worktree currently contains:

当前本地工作树包含：

- `apps/api/app/workflows/bold_metrics.py`
- workflow routing in `pipeline.py`

The local worktree does not currently contain:

当前本地工作树并不包含：

- a checked-in `bold_descriptive_review.py`  
- 已签入仓库的 `bold_descriptive_review.py`
- a checked-in `bold_group_analysis.py`  
- 已签入仓库的 `bold_group_analysis.py`

Therefore implementation should start by making this repository capable of generating the downstream metric/result packages directly, instead of assuming those external scripts already exist locally.

因此，实现应从“让当前仓库直接具备生成下游指标和结果包的能力”开始，而不是假设那些外部脚本已经在本地仓库中存在。

## Delivery Sequence / 交付顺序

1. implement real metric engine and result contract  
1. 实现真实指标引擎和结果契约
2. implement seed preset registry and batch seed outputs  
2. 实现 seed preset 注册表和批量 seed 输出
3. implement descriptive review outputs and display-oriented figures  
3. 实现 descriptive review 输出和面向展示的图像
4. add strict group-analysis gate and future group output scaffolding  
4. 加入严格的组分析门控和未来 group 输出骨架
5. extend toward research-style comparison figures  
5. 扩展到科研风格对比图输出

## Risks / 风险

- local repository and runtime evidence are not fully symmetric  
- 本地仓库与运行环境证据并不完全对称
- broad seed expansion can silently corrupt interpretability if not blocked  
- 如果不阻止宽泛 seed 扩展，会悄悄破坏结果可解释性
- group figures can easily look scientific while remaining statistically invalid  
- 组图很容易“看起来像科研图”，但统计上仍然无效
- visually impressive figures are unacceptable if provenance, mask handling, or thresholds are unclear  
- 如果 provenance、mask 处理或阈值不清楚，再好看的图也不可接受

## Decision Summary / 决策总结

Approved design direction:

已确认的设计方向：

- structured-output-contract first  
- 先做结构化输出契约
- Phase 1 single-subject plus descriptive first  
- 第一阶段先做单被试加 descriptive
- Phase 2 group analysis second  
- 第二阶段再做 group analysis
- fixed-coordinate spherical seeds as the dominant seed strategy  
- 以固定坐标球形 seed 作为主导策略
- target future research figures that feel similar to SPM12 statistical comparison output  
- 未来科研对比图目标设定为接近 SPM12 统计对比输出风格
