# 代码仓库功能分类与地址索引

本文档按功能域梳理当前仓库的主要能力、访问入口和代码位置。仓库根目录为 `C:\Users\A\Documents\New project 2`。

## 1. 总体项目

| 功能 | 说明 | 对应地址 |
| --- | --- | --- |
| 产品定位 | Image Agent，面向神经影像研究流程的引导式执行系统，包含上传、识别、工作流确认、任务观察、结果审查、报告导出和 Agent/RAG 解释。 | `README.md` |
| 后端服务 | FastAPI 控制平面，负责认证、项目、上传、序列、任务、结果、报告、Agent、RAG、运行时状态。 | `apps/api` |
| Web 控制台 | React/Vite 前端，用于项目管理、影像导入、工作流启动、任务监控、结果和报告审查。 | `apps/console` |
| 桌面界面壳 | 早期/本地打包用 React/Vite 桌面向界面。 | `apps/desktop` |
| 运行数据 | SQLite、上传文件、衍生结果、日志、Agent incubation 等本地运行数据。 | `data` |
| RAG 索引 | 本地 RAG 分块、manifest 和 Elasticsearch hybrid search 配置。 | `.rag_index` |
| 项目文档 | API、架构、部署、RAG、工作流、技能、验收报告和工作日志。 | `docs` |
| 安装/运维脚本 | Bootstrap、仓库卫生检查、Docker 权限配置、前端契约测试、模型连通性验证。 | `scripts` |

## 2. 启动入口和服务地址

| 服务 | 默认地址 | 启动方式 | 入口文件 |
| --- | --- | --- | --- |
| API 后端 | `http://<server>:8000` | 在 `apps/api` 下运行 `uvicorn app.main:app --host 0.0.0.0 --port 8000` | `apps/api/app/main.py` |
| Web 控制台 | Vite 默认 `http://localhost:5173`，README 示例也使用 `5180` | 在 `apps/console` 下运行 `npm run dev -- --host 0.0.0.0 --port 5180` | `apps/console/src/main.tsx` |
| 桌面界面壳 | Vite 默认端口 | 在 `apps/desktop` 下运行 `npm run dev` | `apps/desktop/src/main.jsx` |
| API 文档 | `http://<server>:8000/docs` | FastAPI 自动生成 | `apps/api/app/app_factory.py` |

前端 API 基址默认规则在 `apps/console/src/lib/api.ts`：浏览器当前协议和主机名加 `:8000`。也可以通过浏览器 `localStorage.apiBase` 或设置页修改。

## 3. Web 控制台页面地址

路由集中定义在 `apps/console/src/App.tsx`。

| 页面功能 | 浏览器地址 | 主要代码 |
| --- | --- | --- |
| 登录页 | `/`、`/login` | `apps/console/src/routes/LoginPage.tsx` |
| 项目列表/创建/选择 | `/projects` | `apps/console/src/routes/ProjectsPage.tsx` |
| Gemini 独立界面 | `/gemini` | `apps/console/src/routes/GeminiStandaloneApp.tsx` |
| 项目仪表盘 | `/projects/:projectId/dashboard` | `apps/console/src/routes/DashboardPage.tsx` |
| 影像导入/上传 | `/projects/:projectId/ingest` | `apps/console/src/routes/IngestPage.tsx` |
| 工作流目录/启动 | `/projects/:projectId/workflows` | `apps/console/src/routes/WorkflowsPage.tsx` |
| 任务列表/任务状态 | `/projects/:projectId/tasks` | `apps/console/src/routes/TasksPage.tsx` |
| 结果列表 | `/projects/:projectId/results` | `apps/console/src/routes/ResultsIndexPage.tsx` |
| 单任务结果详情 | `/projects/:projectId/results/:taskId` | `apps/console/src/routes/ResultDetailPage.tsx` |
| 科学报告入口 | `/projects/:projectId/reports` | `apps/console/src/routes/ReportsPage.tsx` |
| Agent Review / RAG 对话 | `/projects/:projectId/agent` | `apps/console/src/routes/AgentPage.tsx` |
| 设置/运行时状态 | `/projects/:projectId/settings` | `apps/console/src/routes/SettingsPage.tsx` |
| 布局、导航、空状态、日志、状态徽章 | 所有受保护项目页 | `apps/console/src/components` |
| API client、类型、结果 artifact、工作流归一化 | 前端共享逻辑 | `apps/console/src/lib` |

## 4. 后端 API 功能地址

FastAPI 应用创建在 `apps/api/app/app_factory.py`，所有路由模块在 `apps/api/app/routes`。

### 4.1 系统和运行时

| API | 功能 | 代码地址 |
| --- | --- | --- |
| `GET /health` | 健康检查。 | `apps/api/app/routes/system.py` |
| `GET /workflows` | 返回固定工作流目录。 | `apps/api/app/routes/system.py` |
| `GET /result-contract` | 返回结果契约。 | `apps/api/app/routes/system.py` |
| `GET /deployment` | 返回部署、生产就绪、模型网关、RAG 等状态。 | `apps/api/app/routes/system.py` |
| `GET /runtime/containers` | 检查运行时容器/镜像状态。 | `apps/api/app/routes/system.py` |
| `GET /runtime/probe` | 运行时探测。 | `apps/api/app/routes/system.py` |
| `GET /admin/containers` | 管理视角容器信息。 | `apps/api/app/routes/system.py` |

### 4.2 认证和项目

| API | 功能 | 代码地址 |
| --- | --- | --- |
| `POST /auth/login` | 控制台登录，默认开发账号来自环境配置。 | `apps/api/app/routes/auth.py`、`apps/api/app/security.py` |
| `GET /projects` | 项目列表。 | `apps/api/app/routes/projects.py` |
| `POST /projects` | 创建项目。 | `apps/api/app/routes/projects.py` |

认证开关和 token 逻辑在 `apps/api/app/security.py`，可通过 `IMAGE_AGENT_REQUIRE_AUTH`、`IMAGE_AGENT_CONSOLE_USERNAME`、`IMAGE_AGENT_CONSOLE_PASSWORD`、`IMAGE_AGENT_CONSOLE_TOKEN` 配置。

### 4.3 上传、数据集导入和序列识别

| API | 功能 | 代码地址 |
| --- | --- | --- |
| `POST /projects/{project_id}/upload` | 上传单个 NIfTI/普通影像文件并检测序列。 | `apps/api/app/routes/uploads.py`、`apps/api/app/services/upload_service.py` |
| `POST /projects/{project_id}/upload-dwi` | 上传 DWI NIfTI、bval、bvec、JSON sidecar。 | `apps/api/app/routes/uploads.py`、`apps/api/app/imaging/dwi_sidecars.py` |
| `POST /projects/{project_id}/upload-dicom` | 上传 DICOM zip 并登记 DICOM 序列。 | `apps/api/app/routes/uploads.py` |
| `POST /projects/{project_id}/datasets/upload-session` | 创建数据集上传会话。 | `apps/api/app/routes/uploads.py` |
| `POST /projects/{project_id}/datasets/{upload_session_id}/ingest` | 导入混合数据集 zip，生成 inventory。 | `apps/api/app/routes/uploads.py`、`apps/api/app/imaging/ingest.py` |
| `GET /projects/{project_id}/datasets/{upload_session_id}/inventory` | 查询数据集清单和识别结果。 | `apps/api/app/routes/uploads.py` |
| `GET /projects/{project_id}/files` | 项目文件列表。 | `apps/api/app/routes/uploads.py` |
| `DELETE /projects/{project_id}/files/{file_id}` | 删除项目文件。 | `apps/api/app/routes/uploads.py` |
| `GET /projects/{project_id}/series` | 项目影像序列列表。 | `apps/api/app/routes/series.py` |
| `GET /series/{series_id}` | 获取单个序列详情。 | `apps/api/app/routes/series.py` |

影像检测和序列记录相关代码在 `apps/api/app/imaging`，上传文件落盘工具在 `apps/api/app/storage/upload_files.py`。

### 4.4 工作流启动和任务执行

| API | 功能 | 代码地址 |
| --- | --- | --- |
| `POST /series/{series_id}/run` | 直接对序列启动固定工作流。 | `apps/api/app/routes/series.py`、`apps/api/app/services/task_service.py` |
| `GET /projects/{project_id}/tasks` | 查询项目任务列表。 | `apps/api/app/routes/tasks.py` |
| `GET /tasks/{task_id}` | 查询单个任务。 | `apps/api/app/routes/tasks.py` |
| `GET /tasks/{task_id}/logs` | 获取脱敏任务日志。 | `apps/api/app/routes/tasks.py`、`apps/api/app/services/result_service.py` |
| `GET /tasks/{task_id}/events` | 获取任务事件和远端日志摘要。 | `apps/api/app/routes/tasks.py` |
| `GET /tasks/{task_id}/outputs` | 获取任务输出 artifact 列表。 | `apps/api/app/routes/tasks.py` |
| `GET /tasks/{task_id}/observe-repair` | 只读观察/修复建议入口，返回安全脱敏 payload。 | `apps/api/app/routes/tasks.py`、`apps/api/app/agent/tools.py` |

执行层支持 Celery/Redis 和本地线程 fallback：

| 功能 | 代码地址 |
| --- | --- |
| 执行计划和任务执行器 | `apps/api/app/execution/task_executor.py` |
| Celery app 配置 | `apps/api/app/execution/celery_app.py` |
| Celery task 定义 | `apps/api/app/execution/celery_tasks.py` |
| 队列选择：CPU/GPU/SANDBOX/LONG | `apps/api/app/execution/queueing.py` |
| Worker 实际执行入口 | `apps/api/app/execution/worker.py` |

### 4.5 结果、artifact 和报告

| API | 功能 | 代码地址 |
| --- | --- | --- |
| `GET /tasks/{task_id}/result-summary` | 读取统一结果摘要。 | `apps/api/app/routes/results.py`、`apps/api/app/services/result_service.py` |
| `GET /tasks/{task_id}/artifact-manifest` | 生成前端可预览/下载的 artifact manifest。 | `apps/api/app/routes/results.py`、`apps/api/app/workflows/artifact_manifest.py` |
| `GET /tasks/{task_id}/export-bundle` | 直接导出任务结果包。 | `apps/api/app/routes/results.py` |
| `POST /tasks/{task_id}/export-bundle-ticket` | 创建下载 ticket。 | `apps/api/app/routes/results.py` |
| `GET /tasks/{task_id}/export-bundle-download` | 使用 ticket 下载结果包。 | `apps/api/app/routes/results.py` |
| `GET /tasks/{task_id}/artifacts/{relative_path:path}` | 下载单个 artifact。 | `apps/api/app/routes/results.py` |
| `POST /agent/tools/verify-scientific-reports` | 校验科学报告。 | `apps/api/app/routes/reports.py` |
| `POST /projects/{project_id}/bold/group-analysis` | BOLD 组分析。 | `apps/api/app/routes/reports.py`、`apps/api/app/workflows/bold_group_analysis.py` |
| `POST /projects/{project_id}/bold/descriptive-review` | BOLD 描述性审查。 | `apps/api/app/routes/reports.py`、`apps/api/app/workflows/bold_descriptive_review.py` |

报告和结果契约相关实现主要在 `apps/api/app/workflows/scientific_reports.py`、`apps/api/app/workflows/result_contract.py`、`apps/api/app/workflows/bold_result_contract.py`。

### 4.6 Agent、RAG 和模型网关

| API | 功能 | 代码地址 |
| --- | --- | --- |
| `GET /agent/rag/status` | 查询 RAG 索引状态。 | `apps/api/app/routes/agent.py` |
| `POST /agent/rag/rebuild` | 重建 RAG 索引。 | `apps/api/app/routes/agent.py` |
| `POST /agent/rag/query` | 直接 RAG 查询。 | `apps/api/app/routes/agent.py` |
| `GET /agent/model/status` | 查询模型网关状态。 | `apps/api/app/routes/agent.py` |
| `POST /agent/runs` | Agent 主入口，支持问题回答、工作流准备、确认请求。 | `apps/api/app/routes/agent.py`、`apps/api/app/services/agent_service.py` |
| `GET /agent/runs/{agent_run_id}` | 查询单次 Agent run。 | `apps/api/app/routes/agent.py` |
| `POST /agent/runs/{thread_id}/resume` | 恢复并批准/拒绝 Agent workflow confirmation。 | `apps/api/app/routes/agent.py` |
| `GET /projects/{project_id}/agent-runs` | 项目 Agent 历史记录。 | `apps/api/app/routes/agent.py` |
| `POST /chat` | 兼容旧聊天入口，新功能应优先用 `/agent/runs`。 | `apps/api/app/routes/chat.py` |

Agent 核心模块：

| 功能 | 代码地址 |
| --- | --- |
| LangGraph/Agent 图和运行器 | `apps/api/app/agent/graph.py`、`apps/api/app/agent/langgraph_runner.py` |
| Agent 状态、线程、run ledger | `apps/api/app/agent/state.py`、`apps/api/app/agent/thread_store.py`、`apps/api/app/agent/run_ledger.py` |
| 工具注册和调度 | `apps/api/app/agent/tool_registry.py`、`apps/api/app/agent/tool_dispatcher.py`、`apps/api/app/agent/tools.py` |
| RAG 索引、编排和评估 | `apps/api/app/agent/rag_index.py`、`apps/api/app/agent/rag_orchestration.py`、`apps/api/app/agent/rag_eval.py` |
| 模型网关 | `apps/api/app/agent/model_gateway.py` |
| Prompt 和技能加载 | `apps/api/app/agent/prompt_loader.py`、`apps/api/app/agent/skill_loader.py` |
| Incubation/未知工作流提案 | `apps/api/app/agent/incubation.py` |
| Agent API 契约 | `apps/api/app/agent/contracts.py` |

## 5. 固定工作流能力

工作流目录和运行时镜像约束主要在 `apps/api/app/workflows/registry.py`。

| 工作流 ID | 功能分类 | 说明 | 主要代码/文档 |
| --- | --- | --- | --- |
| `t1_deepprep_anat_report` | T1 | T1 DeepPrep 解剖处理、QC、结构化结果和 HTML 科学报告。 | `apps/api/app/workflows/deepprep.py`、`apps/api/app/workflows/t1_results.py`、`docs/rag/workflows/t1_deepprep_anat_report.md` |
| `t1_deepprep` | T1 | T1 DeepPrep 处理流程。 | `apps/api/app/workflows/deepprep.py` |
| `t1_deepprep_validate` | T1 | T1 DeepPrep 预检/验证路径。 | `apps/api/app/workflows/deepprep.py` |
| `bold_deepprep` | BOLD | 旧版/兼容 BOLD DeepPrep 流程。 | `apps/api/app/workflows/deepprep.py`、`apps/api/app/workflows/bold_results.py` |
| `bold_deepprep_validate` | BOLD | BOLD DeepPrep 验证路径。 | `apps/api/app/workflows/deepprep.py` |
| `bold_fmriprep` | BOLD | fMRIPrep BOLD 预处理。 | `apps/api/app/workflows/pipeline.py`、`apps/api/app/workflows/bold_results.py` |
| `bold_fmriprep_xcpd_report` | BOLD | fMRIPrep + XCP-D 完整处理、指标、QC 和报告。 | `apps/api/app/workflows/bold_metrics.py`、`apps/api/app/workflows/bold_results.py`、`docs/rag/workflows/bold_fmriprep_xcpd_report.md` |
| `bold_fmriprep_xcpd_report_validate` | BOLD | fMRIPrep + XCP-D 验证路径。 | `apps/api/app/workflows/pipeline.py` |
| `dwi_fast_gpu_dti` | DWI | DWI fast GPU DTI，输出 FA/MD/AD/RD、atlas 表、QC 和报告。 | `apps/api/app/workflows/dwi_fast_dti.py`、`docs/rag/workflows/dwi_fast_gpu_dti.md` |
| `dwi_fast_gpu_dti_validate` | DWI | DWI fast GPU DTI 验证路径。 | `apps/api/app/workflows/dwi_fast_dti.py` |

其他工作流辅助模块：

| 功能 | 地址 |
| --- | --- |
| 工作流资格判断 | `apps/api/app/workflows/eligibility.py` |
| Docker 命令封装 | `apps/api/app/workflows/docker_command.py` |
| Native QC 收集 | `apps/api/app/workflows/native_qc.py` |
| QSIPrep 输出处理 | `apps/api/app/workflows/qsiprep_outputs.py` |
| 远端脚本/远端执行辅助 | `apps/api/app/workflows/remote_scripts.py` |
| 任务日志和 stale task 恢复 | `apps/api/app/workflows/task_logs.py`、`apps/api/app/workflows/stale_tasks.py`、`apps/api/app/workflows/recovery.py` |

## 6. 数据库和文件存储地址

配置入口在 `apps/api/app/core/config.py`。默认根目录是仓库根目录，也可用 `IMAGE_AGENT_ROOT` 覆盖。

| 数据 | 默认位置 | 说明 |
| --- | --- | --- |
| SQLite 数据库 | `data/app.db` | 表结构在 `apps/api/app/db/schema.sql` |
| 上传原始文件 | `data/projects/{project_id}/raw` | 用户上传的 NIfTI、DWI sidecar、DICOM zip、数据集等 |
| 工作流输出 | `data/projects/{project_id}/derivatives/{task_id}` | 任务衍生结果、报告、artifact |
| 任务日志 | `data/projects/{project_id}/logs/{task_id}.log` | 后端任务日志 |
| Agent incubation | `data/agent_incubation` | 未知/不支持工作流提案记录 |
| RAG 索引 | `.rag_index` | chunks、manifest、Elasticsearch 配置 |

主要数据库表：

| 表 | 作用 |
| --- | --- |
| `projects` | 项目 |
| `files` | 项目文件 |
| `upload_sessions` | 数据集上传会话 |
| `sequence_findings` | 数据集序列发现结果 |
| `imaging_series` | 影像序列 |
| `tasks` | 工作流任务 |
| `execution_runs`、`execution_attempts`、`execution_events` | 执行层审计和队列状态 |
| `outputs` | 任务输出 artifact |
| `chat_messages` | 兼容聊天记录 |
| `agent_runs`、`agent_run_events` | Agent run ledger |
| `agent_confirmations`、`agent_confirmation_events` | Agent 工作流确认记录 |

## 7. 配置、部署和运行时能力

| 功能 | 地址 |
| --- | --- |
| 环境变量和默认路径 | `apps/api/app/core/config.py` |
| CORS、生产模式、部署 scope | `apps/api/app/app_factory.py` |
| 启动时初始化 DB、请求校验异常处理 | `apps/api/app/app_hooks.py` |
| Bearer 认证中间件 | `apps/api/app/security.py` |
| Docker 访问配置脚本 | `scripts/configure_docker_access.py` |
| 安装/bootstrap 主脚本 | `scripts/bootstrap_image_agent.py` |
| 远端生产部署文档 | `docs/deployment.md`、`docs/deployment/remote-agent-production.md` |
| 远端验收模板/日志 | `docs/deployment/remote-agent-acceptance-template.md`、`docs/deployment/remote-agent-acceptance-log-20260607.md` |

## 8. RAG、知识库和技能文档

| 功能 | 地址 |
| --- | --- |
| RAG 合同和评估文档 | `docs/rag/contracts` |
| 模态/BIDS 数据要求 | `docs/rag/data-requirements` |
| T1/BOLD 结果解释 | `docs/rag/interpretation` |
| 非诊断边界和 RAG 优先级 | `docs/rag/safety` |
| 常见错误排查 | `docs/rag/troubleshooting/common-errors.md` |
| 厂商/官方资料缓存 | `docs/rag/vendor` |
| QSIPrep/QSIRecon 知识库 | `docs/knowledge-base/qsirecon` |
| Image Agent 技能 | `docs/skills/image-agent-*`、`docs/skills/neuroimaging-workflow-runner` |
| RAG 构建/评估脚本 | `apps/api/scripts/setup_elasticsearch_hybrid_rag.py`、`apps/api/scripts/evaluate_rag.py`、`apps/api/scripts/fetch_vendor_docs.py` |

## 9. 脚本和测试地址

| 分类 | 地址 | 说明 |
| --- | --- | --- |
| 根级脚本 | `scripts` | Bootstrap、Docker、仓库卫生、前端契约、rawchat 连通性 |
| API 运维脚本 | `apps/api/scripts` | RAG、发布门禁、远端 smoke、报告再生成、stale task reconciliation 等 |
| API 测试 | `apps/api/tests` | FastAPI、Agent、RAG、工作流、结果契约、上传、执行、脚本等测试 |
| Console 测试 | `apps/console/src/**/*.test.tsx`、`apps/console/src/**/*.test.ts` | 页面、组件、API client、工作流工具测试 |
| Pytest 缓存 | `.pytest_cache`、`apps/api/.pytest_cache`、`apps/console/.pytest_cache` | 本地测试缓存，不是核心功能代码 |

## 10. 快速查找建议

| 想改的功能 | 优先看哪里 |
| --- | --- |
| 新增/修改 API | `apps/api/app/routes` 和对应 `apps/api/app/services` |
| 新增上传类型或序列识别 | `apps/api/app/imaging`、`apps/api/app/services/upload_service.py` |
| 新增固定工作流 | `apps/api/app/workflows/registry.py`、`apps/api/app/workflows/pipeline.py`、对应 `docs/rag/workflows` |
| 改 Agent 行为 | `apps/api/app/agent`、`apps/api/app/services/agent_service.py` |
| 改前端页面 | `apps/console/src/routes` |
| 改前端 API 调用 | `apps/console/src/lib/api.ts` |
| 改导航和整体布局 | `apps/console/src/components/AppShell.tsx` |
| 改结果展示和 artifact 下载 | `apps/console/src/routes/ResultDetailPage.tsx`、`apps/console/src/lib/resultArtifacts.ts`、`apps/api/app/services/result_service.py` |
| 改部署/安装流程 | `scripts/bootstrap_image_agent.py`、`docs/deployment.md` |

## 11. 工程化风险与异常管理思考

这一节从“功能能跑”提升到“真实用户、真实数据、真实网络下是否可靠”的角度看仓库。以下内容不是现有功能清单，而是维护和演进时应优先关注的工程问题。

### 11.1 Web 上传 2GB 文件的异常管理

当前上传链路：

| 环节 | 现状 | 对应代码 |
| --- | --- | --- |
| 前端上传 | 使用浏览器 `File` + `FormData`，通过 `fetch` 一次性提交 multipart 请求。 | `apps/console/src/routes/IngestPage.tsx`、`apps/console/src/lib/api.ts` |
| 后端接收 | FastAPI `UploadFile` 接收 multipart。 | `apps/api/app/routes/uploads.py` |
| 写盘方式 | `save_stream_to_path()` 按 1MB chunk 从 stream 读取、写入目标文件，并同步计算 sha256；这避免了把 2GB 文件整体读入内存。 | `apps/api/app/storage/upload_files.py` |
| 元数据入库 | 文件写盘完成后再写入 `files` 表；单文件上传会继续检测序列并写入 `upload_sessions`、`imaging_series`。 | `apps/api/app/services/upload_service.py`、`apps/api/app/db/schema.sql` |
| 混合数据集导入 | zip 先落盘；超过 `IMAGE_AGENT_SYNC_INGEST_MAX_BYTES` 后走后台处理和 inventory 轮询。 | `apps/api/app/services/upload_service.py` |

当前主要风险：

| 风险 | 可能表现 | 建议处理 |
| --- | --- | --- |
| 单请求中断 | 2GB 上传到 90% 时网络断开，浏览器只能整体重传。 | 引入分片/断点续传：`create_upload_session` 后按 chunk 上传，服务端记录 chunk offset、sha256、状态。 |
| 反向代理限制 | Nginx、网关、云负载均衡默认 body size 或 timeout 拦截。 | 部署文档明确 `client_max_body_size`、read/write timeout；API 暴露最大上传大小给前端。 |
| 浏览器无细粒度进度 | 当前 `fetch` 上传难以提供可靠 upload progress。 | 大文件上传使用 `XMLHttpRequest` 或分片上传，每片完成后更新进度。 |
| 磁盘空间不足 | 后端写到一半失败，留下不完整文件。 | 上传前检查可用空间；写入 `.part` 临时文件；完成校验后原子 rename；失败时标记并清理。 |
| DB 和文件不一致 | 文件已写入但 DB 插入失败，或 DB 有记录但文件残缺。 | 使用上传状态机：`ready/uploading/verifying/completed/failed/cancelled`；定期 reconciliation 清理孤儿文件。 |
| 重复上传 | 用户多次点击或刷新导致重复文件。 | 前端禁用重复提交；后端支持 idempotency key；以 sha256/文件名/大小识别重复。 |
| 恶意/异常压缩包 | zip bomb、路径穿越、超大解压后体积。 | DICOM/dataset zip 解压前限制条目数、总解压大小、压缩比；已有路径穿越检查，应补充体积策略。 |
| 超时和后台任务失联 | 大文件上传成功后，后台 ingest 或转换失败，用户只看到卡住。 | `upload_sessions` 持久化错误码、错误阶段、最近心跳、可重试标记；前端轮询展示明确失败原因。 |
| 敏感路径/患者信息泄露 | 错误日志把本机路径、token、患者标识返回给前端。 | 延续现有脱敏策略，所有异常响应只返回安全错误码和用户可读原因；详细日志留服务端。 |

推荐的大文件上传状态机：

| 状态 | 含义 | 前端行为 |
| --- | --- | --- |
| `ready` | 上传会话已创建，等待文件分片。 | 展示等待上传。 |
| `uploading` | 分片上传中。 | 展示百分比、速度、剩余时间、暂停/取消。 |
| `verifying` | 服务端合并分片、校验大小和 sha256。 | 展示“正在校验”。 |
| `uploaded` | 原始文件安全落盘，但尚未完成影像识别。 | 可进入后台导入状态。 |
| `ingesting` | 正在 DICOM/NIfTI/BIDS 识别或转换。 | 轮询 inventory。 |
| `completed` | 上传和识别完成。 | 刷新 series/tasks。 |
| `failed` | 上传或导入失败。 | 展示可恢复错误、重试入口。 |
| `cancelled` | 用户取消。 | 清理临时文件，允许重新上传。 |

建议的 API 演进：

| API | 作用 | 备注 |
| --- | --- | --- |
| `POST /projects/{project_id}/uploads/sessions` | 创建大文件上传会话，声明文件名、大小、MIME、预期 sha256。 | 可复用现有 `upload_sessions` 表，也可新增 chunk 表。 |
| `PUT /projects/{project_id}/uploads/sessions/{session_id}/chunks/{index}` | 上传单个分片。 | 请求带 `Content-Range`、chunk sha256。 |
| `GET /projects/{project_id}/uploads/sessions/{session_id}` | 查询已上传分片、状态、错误码。 | 用于断点续传和刷新恢复。 |
| `POST /projects/{project_id}/uploads/sessions/{session_id}/complete` | 合并分片、校验、原子提交。 | 成功后写入 `files` 并触发 ingest。 |
| `DELETE /projects/{project_id}/uploads/sessions/{session_id}` | 取消上传并清理临时文件。 | 需要幂等。 |

建议的代码落点：

| 改造点 | 地址 |
| --- | --- |
| 上传 session/chunk 路由 | `apps/api/app/routes/uploads.py` |
| 上传状态机和合并校验服务 | `apps/api/app/services/upload_service.py` |
| 安全写盘、`.part`、rename、sha256 工具 | `apps/api/app/storage/upload_files.py` |
| 新增 chunk/session 表或扩展 schema | `apps/api/app/db/schema.sql` |
| 前端分片上传、进度、暂停、恢复 | `apps/console/src/routes/IngestPage.tsx`、`apps/console/src/lib/api.ts` |
| 大文件上传配置展示 | `apps/console/src/routes/SettingsPage.tsx`、`GET /deployment` |
| 异常和重试测试 | `apps/api/tests/test_upload_file_storage.py`、`apps/api/tests/test_api_flow.py`、`apps/console/src/lib/api.test.ts` |

### 11.2 异常分类建议

| 分类 | 示例 | 用户提示 | 服务端处理 |
| --- | --- | --- | --- |
| 用户输入错误 | 文件类型不支持、DWI 缺少 bval/bvec/JSON。 | 明确指出缺哪个文件或哪类格式不支持。 | 返回 400/422，记录安全错误码。 |
| 网络/客户端中断 | 上传断线、浏览器刷新。 | 提示可继续上传或重新选择文件。 | 保留可恢复 session，过期后清理。 |
| 资源不足 | 磁盘不足、CPU/GPU 队列满。 | 提示资源不足和建议稍后重试。 | 返回 507/503 或业务错误码，写入事件。 |
| 后台处理失败 | DICOM 转换失败、BIDS 识别失败。 | 展示失败阶段和可操作建议。 | `upload_sessions.error_message` 脱敏保存，inventory 标记失败。 |
| 下游工作流失败 | Docker 不可用、许可证缺失、容器镜像缺失。 | 引导到 Settings/Runtime 检查。 | 任务状态 `failed`，写入 `execution_events`。 |
| 安全风险 | zip path traversal、疑似 zip bomb、非法路径。 | 提示文件包不安全或结构异常。 | 立即拒绝，保留审计日志，不回显敏感路径。 |
| 系统缺陷 | 未捕获异常、DB 写入失败。 | 展示通用失败和 request id。 | 结构化日志、告警、reconciliation 修复不一致状态。 |

### 11.3 可靠性和可观测性清单

| 维度 | 建议 |
| --- | --- |
| 幂等性 | 上传、任务启动、Agent confirmation 都应有幂等键，避免刷新/重试创建重复任务。 |
| 事务边界 | 文件写盘和 DB 提交之间要有补偿机制；不能假设两者一定同时成功。 |
| 清理机制 | `.part`、过期 chunk、失败 session、孤儿 outputs 需要定时清理或启动时 reconciliation。 |
| 限流和配额 | 按用户/项目限制并发上传数、单文件大小、项目总容量、后台导入并发。 |
| 错误码 | 面向前端定义稳定业务错误码，避免 UI 解析任意错误字符串。 |
| 日志 | 每个上传/任务/Agent run 应有 correlation id，日志中严禁明文 token、患者标识、绝对路径回显到前端。 |
| 前端体验 | 大文件上传必须有进度、取消、重试、断点恢复、错误原因和下一步建议。 |
| 测试 | 加入模拟中断、磁盘不足、DB 插入失败、重复请求、恶意 zip、后台处理超时的测试。 |

### 11.4 当前仓库已有的可靠性基础

| 已有基础 | 地址 |
| --- | --- |
| 上传流式写盘和 sha256 | `apps/api/app/storage/upload_files.py` |
| 上传 session 和 inventory 状态 | `apps/api/app/db/schema.sql`、`apps/api/app/services/upload_service.py` |
| 后台导入路径 | `apps/api/app/services/background.py`、`apps/api/app/services/upload_service.py` |
| 任务事件和 execution 审计表 | `apps/api/app/db/schema.sql`、`apps/api/app/execution` |
| 日志/metadata 脱敏 | `apps/api/app/routes/tasks.py`、`apps/api/app/services/result_service.py`、`apps/console/src/lib/redaction.ts` |
| 运行时/部署检查 | `apps/api/app/routes/system.py`、`apps/api/app/services/agent_service.py`、`apps/console/src/routes/SettingsPage.tsx` |
