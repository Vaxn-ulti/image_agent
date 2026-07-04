import assert from "node:assert/strict";
import test from "node:test";

import { workflowOptionsForSeries } from "./workflows.mjs";

test("workflowOptionsForSeries excludes non-agent-selectable fixed workflows", () => {
  const options = workflowOptionsForSeries(
    { id: 11, modality: "T1" },
    [
      {
        agent_selectable: true,
        lane: "fixed_workflow",
        modality: "T1",
        runtime_workflow_type: "t1_deepprep",
        type: "t1_deepprep_anat_report",
      },
      {
        agent_selectable: false,
        lane: "fixed_workflow",
        modality: "T1",
        runtime_workflow_type: "t1_deepprep_validate",
        type: "t1_deepprep_validate",
      },
    ],
  );

  assert.deepEqual(
    options.map((workflow) => workflow.type),
    ["t1_deepprep_anat_report"],
  );
});
