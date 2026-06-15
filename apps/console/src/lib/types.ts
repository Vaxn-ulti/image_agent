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
  log_path?: string;
  qsiprep_task_id?: number | null;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type WorkflowCatalogItem = {
  type?: string;
  workflow_type?: string;
  requires_confirmation?: boolean;
  runtime_workflow_type?: string | null;
  api_runnable?: boolean;
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

export type DeploymentResponse = {
  backend_runtime_mode?: 'local' | 'remote' | string;
  api_base_hint?: string;
  agent?: {
    provider?: string;
    model?: string;
    configured?: boolean;
  };
};

export type Inventory = {
  total_files?: number;
  bids_dataset_root?: string;
  inventory_status?: TaskStatus;
  error_message?: string;
  dicom?: {
    found_files?: number;
    conversion_status?: string;
  };
  post_conversion_counts?: {
    by_modality?: Record<string, number>;
    by_sequence?: Record<string, number>;
  };
  recognized_unsupported_sequences?: Array<{ sequence: string; count: number; message: string }>;
};

export type OutputItem = {
  id?: number;
  output_type?: string;
  path?: string;
  relative_path?: string;
  download_url?: string;
  content_type?: string;
  size_bytes?: number;
  metadata?: Record<string, unknown>;
  feature_group?: string;
  space?: string;
  source_stage?: string;
  artifact_role?: string;
  artifact_origin?: string;
  native_artifact?: boolean;
  provenance?: Record<string, unknown>;
};

export type ResultSummary = {
  contract_version: string;
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
