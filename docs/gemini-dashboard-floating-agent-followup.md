# Gemini Follow-up: Align Dashboard With Reference Image and Backend Contracts

Continue from the current worktree. Do not restart the design from scratch. Do not ask for plan confirmation. Read the reference image and backend interface files below first, then implement only the frontend fixes needed for the dashboard. After editing, update tests and run the requested checks.

## Visual Reference

Use this original screenshot as the visual target:

`C:\Users\A\AppData\Local\Temp\codex-clipboard-5883c73b-e630-4fba-9894-c9ba37afd07e.png`

If your CLI can read images, inspect it directly. If image reading is unavailable, follow this description:

- Light product dashboard with a fixed left sidebar, top-right settings/profile controls, and a main page title: Brain Imaging Processing Agent.
- Main content is a clean, dense dashboard grid:
  - Upload Data panel at upper left.
  - Workflow Status panel at upper right.
  - Pipeline Parameters panel below upload.
  - Recent Runs panel beside parameters.
  - Results Preview panel spanning the lower area.
- Panels should feel like task surfaces, not marketing cards. Keep spacing tight, typography restrained, and controls familiar.
- The Agent chat must not occupy the main dashboard grid. It should be a floating right-side drawer that can expand and collapse.

## Backend References To Study Before Editing

Read these files before making changes:

- `GEMINI_FRONTEND_LOG.md`: explains the existing frontend state and which generated prototype paths should not become production targets.
- `docs/product-readiness.md`: especially Fast Launch Main Flow Goal and Productization Gates. Preserve the upload -> series -> workflow -> task -> result -> agent boundary.
- `docs/api.md`: read upload, series/workflow, task/result, `/agent/runs`, `/agent/runs/{thread_id}/resume`, and `/chat` compatibility sections.
- `apps/console/src/lib/api.ts`: use existing frontend API helpers. Do not invent endpoints.
- `apps/console/src/lib/types.ts`: preserve typed backend contracts.
- `apps/console/src/lib/workflows.ts`: preserve workflow eligibility and recommendation logic.
- `apps/console/src/routes/DashboardPage.tsx`: implement the UI fix here.
- `apps/console/src/routes/DashboardPage.test.tsx`: update or add tests here.

## Backend Contract Boundaries

Preserve these rules exactly:

- Upload must keep using the existing upload API helpers and current project/series cache flow.
- Workflow launch must keep using deterministic backend validation through `api.runSeries(...)`, which maps to `/series/{series_id}/run`.
- Do not let the Agent directly start long-running medical imaging work from frontend-only logic.
- Dashboard chat should call `api.runAgent(projectId, message)` first. It may fall back to `api.chat(projectId, message)` only through the existing compatibility behavior.
- If an Agent response reports `task_created`, keep task cache invalidation behavior.
- Result preview must continue to use `result-summary` and `artifact-manifest` behavior through existing helpers.
- Do not point production dashboard code at the `/gemini` prototype route.
- Do not add local fake MRI processing, fake Docker execution, or local visualization logic. Workflow result images depend on backend/container-provided QC artifacts and manifests.

## Required UI Fix

Convert or verify the dashboard Agent Copilot UI as a fixed/floating right-side drawer:

- Remove Agent Copilot from the main dashboard grid columns.
- Keep the main dashboard grid focused on upload, workflow status, pipeline parameters, recent runs, and results preview, visually aligned with the screenshot.
- Expanded drawer:
  - fixed to the right side of the viewport.
  - visible above content with a high but reasonable z-index.
  - contains the existing Agent Copilot header, messages, quick actions, Start recommended pipeline button, input form, and no-diagnosis boundary.
  - has a collapse button with accessible label `Collapse Agent Copilot`.
- Collapsed drawer:
  - compact fixed right-side launcher or rail.
  - accessible label `Open Agent Copilot`.
  - clicking it expands the drawer.
- On wide screens, add right padding to the dashboard root while drawer is open so important controls are not permanently covered.
- On small screens, drawer can overlay content but must have a visible collapse control and must not make the page unusable.

## Tests

Update `apps/console/src/routes/DashboardPage.test.tsx` to verify:

- The Agent Copilot is rendered as a floating drawer or floating launcher, not as an inline grid sidebar.
- The drawer can collapse and expand using `Collapse Agent Copilot` and `Open Agent Copilot`.
- `Explain this step` still calls `api.runAgent(13, "Explain this step")`.
- Typed chat still works.
- Workflow launch still calls `api.runSeries(...)` with the backend recommended workflow when available.

## Checks To Run

Run:

```powershell
cd apps/console
npm.cmd test -- DashboardPage.test.tsx
npm.cmd run lint
```

Stop after implementation and tests. Summarize files changed and test results.
