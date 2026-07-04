export function workflowMetadata(summary, artifactManifest) {
  return summary?.workflow_metadata || artifactManifest?.workflow_metadata || null;
}

export function resultSummaryTitle(summary, artifactManifest) {
  const metadata = workflowMetadata(summary, artifactManifest);
  const workflowName = metadata?.display_name || summary?.modality || summary?.workflow_type || artifactManifest?.workflow_type || 'Workflow';
  return `${workflowName} result summary`;
}

export function workflowMachineLabel(summary, artifactManifest) {
  const workflowType = summary?.workflow_type || artifactManifest?.workflow_type || 'unknown_workflow';
  const runtimeWorkflowType = summary?.runtime_workflow_type || artifactManifest?.runtime_workflow_type;
  const runtimeSuffix = runtimeWorkflowType && runtimeWorkflowType !== workflowType ? ` / runtime ${runtimeWorkflowType}` : '';
  const contractSuffix = summary?.contract_version ? ` / contract ${summary.contract_version}` : '';
  return `${workflowType}${runtimeSuffix}${contractSuffix}`;
}
