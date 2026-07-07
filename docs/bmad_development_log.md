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

### Checkpoint 1: Structured Intent Decision Slice

- 基于 `docs/image_agent_production_implementation_spec.md` Phase 2 和本日志上一轮 `Next Iteration Scope`，完成第一片结构化意图决策能力：
  - 新增 `apps/api/app/agent/intent.py`，提供 `IntentDecision` Pydantic 模型和 `normalize_intent_decision()`。
  - 将 inventory/capability 解释问题、显式 fixed workflow launch、低置信度 run 请求、toolchain incubation 请求归一化为带 `intent_decision` 元数据的结构化决策。
  - `apps/api/app/agent/graph.py` 的 `_plan()` 现在在模型 planner 输出后统一调用 intent normalizer，再进入 read-only、fixed workflow confirmation 或 incubation 分支。
  - 保留 LangGraph/AgentRunner 现有执行边界：没有创建生产任务，没有运行远程 workflow，没有改动远程部署配置。
- TDD 记录：
  - RED：`python -m pytest apps/api/tests/test_agent_intent.py -q` -> 预期失败，`ModuleNotFoundError: No module named 'app.agent.intent'`。
  - GREEN：`python -m pytest apps/api/tests/test_agent_intent.py -q` -> `4 passed`。
  - RED：`python -m pytest apps/api/tests/test_agent_graph.py::test_agent_plan_uses_structured_intent_guard_for_inventory_question apps/api/tests/test_agent_graph.py::test_agent_plan_preserves_explicit_fixed_workflow_launch -q` -> 预期失败，旧 `_plan()` 缺少 `intent_decision` 且误判中文“立即运行”。
  - GREEN：`python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py::test_agent_plan_uses_structured_intent_guard_for_inventory_question apps/api/tests/test_agent_graph.py::test_agent_plan_preserves_explicit_fixed_workflow_launch -q` -> `6 passed`。
  - Graph regression：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `52 passed`。
- Checkpoint commits：
  - `67ed5d7d feat: add structured agent intent decision`
  - `1b97bdbe refactor: route agent planning through intent decision`
- 下一步建议：
  - 继续 Phase 2 的 `ContextGrounder` / `PolicySnapshot` / loop budget，不要扩大到远程 smoke 或 workflow rerun，除非先有新的 BMAD scope 和验证计划。
