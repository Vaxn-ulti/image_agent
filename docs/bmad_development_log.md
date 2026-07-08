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

### Checkpoint 3: Target Graph Product Boundaries And Engineering Decisions

- 基于用户纠偏，重新对齐 `docs/image_agent_production_implementation_spec.md` section 8 的完整 LangGraph Target Graph，而不是只围绕当前已落地的 intent 小图推进。
- 明确当前代码状态：
  - `apps/api/app/agent/langgraph_runner.py` 目前实现的是 target graph 的前段骨架：intake、safety、rule/LLM/fusion intent、coarse answer/tool route、RAG/skill、read-only/fixed/incubation/observe-repair lane。
  - 尚未完整实现 target graph 中的 requirement completeness、clarification interrupt、neuroimaging intake validation、sequence normalization、preflight-lite、capability matcher、fixed workflow recommendation、ExecutionPlan candidate、plan policy gate、authorization verification、execution control plane、worker lease/reaper/QC gate 闭环。
- 新增产品边界与工程决策文档：
  - `docs/superpowers/specs/2026-07-07-target-graph-product-boundaries.md`
  - 将 section 9 的 100 个工程问题按部署、隐私、意图/LangGraph、RAG/Registry/KG、脑影像 workflow、执行系统六类收敛为推荐决策和硬边界。
- 新增 target graph 实施计划：
  - `docs/superpowers/plans/2026-07-07-target-graph-implementation.md`
  - 下一代码切片按 target graph 顺序推进：先做 `requirement_completeness` 和 `clarification_interrupt`，再做 neuroimaging intake/normalization、capability matcher、ExecutionPlan/policy gate、authorization/execution-control boundary。
- 产品边界要点：
  - Image Agent 是研究脑影像 workflow control plane，不是临床诊断产品，不是自由远程代码执行助手。
  - fixed mature workflow 必须经过 registry、preflight、policy gate、人类授权。
  - unknown/non-production workflow 只能进入 incubation/sandbox。
  - 所有执行必须有 provenance、safe graph state、event log、artifact manifest 和 QC boundary。
- 本 checkpoint 只更新设计、计划和日志；没有远程 workflow run、没有 API restart、没有生产任务创建、没有远程部署配置变更。

### Checkpoint 4: Target Graph Slice 1 Requirement Completeness Gate

- 按新的 target graph 实施计划完成第一段代码切片：在 `select_skill` 之后、`task_planning` 之前加入 `requirement_completeness` 和 `clarification_interrupt`。
- 生产边界：
  - fixed workflow 请求在进入 task planning 前必须先检查最低可执行信息。
  - 多序列且未指定 `series_id` 时进入 clarification interrupt，不创建 confirmation 或 production task。
  - 未指定 `workflow_type` 但 registry 存在时允许后续 capability matcher 推断；只有没有 registry 可推断时才要求用户补充 workflow。
  - clarification interrupt 使用 read-only lane 终止本轮图执行，并在 safe `graph_state` 与事件流中暴露审计信息。
- 代码落点：
  - `apps/api/app/agent/langgraph_runner.py`：新增 graph nodes、conditional edge、deterministic fallback 路径、public graph state 字段。
  - `apps/api/app/agent/state.py`：新增 `requirement_completeness` state field。
  - `apps/api/tests/test_agent_graph.py`：新增 compiled graph topology 和 ambiguous tool-task clarification 测试。
- TDD / verification 记录：
  - RED：新 graph topology 测试因缺少 `requirement_completeness` / `clarification_interrupt` nodes 失败。
  - RED：ambiguous fixed workflow 测试因直接进入 confirmation/proposal 而非 clarification 失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_compiled_graph_includes_requirement_completeness_before_task_planning apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_clarifies_incomplete_tool_task_before_confirmation -q` -> `2 passed`。
  - Graph regression：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `56 passed`。
  - Combined regression：`python -m pytest apps/api/tests/test_agent_intent.py apps/api/tests/test_agent_graph.py apps/api/tests/test_agent_api.py::test_agent_run_unconfigured_model_answers_inventory_without_confirmation apps/api/tests/test_agent_api.py::test_agent_run_forces_unknown_fixed_workflow_into_incubation_without_production_task -q` -> `69 passed, 3 warnings`。
- 本 checkpoint 没有远程 workflow run、没有 API restart、没有生产任务创建、没有远程部署配置变更。

### Checkpoint 5: Target Graph Slice 2 Neuroimaging Intake And Sequence Normalization

- 按 target graph 实施计划完成第二段代码切片：在 `requirement_completeness` 之后、`task_planning` 之前加入 `neuroimaging_data_intake_validation` 和 `sequence_metadata_normalization`。
- 生产边界：
  - 本切片只消费已存在的 `project_context` / imaging ingest 结果，生成安全、可审计的 graph state；不读取原始影像文件、不运行 DICOM/NIfTI 转换、不创建任务。
  - metadata precedence 固定为 `sidecar_json -> dicom_tags -> nifti_header -> filename_tokens`，作为 graph_state 契约暴露给后续 capability matcher / policy gate。
  - unsupported recognized sequence 使用统一 limitation：`Current software does not support radiomics/processing for this sequence.`，后续 workflow 推荐不得绕开这个边界。
  - public state 只暴露 file/series 的非敏感摘要字段，不暴露原始路径或完整 sidecar。
- 代码落点：
  - `apps/api/app/agent/langgraph_runner.py`：新增两个 target graph nodes、fallback 顺序、safe public graph_state、series/file normalization helpers。
  - `apps/api/app/agent/state.py`：新增 `neuroimaging_intake` 和 `sequence_normalization` state fields。
  - `apps/api/tests/test_agent_graph.py`：新增 graph topology、metadata precedence、sidecar/header source、unsupported sequence boundary 测试。
- TDD / verification 记录：
  - RED：compiled graph test 因缺少 `neuroimaging_data_intake_validation` / `sequence_metadata_normalization` nodes 失败。
  - RED：runtime graph_state 测试因缺少 `neuroimaging_intake` 和 `sequence_normalization` 失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_compiled_graph_includes_requirement_completeness_before_task_planning apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_normalizes_neuroimaging_series_before_task_planning apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_records_unsupported_sequence_boundary -q` -> `3 passed`。
  - Graph regression：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `58 passed`。
- 本 checkpoint 没有远程 workflow run、没有 API restart、没有生产任务创建、没有远程部署配置变更。

### Checkpoint 6: Target Graph Slice 3 Capability Matcher And Registry Recommendation

- 按 target graph 实施计划完成第三段代码切片：将原本隐式藏在 `task_planning` 内的 workflow matching 拆成显式 graph stages：
  - `curated_workflow_registry`
  - `capability_matcher`
  - `fixed_workflow_recommendation`
- 生产边界：
  - fixed workflow 推荐必须来自 curated registry，不允许 LLM 自由提升未注册 workflow。
  - `agent_selectable=False` 的 registry entry 即使 capability 文本匹配，也只能记录为 excluded evidence，不能进入 fixed production recommendation。
  - capability matcher 暴露 matched workflow、series modality、query tokens、registry 规模、excluded workflow types，供后续 policy gate / eval 使用。
  - 本切片仍只到 confirmation 前推荐边界，不创建 production task。
- 代码落点：
  - `apps/api/app/agent/langgraph_runner.py`：新增三个 target graph nodes、graph/fallback 顺序、matcher audit helper、public graph_state 字段；`task_planning` 只保留策略规划，不再隐式执行 workflow matching。
  - `apps/api/app/agent/state.py`：新增 registry/matcher/recommendation state fields。
  - `apps/api/tests/test_agent_graph.py`：升级 graph topology、capability evidence、DWI match、non-agent-selectable exclusion 测试。
- TDD / verification 记录：
  - RED：compiled graph test 因缺少 `curated_workflow_registry` / `capability_matcher` / `fixed_workflow_recommendation` nodes 失败。
  - RED：capability tests 因缺少 registry/matcher/recommendation graph_state 失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_compiled_graph_includes_requirement_completeness_before_task_planning apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_matches_fixed_workflow_from_capability_metadata_when_planner_omits_type apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_matches_dwi_fixed_workflow_from_capability_metadata apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_does_not_capability_match_non_agent_selectable_workflow -q` -> `4 passed`。
  - Graph regression：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `58 passed`。
- 本 checkpoint 没有远程 workflow run、没有 API restart、没有生产任务创建、没有远程部署配置变更。

### Checkpoint 7: Target Graph Slice 4 ExecutionPlan Candidate And Policy Gate

- 按 target graph 实施计划完成第四段代码切片：在 fixed workflow recommendation 之后、authorization/confirmation 之前加入：
  - `execution_plan_candidate`
  - `plan_policy_gate`
- 生产边界：
  - fixed workflow 在进入 confirmation 前必须生成可审计 plan candidate。
  - policy gate 阻断缺 workflow id、缺 series id、缺 input manifest、容器镜像未固定、unsafe mount、缺 QC expectations 的计划。
  - `:latest` 或无 tag 容器镜像不能进入 confirmation；本轮新增测试覆盖 `example/custom:latest` 被挡在 confirmation/thread 创建之前。
  - 通过 gate 只代表允许进入人工确认卡，不代表已授权执行；本切片仍不创建 production task。
- 代码落点：
  - `apps/api/app/agent/langgraph_runner.py`：新增 plan candidate / policy gate nodes、fallback 顺序、container image pin 检查、input manifest 构造、blocked gate 返回。
  - `apps/api/app/agent/state.py`：新增 `execution_plan_candidate` 和 `plan_policy_gate` state fields。
  - `apps/api/tests/test_agent_graph.py`：新增 graph topology、固定 workflow plan candidate、unpinned image confirmation-block 测试。
- TDD / verification 记录：
  - RED：compiled graph test 因缺少 `execution_plan_candidate` / `plan_policy_gate` nodes 失败。
  - RED：fixed workflow graph_state 测试因缺少 plan candidate / policy gate 失败。
  - RED：custom `:latest` workflow 未被 gate 拦截并掉入 confirmation 准备失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_compiled_graph_includes_requirement_completeness_before_task_planning apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_matches_fixed_workflow_from_capability_metadata_when_planner_omits_type apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_blocks_unpinned_execution_plan_before_confirmation -q` -> `3 passed`。
  - Graph regression：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `59 passed`。
- 本 checkpoint 没有远程 workflow run、没有 API restart、没有生产任务创建、没有远程部署配置变更。

### Checkpoint 8: Target Graph Slice 5 Authorization And Execution Control Boundary

- 按 target graph 实施计划完成第五段代码切片：在 policy gate 之后、fixed workflow confirmation 之前加入：
  - `authorization_scope_classifier`
  - `execution_control_boundary`
- 生产边界：
  - 初次 graph run 只能到 `pending_human_confirmation`，`task_creation_allowed=false`，不允许创建 production task。
  - fixed mature workflow 的授权范围明确为 `fixed_mature_workflow`，TTL 固定为 3600 秒，并绑定 project/series/workflow。
  - resume 时只有 server-side pending confirmation、未过期、fingerprint verified 才标记 `human_approved` 并进入 `create_workflow_task` execution-control adapter。
  - incubation/sandbox/new tool 不允许通过 fixed workflow confirmation 进入 production task。
- 代码落点：
  - `apps/api/app/agent/langgraph_runner.py`：新增 authorization scope / execution boundary nodes、graph/fallback 顺序、public graph_state；增强 resume annotation，暴露 approved 后的 execution-control boundary。
  - `apps/api/app/agent/state.py`：新增 `authorization_scope` 和 `execution_control_boundary` state fields。
  - `apps/api/tests/test_agent_graph.py`：新增 graph topology、初次 run pending authorization、resume approved adapter boundary 断言。
- TDD / verification 记录：
  - RED：compiled graph test 因缺少 authorization / execution-control nodes 失败。
  - RED：fixed workflow confirmation graph_state 因缺少 pending authorization / task_creation_allowed=false 失败。
  - RED：resume approved graph_state 因缺少 human-approved execution-control boundary 失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_graph.py::test_langgraph_compiled_graph_includes_requirement_completeness_before_task_planning apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_matches_fixed_workflow_from_capability_metadata_when_planner_omits_type apps/api/tests/test_agent_graph.py::test_langgraph_agent_runner_resume_marks_fixed_workflow_graph_gate -q` -> `3 passed`。
  - Graph regression：`python -m pytest apps/api/tests/test_agent_graph.py -q` -> `59 passed`。
- 本 checkpoint 没有远程 workflow run、没有 API restart、没有未授权生产任务创建、没有远程部署配置变更。

### Checkpoint 9: DeepSeek Production Gateway Boundary Cutover

- 按新的生产规划边界完成模型网关目标切换：
  - fast-launch readiness 不再把 rawchat/GPT-5.5 Responses tool-loop 作为生产目标；
  - 新生产目标为 DeepSeek OpenAI-compatible chat completions；
  - DeepSeek 目标必须直连 `https://api.deepseek.com`，且 `trust_env_proxy=false`。
- 生产边界：
  - DeepSeek chat completions 支持文本和结构化 JSON，但不提供 Responses tool-loop；
  - workflow 启动仍必须经过后端 pending confirmation / resume / fingerprint verified 路径；
  - 旧 rawchat 相关历史日志保留为审计记录，但部署文档和 readiness gate 不再要求 rawchat。
- 环境处理：
  - 本地 `.env` 已写入新的 DeepSeek key 与 `IMAGE_AGENT_MODEL_*` / `DEEPSEEK_*` 配置；
  - `.env` 被 `.gitignore` 覆盖，未进入 git；
  - 日志只记录配置状态，不记录明文密钥。
- 代码落点：
  - `apps/api/app/services/agent_service.py`：更新 fast-launch model target gate 与 blocking reason。
  - `apps/console/src/lib/types.ts`：补充 model target base URL evidence 字段。
  - `docs/deployment/remote-agent-production.md`、`docs/deployment/remote-agent-acceptance-template.md`：部署和验收命令切到 DeepSeek，并移除 DeepSeek 路径下的 tool-loop 硬要求。
  - `apps/api/tests/test_agent_api.py`、`apps/console/src/routes/SettingsPage.test.tsx`、`apps/console/src/components/AppShell.test.tsx`：更新测试期望。
- TDD / verification 记录：
  - RED：focused deployment readiness tests 因实现仍期待 rawchat/GPT-5.5 Responses 而失败。
  - GREEN：`python -m pytest apps/api/tests/test_agent_api.py::test_deployment_fast_launch_readiness_requires_deepseek_chat_completions_and_remote_evidence apps/api/tests/test_agent_api.py::test_deployment_fast_launch_readiness_blocks_deepseek_without_direct_transport apps/api/tests/test_agent_api.py::test_deployment_fast_launch_readiness_accepts_privacy_safe_remote_acceptance_id -q --tb=short` -> `4 passed`。
- 本 checkpoint 没有远程 workflow run、没有 API restart、没有生产任务创建、没有明文密钥写入 git-tracked 文件。

### Checkpoint 10: Model-Free Workflow Confirmation And Browser Resume UX

- 按新的生产规划继续补齐 Agent 交互边界：让固定工作流确认卡在模型网关不可用时也能通过确定性规则生成，但仍不允许未授权创建任务。
- 生产边界：
  - `准备工作流确认 / workflow confirmation` 这类显式请求进入 fixed workflow confirmation lane；
  - `不要创建或启动任务` 不再把“准备确认卡”误判为纯只读回答；
  - 首次 Agent run 只创建 pending confirmation/thread，不创建 workflow task；
  - 只有用户点击批准后，后端 resume endpoint 通过 fingerprint/pending confirmation 才能创建 task；
  - 缺 Docker sudo/runtime credentials 时，真实 workflow task 可以失败在运行阶段，但这发生在审批后，属于执行环境边界而不是 Agent 绕过审批。
- 代码落点：
  - `apps/api/app/agent/intent.py`：新增显式确认准备短语和 rule intent evidence。
  - `apps/api/app/agent/graph.py`：新增 model-gateway-unconfigured 时的 deterministic fixed workflow planner fallback。
  - `apps/api/app/services/agent_service.py`：让 model-free fixed workflow confirmation request 绕过只读 fallback，进入 LangGraph confirmation path。
  - `apps/api/tests/test_agent_api.py`、`apps/api/tests/test_agent_graph.py`：补充 model-free confirmation 与中文稳定结果摘要断言。
  - `apps/console/scripts/browser_upload_agent_smoke.mjs`：新增 `--workflow-confirmation-resume`，真实浏览器上传、发送确认请求、点击批准并轮询 created task。
  - `apps/console/src/routes/AgentPage.tsx`：审批卡移入主聊天流，移除右侧 Evidence 面板的关键操作按钮，避免点击被布局遮挡。
- TDD / verification 记录：
  - RED：model-free 确认请求最初返回 `answered`，没有生成 confirmation。
  - GREEN：API regression 验证 `confirmation_required`、`image-agent-workflow-runner`、pending confirmation row、approval 前无 task。
  - RED：浏览器 smoke 首次发现 CLI workflow 模式仍发送默认“分析当前数据”消息。
  - GREEN：CLI parse test 锁定 workflow 模式默认使用 generated approval message。
  - RED：真实浏览器发现重复文本 locator 和右侧 approval button click interception。
  - GREEN：审批卡进入主聊天流后，真实浏览器完整通过 upload -> confirmation -> approve -> task created。
- Verification：
  - `python -m pytest apps/api/tests/test_agent_api.py::test_agent_run_prepares_workflow_confirmation_without_model_when_user_says_do_not_launch apps/api/tests/test_agent_api.py::test_agent_run_unconfigured_model_answers_inventory_without_confirmation apps/api/tests/test_agent_api.py::test_agent_run_falls_back_to_read_only_backend_answer_when_model_unconfigured apps/api/tests/test_agent_api.py::test_agent_resume_approved_confirmation_creates_real_task apps/api/tests/test_agent_graph.py -q --tb=short` -> `63 passed, 3 warnings`。
  - `node node_modules/vitest/vitest.mjs run src/routes/AgentPage.test.tsx --run` -> `12 passed`。
  - `node node_modules/vitest/vitest.mjs run scripts/browser_upload_agent_smoke.test.mjs --run` -> `4 passed`。
  - `node node_modules/typescript/bin/tsc -b` -> passed。
  - `node scripts/browser_upload_agent_smoke.mjs --root .tmp/browser-workflow-confirmation-resume-20260708e --api-port 8146 --console-port 5186 --workflow-confirmation-resume --output-json .tmp/browser-workflow-confirmation-resume-20260708e.json` -> passed。
  - `node scripts/browser_upload_agent_smoke.mjs --root .tmp/browser-upload-agent-smoke-regression-20260708 --api-port 8147 --console-port 5187 --output-json .tmp/browser-upload-agent-smoke-regression-20260708.json` -> passed。
- 本 checkpoint 没有远程部署配置变更、没有明文密钥写入 git-tracked 文件；真实浏览器 isolated smoke 在 approval 后创建 task，随后因缺 `IMAGE_AGENT_SUDO_PASSWORD` 按预期停在真实 Docker runtime credential boundary。
