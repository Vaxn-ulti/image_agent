# Gemini Task: Dashboard Floating Agent Drawer

You are Gemini working inside the repository `C:\Users\A\Documents\New project 2`.

## User Request

The current frontend drifted away from the reference image. Update the real console frontend using the provided reference layout. Agent chat must become a floating right-side chat panel that can expand and collapse. Codex will review and verify your changes after you finish.

Reference image path:

`C:\Users\A\AppData\Local\Temp\codex-clipboard-5883c73b-e630-4fba-9894-c9ba37afd07e.png`

## Scope

- Modify the real production console under `apps/console`, especially `apps/console/src/routes/DashboardPage.tsx` and tests as needed.
- Do not only update `apps/console/src/routes/GeminiStandaloneApp.tsx`. That route is a prototype. The real target is `/projects/:projectId/dashboard`.
- Do not modify backend code.
- Do not modify `.env` or commit any secrets.
- Avoid changing `apps/console/src/lib/api.ts` unless a type-only adjustment is truly necessary. Do not invent new API endpoints.

## Backend/API Boundaries

- Upload must keep using existing API methods:
  - `api.uploadNifti` for NIfTI.
  - `api.uploadDwi` for complete DWI sidecar set.
  - `api.createUploadSession` + `api.ingestDataset` + `api.getInventory` for zip ingest.
- Workflow launch must keep using deterministic `api.runSeries(seriesId, workflowType, qsiprepTaskId?)` only. Do not let chat directly bypass this path.
- Dashboard chat must keep existing behavior: try `api.runAgent(projectId, message)`, then fallback to `api.chat(projectId, message)` if the Agent run fails.
- Keep cache invalidation behavior for `task_created` Agent responses.
- Keep result-summary/artifact-manifest usage. Do not add frontend-only fake result images as production evidence.
- Keep the warning/boundary copy that this is not medical diagnosis.

## Design Direction

- Use the reference image as the main spatial/layout guide: left navigation, clean light workspace, large `Brain Imaging Processing Agent` header, upload/status/parameters/recent-runs/results-preview panels in a calm clinical workbench layout.
- This is product UI, not a marketing page. Keep it dense, predictable, task-focused, with restrained green accent and neutral surfaces.
- Move the current inline Agent Copilot sidebar out of the grid and make it a fixed/floating right-side drawer.
- The drawer must support expanded and collapsed states:
  - Collapsed state: compact fixed button or rail on the right side, visible above content, with accessible `aria-label`.
  - Expanded state: fixed right panel with Agent Copilot header, message history, quick actions, input form, and a collapse button.
  - Default should be expanded on desktop if there is enough width, collapsed or compact on small screens.
  - The drawer must not permanently hide critical dashboard controls. On wide screens, add reasonable right padding or max-width behavior so the panel does not cover important content; on smaller screens, it may overlay as a drawer with a clear close/collapse control.
- Keep the dashboard grid closer to the image: upload and workflow status in the top row; pipeline parameters and recent runs below; results preview spanning wide below. Agent chat floats outside this grid.
- Do not nest cards inside cards. Use cards only for the main panels or repeated items. Keep border radii around 8px or existing system style.
- Use `lucide-react` icons already available. Prefer icon buttons for collapse/expand/send where appropriate.
- Keep text fitting inside buttons/panels. No decorative gradient orbs, no glassmorphism.

## Testing Requirements

- Update `DashboardPage` tests to assert the floating Agent drawer behavior:
  - Agent Copilot is available as a floating right-side chat/drawer.
  - It can collapse and expand.
  - Quick action still calls `api.runAgent(projectId, "Explain this step")`.
  - Text entry still sends to `api.runAgent` and fallback `api.chat` remains covered by existing tests.
- Preserve existing tests for upload, workflow selection, run, results preview, and task cache invalidation.
- Run at least:

```powershell
cd apps/console
npm.cmd test -- DashboardPage.test.tsx
npm.cmd run lint
```

If feasible, also run:

```powershell
npm.cmd run build
```

## Completion Summary

After editing, summarize:

- Files changed.
- How the drawer works.
- Which tests/commands passed or failed.

Important: Keep implementation focused. Do not redesign unrelated pages. Do not create new backend contracts. Do not touch secrets.
