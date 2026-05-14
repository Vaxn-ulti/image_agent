Ripgrep is not available. Falling back to GrepTool.
基于对 `/home/yyf/project/image_agent/docs/phase4-plan-and-solve.md` 的审核，从测试、评审策略和实现风险角度分析如下：

### 1. 计划中的核心优势 (Strongest Parts)
*   **标准化与确定性**：明确了将混合数据源（DICOM/NIfTI）统一映射到 BIDS (Brain Imaging Data Structure) 标准的路径，解决了数据管理的混乱。
*   **明确的序列分类学**：通过 `Supported` 和 `Recognized but Unsupported` 的分类，提供了清晰的临床预期管理。
*   **部署抽象化**：提前考虑了 `Local` 与 `Remote` 两种模式，为后续从单机桌面端向云端架构迁移打下了坚实基础。
*   **数据完整性**：坚持保留原始上传字节（Originals）的设计符合临床数据回溯和审计的要求。

### 2. 具体风险与缺口 (Concrete Risks/Gaps)
*   **同步 API 超时风险**：`/ingest` 接口虽然提到了“异步”，但在同步响应中包含转换汇总。如果用户上传数千个 DICOM 文件，`dcm2niix` 转换和 BIDS 规范化过程可能导致 HTTP 连接超时。
*   **BIDS 路径冲突**：第 7 节中的路径逻辑（如 `sub-01_T1w.nii.gz`）未考虑同一受试者在同一次上传中存在多个相同模态序列的情况（如多次采集或不同角度），缺乏 `run-{N}` 或 `acq-{label}` 等 BIDS 标准实体来区分。
*   **测试数据获取与管理**：计划提到了后端单元测试和集成测试，但未说明如何构建和管理用于测试的样本医学图像库（如包含各种边缘情况的 DICOM 字典）。
*   **存储清理机制**：对于“Remote”模式，缺乏对 `uploads/` 目录下临时文件或失败上传任务的自动清理策略，长期运行存在磁盘空间耗尽风险。

### 3. 必须修改的建议 (Must-change Suggestions)
*   **API 异步化改造**：将 `/ingest` 修改为完全异步模式。接口应立即返回 `202 Accepted` 和 `task_id`，由前端通过 `/inventory` 轮询或通过事件流获取最终的汇总结果。
*   **引入 BIDS 唯一性标识**：在规范化层级必须增加对重复模态的处理逻辑，使用 `SeriesNumber` 或时间戳自动生成 `run-1`, `run-2` 等标签，防止文件覆盖。
*   **明确异常处理深度**：需要定义当 `dcm2niix` 部分成功（partial failure）时，哪些特定的关键标签缺失会导致整个序列被标记为 `failed` 而非 `unsupported`。

### 4. 可选建议 (Optional Suggestions)
*   **集成 BIDS-Validator**：在归档阶段增加一个轻量级的 `bids-validator` 调用，确保生成的 `rawdata` 目录 100% 符合 BIDS 规范。
*   **侧边栏数据增强**：在生成的 BIDS JSON 侧边栏中添加自定义字段 `X-SequenceLabel` 和 `X-ProcessingSupported`，方便后续算法直接读取。
*   **资源配额检查**：在上传开始前增加对存储空间的预检，防止大文件上传中途因磁盘溢出而崩溃。

### 5. MVP 可实现性评估
**结论：可实现 (Implementable)**。
该计划功能边界清晰，将处理范围严格限制在 DeepPrep 和 QSI 家族内，避开了复杂的统计报表开发，非常适合作为最小可行性产品（MVP）的开发蓝图。只要解决上述 API 异步化和路径冲突问题，即可进入开发阶段。
