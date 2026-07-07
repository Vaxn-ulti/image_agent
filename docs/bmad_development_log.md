# BMAD Development Log

本日志记录 Image Agent 按 BMAD-style 工作流推进生产级后端重构的过程。BMAD 在本项目中被映射为：文档驱动、角色分工、持续验证、阶段性 commit 备份。

## 2026-07-07

### Checkpoint 0: Execution Control Plane Baseline

- 基于 `docs/image_agent_production_implementation_spec.md` 确认当前开发方向：单机/科室内网生产版、registry-first、LangGraph 分层编排、Celery/Redis 执行控制面。
- 已有基线改动包含：
  - `ExecutionPlan` / `ApprovedExecutionPlan` 合同。
  - Celery/Redis 队列路由和本地 fallback executor。
  - `execution_runs`、`execution_attempts`、`execution_events` 表。
  - LangGraph 主图初步重排为 intake、safety、intent、answer/tool route、read-only、fixed workflow、incubation、observe repair。
  - 后端聚焦测试覆盖 execution plan、task executor、task service、agent graph 和 API flow。
- 验证记录：
  - 工作目录：`apps/api`
  - 命令：`python -m pytest tests/test_agent_graph.py tests/test_execution_plan_contract.py tests/test_task_executor.py tests/test_execution_task_service.py tests/test_api_flow.py::test_full_t1_mock_flow tests/test_api_flow.py::test_task_status_responses_omit_backend_log_path tests/test_agent_api.py::test_agent_resume_preserves_canonical_workflow_type_and_records_runtime_alias tests/test_requirements_contract.py tests/test_repository_hygiene.py -q`
  - 结果：`63 passed, 3 warnings`

### BMAD Role Mapping

- PM：维护 spec、验收标准、优先级和开发日志。
- Architect：控制模块边界，保证 LangGraph、ExecutionPlan、Registry、RAG/KG、Execution Control Plane 分层清晰。
- Dev：按小步实现后端模块，优先补齐生产地基。
- QA：每轮运行聚焦测试，后续补充回归评估集。
- DevOps：关注 Celery/Redis、DB state machine、容器执行、日志、备份、可观测性。

### Next Iteration Scope

下一轮优先实现：`IntentDecision` 模型、规则优先意图识别、置信度门控、运行策略预算，并把 LangGraph 主图中的意图节点从字符串启发式升级为可测试的结构化决策。
