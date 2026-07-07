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

### Checkpoint 2: Production Intent Routing And LangGraph Stage Split

- 基于用户要求“所有任务都按真实 production 级开发”，将结构化意图从第一版 normalizer 升级为三层生产路由：
  - 规则层：`classify_rule_intent()` 输出 `RuleIntentSignal`，覆盖 inventory/capability、status、result analysis、显式 launch、否定 launch、incubation/new workflow 语言。
  - LLM 层：planner schema 现在要求 `intent_category`、`intent_subcategory`、`confidence`、`evidence_spans`、`risk_level`、`ambiguities`、`route_recommendation`。
  - 融合层：`normalize_intent_decision()` 输出 `intent_decision.v2` audit block，保留 rule signal、LLM signal、final gate、conflict、policy 和 reasons。
- 新 LangGraph 图设计已落地：
  - compiled graph 和 deterministic fallback 都按 `run_intake -> safety_risk_router -> rule_intent_classifier -> llm_intent_planner -> intent_fusion_gate -> answer_or_task_router` 执行。
  - public `graph_state` 暴露安全审计字段：`intent_decision`、`rule_intent_signal`、`llm_intent_signal`。
  - 旧 `classify_intent` 保留为兼容 wrapper，但新图不依赖它。
- 安全/产品边界：
  - 否定启动、只读解释和 inventory/capability 规则优先，LLM 不能推翻。
  - LLM 缺失 confidence 对 launch-like 请求会进入 clarification/read-only，不再默认视为通过。
  - unknown/non-production workflow 仍进入 incubation，不创建 confirmation 或 production task。
  - 本轮没有远程 workflow run、没有 API restart、没有生产任务创建、没有远程部署配置变更。
- TDD / verification 记录：
  - RED：规则分类器测试因 `classify_rule_intent` 缺失失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_intent.py -q` -> `8 passed`。
  - RED：v2 fusion audit 测试因缺少 `intent_decision.v2` 字段失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_intent.py -q` -> `11 passed`。
  - RED：planner schema 测试因缺少 production intent fields 失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py::test_agent_runner_passes_json_schema_to_tool_enabled_planner apps/api/tests/test_agent_graph.py::test_agent_runner_passes_json_schema_to_no_tools_planner_fallback -q` -> `13 passed`。
  - RED：LangGraph node/fallback tests 因 state fields 和 graph nodes 缺失失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `54 passed`。
  - Combined regression：`python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py apps/api/tests/test_agent_api.py::test_agent_run_unconfigured_model_answers_inventory_without_confirmation apps/api/tests/test_agent_api.py::test_agent_run_forces_unknown_fixed_workflow_into_incubation_without_production_task -q` -> `67 passed, 3 warnings`。
  - `git diff --check` -> passed.
- Checkpoint commits：
  - `9fc56dff docs: specify production intent routing`
  - `61a862d6 docs: plan production langgraph intent routing`
  - `bbd681f0 feat: add production intent rule classifier`
  - `ebe81e91 feat: fuse rule and llm intent decisions`
  - `b308c7d9 test: require production intent planner contract`
  - `dd676944 feat: expose production intent stages in langgraph`
  - `0ee6d0a2 test: align agent api fixture with production intent contract`
- 下一步建议：
  - 在下一 BMAD checkpoint 继续 `ContextGrounder`、`PolicySnapshot`、loop budget 和 repeated-failure cutoff，将 graph stage audit 接入更完整的 run ledger/eval 统计。
