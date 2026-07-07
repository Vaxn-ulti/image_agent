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
  workflow_metadata?: WorkflowCatalogItem | null;
  status: TaskStatus;
  progress: number;
  error_message?: string | null;
  qsiprep_task_id?: number | null;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type ObserveRepairResponse = {
  status: 'ok' | 'not_found' | string;
  policy: 'read_only_observe_repair' | string;
  task_id: number;
  task?: Task | null;
  events?: Array<Record<string, unknown>>;
  remote_logs?: Array<{ name?: string; source_stage?: string; size_bytes?: number; tail?: string }>;
  main_log?: { tail?: string };
  result_summary_status?: string;
  repair_suggestions?: Array<{ kind?: string; message?: string }>;
  auto_rerun_allowed?: boolean;
  production_task_created?: boolean;
  requires_preflight_before_retry?: boolean;
  requires_human_confirmation_before_retry?: boolean;
};

export type TaskEventsResponse = {
  status: 'ok' | string;
  task?: Task | null;
  task_id?: number;
  events?: Array<{
    name?: string;
    progress?: number;
    source_stage?: string;
    status?: string;
    type?: string;
    [key: string]: unknown;
  }>;
  remote_logs?: Array<{ name?: string; source_stage?: string; size_bytes?: number; tail?: string }>;
  main_log?: { tail?: string };
};

export type WorkflowCatalogItem = {
  type?: string;
  workflow_type?: string;
  lane?: string;
  requires_confirmation?: boolean;
  runtime_workflow_type?: string | null;
  api_runnable?: boolean;
  agent_selectable?: boolean;
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
  workflow_metadata?: WorkflowCatalogItem | null;
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
      actual_model_gateway_access?: string;
      actual_provider_profile?: string;
      actual_trust_env_proxy?: boolean;
      actual_wire_api?: string;
      expected_model?: string;
      expected_model_gateway_access?: string;
      expected_provider_profile?: string;
      expected_trust_env_proxy?: boolean;
      expected_wire_api?: string;
      direct_transport?: boolean;
      model_tool_loop?: boolean;
      status?: 'passed' | 'blocked' | 'missing' | string;
    };
    production_deployment?: {
      blocking_reasons?: string[];
      readiness_status?: 'ready' | 'blocked' | string;
      ready?: boolean;
      required?: boolean;
      status?: 'passed' | 'blocked' | 'missing' | string;
    };
    strict_remote_acceptance?: {
      evidence_id?: string;
      reason?: string;
      required_evidence?: string;
      status?: 'passed' | 'blocked' | 'missing' | string;
    };
    rag_elasticsearch_hybrid?: {
      blocking_codes?: string[];
      configured?: boolean;
      dense_vector_dims?: number | null;
      dense_vector_field?: string | null;
      embedding_endpoint_configured?: boolean;
      embedding_model?: string | null;
      embedding_production_ready?: boolean;
      embedding_provider?: string | null;
      embedding_transport?: string | null;
      engine?: string | null;
      fusion?: string | null;
      index?: string | null;
      indexed_chunk_count?: number | null;
      lexical_retriever?: string | null;
      mode?: string | null;
      official_rrf_source_present?: boolean;
      persisted?: boolean;
      status?: 'passed' | 'blocked' | 'missing' | string;
      vector_retriever?: string | null;
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
    deployment_scope?: 'public_internet' | 'private_network' | string;
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
  attachments?: Array<{
    file_id?: number;
    original_name?: string;
    file_type?: string;
    size?: number;
    sha256?: string;
  }>;
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

export type ProjectFile = {
  id: number;
  project_id?: number;
  original_name: string;
  file_type?: string;
  size?: number;
  sha256?: string;
  created_at?: string;
  json_summary?: Record<string, unknown>;
  linked_series?: Array<{
    id: number;
    modality?: string;
    sequence_label?: string;
    format?: string;
    confidence?: number;
    status?: string;
  }>;
};

export type DeleteProjectFileResponse = {
  deleted_file?: {
    id?: number;
    original_name?: string;
    file_type?: string;
  };
  deleted_series_ids?: number[];
  updated_series_ids?: number[];
  status: 'deleted' | string;
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
  workflow_type?: string;
  runtime_workflow_type?: string | null;
  workflow_metadata?: WorkflowCatalogItem | null;
  artifacts: OutputItem[];
  omitted_artifacts?: Array<Record<string, unknown>>;
};

export type ResultSummary = {
  contract_version: string;
  project_id: number;
  task_id: number;
  workflow_type: string;
  workflow_metadata?: WorkflowCatalogItem | null;
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
  action_lane?: string | null;
  backend_tool?: string | null;
  confirmation?: AgentConfirmation;
  contract_version?: 'agent_run.v1' | string;
  events?: Array<{
    event_type?: string;
    type?: string;
    status?: string;
    message?: string;
    task_id?: number;
    workflow_type?: string;
    runtime_workflow_type?: string;
    metadata?: Record<string, unknown>;
    created_at?: string;
  }>;
  message?: string;
  model_gateway_access?: string | null;
  production_task_created?: boolean | null;
  project_id?: number | null;
  request_type?: string | null;
  response_source?: string | null;
  retrieved_sources?: Array<Record<string, unknown>>;
  runtime_workflow_type?: string | null;
  safe_metadata?: Record<string, unknown>;
  selected_skill?: string;
  series_id?: number | null;
  status?: string;
  task?: Task;
  task_id?: number | null;
  thread_id?: string;
  tool_input?: Record<string, unknown> | null;
  workflow_type?: string | null;
};

export type AgentRunHistoryItem = {
  agent_run_id: string;
  created_at?: string;
  event_count?: number;
  finished_at?: string | null;
  model_gateway_access?: string;
  project_id?: number;
  request_type?: 'run' | 'resume' | string;
  safe_metadata?: Record<string, unknown>;
  selected_skill?: string | null;
  status?: string;
  thread_id?: string | null;
  updated_at?: string;
};

export type ProjectAgentRunHistoryResponse = {
  agent_runs: AgentRunHistoryItem[];
  contract_version: 'project_agent_run_history.v1' | string;
  project_id: number;
};

export type AgentRunLookupResponse = AgentRunResponse & {
  contract_version?: 'agent_run_lookup.v1' | string;
  created_at?: string;
  error_message?: string | null;
  finished_at?: string | null;
  message_sha256?: string;
  request_type?: string;
  updated_at?: string;
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
