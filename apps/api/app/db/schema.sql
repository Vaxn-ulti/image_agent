CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  original_name TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  file_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS imaging_series (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  file_id INTEGER NOT NULL,
  upload_session_id INTEGER,
  bids_path TEXT,
  sequence_label TEXT,
  supported_for_processing INTEGER NOT NULL DEFAULT 1,
  unsupported_reason TEXT,
  modality TEXT NOT NULL,
  format TEXT NOT NULL,
  confidence REAL NOT NULL,
  metadata_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(file_id) REFERENCES files(id)
);
CREATE TABLE IF NOT EXISTS upload_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  label TEXT NOT NULL,
  source_type TEXT NOT NULL,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  inventory_json TEXT NOT NULL DEFAULT '{}',
  error_message TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS sequence_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  upload_session_id INTEGER NOT NULL,
  project_id INTEGER NOT NULL,
  sequence_label TEXT NOT NULL,
  modality TEXT NOT NULL,
  count INTEGER NOT NULL,
  supported_for_processing INTEGER NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(upload_session_id) REFERENCES upload_sessions(id),
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  series_id INTEGER NOT NULL,
  workflow_type TEXT NOT NULL,
  runtime_workflow_type TEXT,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  log_path TEXT NOT NULL,
  error_message TEXT,
  qsiprep_task_id INTEGER,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(series_id) REFERENCES imaging_series(id)
);
CREATE TABLE IF NOT EXISTS execution_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL UNIQUE,
  project_id INTEGER NOT NULL,
  series_id INTEGER NOT NULL,
  workflow_type TEXT NOT NULL,
  runtime_workflow_type TEXT NOT NULL,
  status TEXT NOT NULL,
  queue TEXT,
  celery_task_id TEXT,
  approved_plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(series_id) REFERENCES imaging_series(id)
);
CREATE TABLE IF NOT EXISTS execution_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  task_id INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL,
  status TEXT NOT NULL,
  queue TEXT,
  celery_task_id TEXT,
  worker_id TEXT,
  lease_expires_at TEXT,
  heartbeat_at TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(run_id) REFERENCES execution_runs(id),
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS execution_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  task_id INTEGER NOT NULL,
  attempt_id INTEGER,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES execution_runs(id),
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(attempt_id) REFERENCES execution_attempts(id)
);
CREATE TABLE IF NOT EXISTS outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  output_type TEXT NOT NULL,
  path TEXT NOT NULL,
  preview_path TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
  agent_run_id TEXT PRIMARY KEY,
  request_type TEXT NOT NULL,
  thread_id TEXT,
  project_id INTEGER,
  series_id INTEGER,
  task_id INTEGER,
  workflow_type TEXT,
  status TEXT NOT NULL,
  intent TEXT,
  action_lane TEXT,
  selected_skill TEXT,
  approved INTEGER,
  message_sha256 TEXT,
  model_gateway_access TEXT NOT NULL,
  retrieved_sources_json TEXT NOT NULL DEFAULT '[]',
  tool_invocations_json TEXT NOT NULL DEFAULT '[]',
  safe_metadata_json TEXT NOT NULL DEFAULT '{}',
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(series_id) REFERENCES imaging_series(id),
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS agent_run_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_run_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(agent_run_id) REFERENCES agent_runs(agent_run_id)
);
CREATE TABLE IF NOT EXISTS agent_confirmations (
  thread_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  project_id INTEGER,
  series_id INTEGER,
  workflow_type TEXT,
  qsiprep_task_id INTEGER,
  action_lane TEXT,
  confirmation_fingerprint TEXT NOT NULL,
  confirmation_json TEXT NOT NULL,
  decision_json TEXT NOT NULL DEFAULT '{}',
  selected_skill TEXT,
  retrieved_context_json TEXT NOT NULL DEFAULT '{}',
  extra_json TEXT NOT NULL DEFAULT '{}',
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  consumed_at TEXT,
  terminal_agent_run_id TEXT,
  safe_metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS agent_confirmation_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  agent_run_id TEXT,
  event_type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(thread_id) REFERENCES agent_confirmations(thread_id),
  FOREIGN KEY(agent_run_id) REFERENCES agent_runs(agent_run_id)
);
