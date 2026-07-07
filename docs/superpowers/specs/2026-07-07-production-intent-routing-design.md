# Production Intent Routing Design

## Purpose

Upgrade Image Agent intent routing from a first-slice normalizer into a production-grade layered classifier. The router must combine deterministic rules, structured LLM classification, and a final fusion gate before any confirmation, incubation proposal, or read-only answer is selected.

This design implements the user's requirement that all work target real production behavior, not demo-level heuristics.

## Current Gap

The current implementation has a useful `IntentDecision` model and normalizer, but it is not production-grade because:

- The model planner schema does not require confidence or classification evidence.
- The rule layer runs after the LLM planner decision instead of producing its own first-class signal.
- The final decision does not preserve both rule and LLM evidence for audit.
- Rule/LLM conflicts are not represented as a formal gate outcome.
- Low confidence defaults can silently pass through because missing confidence becomes `0.75`.

## Production Architecture

Intent routing has three explicit layers:

1. Rule classifier
   - Runs before final routing and produces `RuleIntentSignal`.
   - Uses deterministic text and context rules for high-safety decisions.
   - Detects read-only requests, negated launch requests, explicit launch requests, status/result questions, unknown workflow wording, and incubation-like requests.
   - Can be authoritative for safety/read-only gates.

2. LLM structured classifier
   - Uses the existing planner call path, but the schema must require production intent fields.
   - Produces an LLM signal with category, subcategory, confidence, evidence spans, risk level, confirmation requirement, and ambiguity list.
   - Missing confidence is invalid and must be downgraded by the fusion layer, not silently defaulted to a passing value.

3. Fusion decision
   - Combines rule and LLM signals into the final public `decision`.
   - Produces a durable `intent_decision` audit block containing:
     - `contract_version`
     - `final_intent`
     - `final_category`
     - `final_gate`
     - `confidence`
     - `rule_signal`
     - `llm_signal`
     - `conflict`
     - `policy`
     - `reasons`
   - Emits `tool_trace` rows under `stage="intent_rule_classifier"` and `stage="intent_fusion_gate"`.

## Decision Policy

The final fusion policy is intentionally conservative:

- Read-only, negated launch, and safety rules override LLM launch requests.
- Unknown or non-production workflow requests route to `toolchain_incubation`.
- Explicit launch may proceed to fixed-workflow confirmation only when:
  - the rule layer sees launch evidence or no read-only/negation evidence;
  - the LLM category is compatible with `run_workflow`;
  - the lane is fixed workflow;
  - registry/preflight gates later pass.
- Ambiguous or low-confidence launch requests become read-only clarification.
- Missing LLM confidence is treated as incomplete model evidence.
- The fusion gate must never create production tasks directly; it only selects the next graph lane.

## Required Categories

The production categories are:

- `inventory_capability`
- `status_question`
- `result_analysis`
- `read_only_answer`
- `fixed_workflow_launch`
- `toolchain_incubation`
- `unknown_workflow`
- `needs_clarification`
- `safety_blocked`

## API And Graph Behavior

`AgentRunner._plan()` keeps the existing model gateway call, but its output is passed to the production fusion function. The returned decision must preserve existing fields used downstream:

- `intent`
- `action_lane`
- `lane`
- `workflow_type`
- `series_id`
- `requires_confirmation`
- `recommended_next_step`

The returned decision also adds the audit block `intent_decision`.

Downstream behavior remains unchanged:

- `answer_question` goes to read-only answer generation.
- `run_workflow + fixed_workflow` goes to confirmation preparation.
- `run_workflow + toolchain_incubation` goes to proposal creation.

## Testing Requirements

The implementation must add focused tests for:

- Rule-only read-only classification.
- Explicit launch classification.
- Negated launch overriding LLM run requests.
- Missing LLM confidence causing clarification for launch-like requests.
- Rule/LLM conflict audit metadata.
- Unknown workflow or non-production language routing to incubation.
- Planner schema requiring production fields.
- Graph trace including rule and fusion stages.
- API regressions for inventory answer and unknown-workflow incubation.

## Out Of Scope

This slice does not implement:

- New remote workflow runs.
- Remote smoke acceptance.
- New production task execution behavior.
- Frontend visual design.
- Full ContextGrounder or loop-budget state machine.

Those belong to later BMAD checkpoints after this routing contract is stable.

## Acceptance Criteria

- Production intent schema and fusion policy are implemented in `apps/api/app/agent/intent.py`.
- `AGENT_PLANNER_DECISION_SCHEMA` requires production intent fields.
- Existing graph routing continues to pass focused regressions.
- Tests prove conservative handling of rule/LLM conflicts.
- BMAD log records the work and checkpoint commits.
- Working tree is clean after final verification.
