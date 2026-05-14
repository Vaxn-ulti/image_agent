Ripgrep is not available. Falling back to GrepTool.
作为 **Gemini Review Agent (Round 4)**，我已审阅了 `docs/phase4-plan-and-solve.md`。以下是从 **前端 UX** 与 **Local/Remote 部署选择** 维度的专项评审报告：

### 1. 方案亮点 (Strongest Parts)
*   **确定性清单反馈 (Deterministic Inventory):** 引入 `upload-session` 和同步/异步 Inventory 报告，解决了影像上传中“黑盒”处理的问题，前端能清晰展示转换状态（DICOM 转换数量、模态统计），极大提升了临床科研人员的信心。
*   **显式不支持声明:** 明确要求对识别但不支持的序列（如 T2 FLAIR）返回固定错误信息。这种“诚实”的 UX 设计能有效避免用户在后续工作流失败时感到困惑。
*   **BIDS 标准化透明度:** 建立了 BIDS 路径映射的透明反馈，前端可以直接展示文件在系统内部的组织方式，方便专家用户核对。

### 2. 具体风险与缺口 (Concrete Risks/Gaps)
*   **Local Mode 的“文件夹选择”限制:** 方案提到 Local 模式支持“直接文件夹上传 (Direct folder upload)”。若前端是标准 Web 应用，受限于浏览器安全沙箱，无法直接读取宿主机绝对路径。方案未明确是利用 Web Folder Upload API 还是需要通过后台文件系统选择器（API 驱动）。
*   **远程上传的稳定性风险:** DICOM 数据集通常达 GB 级。方案虽提到 `Remote mode` 使用 HTTP multipart/chunking，但未定义**断点续传**或**进度感知**的 UX 标准。在网络不稳时，大文件上传失败会导致极差的体验。
*   **部署模式的 UI 感知缺失:** 方案未定义前端如何检测或切换 `BACKEND_RUNTIME_MODE`。用户不知道当前是在本地高性能处理还是远程排队，这对预期管理至关重要。

### 3. 必须修改的建议 (Must-change Suggestions)
*   **明确 Local 模式的交互逻辑:** 必须在方案中补充：在 `local` 模式下，API 是否支持 `source_path: "/absolute/path/on/disk"` 这种非上传式的“索引”操作。如果仅靠前端上传，Local 模式的性能优势（避免重复拷贝）无法完全体现。
*   **增加上传进度反馈契约:** 在 API 响应或 Long-polling 中必须包含上传/转换的**百分比**或**子任务计数**。当前 `inventory_status: "completed"` 太过粗粒度，无法支撑 UI 进度条。

### 4. 优化建议 (Optional Suggestions)
*   **环境状态标识:** 在前端 Header 或状态栏增加“运行模式”标识（Local/Remote），并显示当前后端的基础延迟（Ping/Health Check）。
*   **BIDS 路径预览:** 在显示 Inventory 报告时，允许用户预览 BIDS 结构的逻辑树，而不是简单的 JSON 列表。
*   **缓存策略:** 建议在前端实现 `apiBase` 的自动探测逻辑，如果探测到 `localhost:8000` 可用，优先切换至 Local 模式。

### 5. MVP 可实现性评估
**结论：可以实现 (Implementable)。**
该方案在数据契约和后端逻辑上非常完备，足以支撑一个最小可用的影像上传与处理闭环。只要在执行阶段解决浏览器上传大文件夹的路径感知问题，即可交付具备生产力的 MVP。

---
*注：本次评审不涉及代理配置（Proxy Configuration）讨论。*
