export const FALLBACK_WORKFLOWS = {
  T1: ["t1_deepprep_anat_report"],
  BOLD: ["bold_fmriprep_xcpd_report"],
  DWI: ["dwi_fast_gpu_dti"],
  DICOM: [],
};

export function workflowOptionsForSeries(series, workflows) {
  const registryOptions = (workflows || []).filter((workflow) => {
    if (!workflow?.type || workflow.type === "toolchain_proposal") return false;
    if (workflow.modality !== series.modality) return false;
    if (workflow.lane === "fixed_workflow" && workflow.agent_selectable === false && !workflow.api_runnable) return false;
    return workflow.lane === "fixed_workflow" || workflow.api_runnable;
  });
  const options = registryOptions.length > 0
    ? registryOptions
    : (FALLBACK_WORKFLOWS[series.modality] || []).map((type) => ({ type }));
  return options.filter((workflow, index, list) => list.findIndex((item) => item.type === workflow.type) === index);
}
