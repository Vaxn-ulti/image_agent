export type TaskStatus = 'queued' | 'running' | 'completed' | 'completed_with_partial_failures' | 'failed' | 'cancelled';

export type Project = {
  id: number;
  name: string;
  description?: string;
  created_at?: string;
};

export type User = {
  id: number;
  username: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type Series = {
  id: number;
  project_id: number;
  modality: 'T1' | 'BOLD' | 'DWI' | 'DICOM' | string;
  format: string;
  confidence: number;
  sequence_label?: string;
  supported_for_processing?: boolean | number;
  unsupported_reason?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  workflow_eligibility?: WorkflowEligibilityContract | null;
};

export type Task = {
  id: number;
  project_id: number;
  series_id?: number | null;
  workflow_type: string;
  status: TaskStatus;
  progress: number;
  error_message?: string | null;
  qsiprep_task_id?: number | null;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type WorkflowCatalogItem = {
  type?: string;
  workflow_type?: string;
  lane?: string;
  requires_confirmation?: boolean;
  runtime_workflow_type?: string | null;
  api_runnable?: boolean;
  agent_selection_aliases?: string[];
  capability_summary?: string;
  display_name?: string;
  is_report_only?: boolean;
  limitations?: string[];
  pipeline_stages?: Array<{ name?: string; purpose?: string }>;
  primary_outputs?: string[];
  qc_outputs?: string[];
  report_outputs?: string[];
  workflow_family?: string;
  workflow_role?: string;
};

export type WorkflowCatalogResponse = {
  workflows: Array<string | WorkflowCatalogItem>;
};

export type WorkflowEligibilityItem = {
  workflow_type: string;
  blocking_reasons?: string[];
  reason?: string;
};

export type WorkflowEligibilityContract = {
  policy_version?: string;
  primary_recommendation?: WorkflowEligibilityItem | null;
  production_task_created?: boolean;
  runnable_workflows?: WorkflowEligibilityItem[];
  blocked_workflows?: WorkflowEligibilityItem[];
};

export type RuntimeResponse = {
  fs_license_exists?: boolean;
  workflows?: Record<string, { available: boolean; image?: string }>;
};

export type FastLaunchReadiness = {
  blocking_reasons?: string[];
  checks?: {
    agent_task_boundary?: {
      chat_authority?: string;
      deterministic_launch_endpoint?: string;
      status?: 'passed' | 'blocked' | 'missing' | string;
      task_creation?: string;
    };
    model_gateway_target?: {
      actual_model?: string;
      actual_provider_profile?: string;
      actual_wire_api?: string;
      expected_model?: string;
      expected_provider_profile?: string;
      expected_wire_api?: string;
      model_tool_loop?: boolean;
      status?: 'passed' | 'blocked' | 'missing' | string;
    };
    strict_remote_acceptance?: {
      evidence_id?: string;
      reason?: string;
      required_evidence?: string;
      status?: 'passed' | 'blocked' | 'missing' | string;
    };
    upload_workflow_result_contract?: {
      result_endpoints?: string[];
      series_endpoint?: string;
      status?: 'passed' | 'blocked' | 'missing' | string;
      upload_endpoint?: string;
      workflow_launch_endpoint?: string;
    };
  };
  ready?: boolean;
  status?: 'ready' | 'blocked' | string;
};

export type DeploymentResponse = {
  backend_runtime_mode?: 'local' | 'remote' | string;
  api_base_hint?: string;
  agent?: {
    provider?: string;
    model?: string;
    configured?: boolean;
    gateway_diagnostics?: {
      model_tool_loop?: string;
      request_shape?: string;
      sdk_method?: string;
      structured_output?: string;
      workflow_task_creation?: string;
    };
  };
  production_readiness?: {
    blocking_reasons?: string[];
    ready?: boolean;
    required?: boolean;
    status?: 'ready' | 'blocked' | string;
  };
  fast_launch_readiness?: FastLaunchReadiness;
};

export type Inventory = {
  total_files?: number;
  bids_dataset_root?: string;
  inventory_status?: TaskStatus;
  error_message?: string;
  dicom?: {
    failures?: Array<Record<string, unknown>>;
    found_files?: number;
    conversion_status?: string;
  };
  post_conversion_counts?: {
    by_modality?: Record<string, number>;
    by_sequence?: Record<string, number>;
  };
  recognized_unsupported_sequences?: Array<{ sequence: string; count: number; message: string }>;
  series?: Array<Record<string, unknown>>;
};

export type OutputItem = {
  id?: number;
  output_type?: string;
  path?: string;
  relative_path?: string;
  download_url?: string;
  content_type?: string;
  size_bytes?: number;
  preview_kind?: 'html' | 'image' | 'table' | 'json' | 'download' | string;
  metadata?: Record<string, unknown>;
  feature_group?: string;
  space?: string;
  source_stage?: string;
  artifact_category?: string;
  artifact_role?: string;
  artifact_origin?: string;
  native_artifact?: boolean;
  container_native_qc?: boolean;
  derived_scientific_report?: boolean;
  frontend_preview_asset?: boolean;
  provenance?: Record<string, unknown>;
};

export type ArtifactManifest = {
  contract_version: 'artifact_manifest_v1' | string;
  task_id: number;
  artifacts: OutputItem[];
  omitted_artifacts?: Array<Record<string, unknown>>;
};

export type ResultSummary = {
  contract_version: string;
  project_id: number;
  task_id: number;
  workflow_type: string;
  modality: 'T1' | 'BOLD' | 'DWI' | string;
  spaces: string[];
  feature_groups: string[];
  outputs: Record<string, OutputItem[] | Record<string, OutputItem[]>>;
  provenance: Record<string, unknown>;
  summary_path?: string;
  legacy_summary?: unknown;
};

export type RagResponse = {
  answer: string;
  citations?: Array<{ path?: string; title?: string; snippet?: string }>;
  backend_context?: Record<string, unknown>;
  dependency_status?: Record<string, unknown>;
  grounding_policy?: Record<string, unknown>;
  intent?: string;
  recommended_next_step?: string;
  tool_chain_hint?: string;
  tool_invocations?: Array<{ tool?: string; status?: string; result?: Record<string, unknown> }>;
  rag_mode?: 'langgraph' | 'fallback' | string;
};

export type AgentConfirmation = {
  action_lane?: string;
  project_id?: number;
  series_id?: number;
  summary?: string;
  title?: string;
  type?: string;
  workflow_type?: string;
  [key: string]: unknown;
};

export type AgentRunResponse = RagResponse & {
  agent_run_id?: string;
  confirmation?: AgentConfirmation;
  message?: string;
  selected_skill?: string;
  status?: string;
  task?: Task;
  thread_id?: string;
};

export type RagStatus = {
  dependencies?: Record<string, boolean | { available?: boolean; [key: string]: unknown }>;
  grounding_policy?: Record<string, unknown>;
  index?: {
    chunk_count?: number;
    document_count?: number;
    engine?: string | null;
    semantic_index?: boolean;
  };
};

export type DwiUploadFiles = {
  nifti: File;
  bval: File;
  bvec: File;
  jsonSidecar: File;
};
