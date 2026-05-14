Ripgrep is not available. Falling back to GrepTool.
这份关于 Phase 4 “Plan-and-Solve” 架构方案的后端 API、数据模型及合同评审报告如下：

### 1. 方案优势 (Strongest Parts)
*   **标准化程度高**：明确引入 BIDS (Brain Imaging Data Structure) 作为数据组织标准，这将极大地提升数据的可移植性和后续算法的兼容性。
*   **确定性库存报告 (Deterministic Inventory)**：在执行耗时任务前提供详细的序列识别统计（支持与不支持列表），能有效提升用户预期管理和系统的可靠性。
*   **序列分类详尽**：针对临床常见的序列（T1, DWI, BOLD, FLAIR 等）制定了清晰的分类与支持矩阵（Sequence Taxonomy），并强制执行“不支持序列”的统一文案回复。
*   **部署灵活性**：考虑了 `local`（本地直连文件系统）和 `remote`（HTTP 多段上传）两种运行模式，API 合同保持一致，增强了系统的扩展能力。

### 2. 具体风险与缺口 (Concrete Risks/Gaps)
*   **同步响应超时风险**：`POST .../ingest` 接口被描述为“同步返回摘要”。然而，DICOM 到 NIfTI 的转换（dcm2niix）以及 NIfTI 的头文件扫描在文件较多时可能耗时数分钟。在 `remote` 模式下，这极易导致 HTTP 超时。
*   **数据模型不匹配**：现有数据库 `imaging_series` 表将 `file_id` 设为 `NOT NULL`，且与文件是一对一关系。Phase 4 引入了 `upload_session`（一个压缩包包含多个序列），目前的表结构无法直接支持一个上传任务生成多个 BIDS 序列。
*   **元数据提取来源不明**：方案提到了 BIDS 路径（如 `sub-01/anat/...`），但未明确 `subject_id` 是从 DICOM Tag（如 `PatientID`）自动提取，还是由前端在 `upload-session` 阶段手动录入。

### 3. 必须修改的建议 (Must-change Suggestions)
*   **异步化 Ingest 接口**：`POST .../ingest` 必须改为异步处理，返回 `202 Accepted` 及任务 ID。前端应通过轮询 `GET .../inventory` 来获取进度和最终结果。
*   **扩展数据模型**：
    *   新增 `upload_sessions` 表记录上传状态。
    *   修改 `imaging_series` 表，允许 `file_id` 为空（用于标识转换后的 BIDS 序列），并增加 `session_id` 和 `bids_path` 字段。
    *   新增 `sequence_findings` 表或在 `imaging_series` 中显式存储 `supported_for_processing` 状态及不支持的原因，避免 Chat Agent 每次都要重新解析 JSON。
*   **明确错误处理合同**：对于 DICOM 转换中的“部分失败”（Partial Failures），API 应返回具体失败的 Series UID 或文件名列表，而不仅仅是一个状态码。

### 4. 可选建议 (Optional Suggestions)
*   **存储策略配置化**：方案提到的 BIDS 归档（软链接 vs 复制）建议在后端配置文件中提供全局开关，默认优先使用软链接以节省磁盘空间。
*   **支持分块上传 (Chunked Upload)**：在 `remote` 模式下，针对 GB 级别的医学影像数据，建议 API 支持分块上传协议（如 TUS 或简单的范围上传），以提高大文件稳定性。

### 5. MVP 可实现性评估
**结论：是 (Implementable)**。
该方案逻辑自洽，核心流程（上传 -> 转换 -> BIDS 归档 -> 序列识别 -> 任务分发）闭环清晰。虽然在数据库架构和异步处理上需要进一步细化，但现有的核心设计已足以支持一个功能完备的最小可行性产品。

---
**Gemini Review Agent Round 2** | 2026-05-13
