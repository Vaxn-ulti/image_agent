import assert from "node:assert/strict";
import test from "node:test";

import { resultSummaryTitle, workflowMachineLabel } from "./resultSummary.mjs";

test("result summary title prefers registry display metadata from summary", () => {
  const summary = {
    modality: "DWI",
    workflow_metadata: { display_name: "DWI fast GPU DTI" },
    workflow_type: "dwi_fast_gpu_dti",
  };

  assert.equal(resultSummaryTitle(summary, null), "DWI fast GPU DTI result summary");
});

test("result summary title falls back to artifact manifest display metadata", () => {
  const summary = {
    modality: "DWI",
    workflow_type: "dwi_fast_gpu_dti",
  };
  const manifest = {
    workflow_metadata: { display_name: "DWI fast GPU DTI" },
    workflow_type: "dwi_fast_gpu_dti",
  };

  assert.equal(resultSummaryTitle(summary, manifest), "DWI fast GPU DTI result summary");
});

test("workflow machine label keeps stable workflow ids for contract display", () => {
  const summary = {
    contract_version: "result_summary.v1",
    runtime_workflow_type: "dwi_fast_gpu_dti",
    workflow_type: "dwi_fast_gpu_dti",
  };

  assert.equal(workflowMachineLabel(summary, null), "dwi_fast_gpu_dti / contract result_summary.v1");
});
