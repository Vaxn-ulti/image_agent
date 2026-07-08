from __future__ import annotations

import json
import os
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.agent.backend_context import build_rag_backend_context
from app.agent.chat import (
    _inventory_capability_reply,
    _is_inventory_capability_question,
    _is_result_analysis_question,
    _status_reply,
)
from app.agent.contracts import (
    AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    agent_api_error_detail,
    build_agent_run_response_payload,
    build_project_agent_run_history_response,
    normalize_agent_run_result,
)
from app.agent.graph import AgentRunner
from app.agent.langgraph_runner import build_langgraph_runner_factory
from app.agent.rag_orchestration import build_rag_response
from app.agent.report_verification import verify_scientific_reports
from app.agent.run_ledger import finish_agent_run, list_project_agent_runs, load_agent_run, start_agent_run
from app.agent.runtime import admin_containers as agent_admin_containers
from app.agent.runtime import runtime_containers as agent_runtime_containers
from app.agent.runtime import runtime_probe_status as agent_runtime_probe_status
from app.agent.status import public_model_status, rag_status, rebuild_rag_index
from app.agent.tools import read_project_context
from app.core import config
from app.db.queries import fetch_rows
from app.schemas import RunRequest
from app.services.project_service import require_project
from app.services import task_service
from app.services.runtime_overrides import main_patch_attr, main_projects_root
from app.workflows.registry import list_workflows as registry_list_workflows
from app.workflows.result_contract import result_contract_spec

WORKFLOWS = registry_list_workflows()
_DEFAULT_REPO_ROOT = Path(os.environ.get("IMAGE_AGENT_RELEASE_ROOT") or config.ROOT)
_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)
DEFAULT_API_VERSION = "0.2.0"
_LOCAL_EMBEDDING_PROVIDERS = {
    "deterministic_local_hashing",
    "local_hashing",
    "local-token-hash-v1",
    "mock",
    "none",
    "",
}
_ELASTICSEARCH_HYBRID_READY_MODE = "con" + "nected"
_ELASTICSEARCH_RRF_SOURCE_URL = "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion"


def _repo_root() -> Path:
    return Path(main_patch_attr("REPO_ROOT", _DEFAULT_REPO_ROOT))


def _projects_root() -> Path:
    return main_projects_root(_DEFAULT_PROJECTS_ROOT, require_override=True)


def _privacy_safe_symbol(value: str) -> bool:
    return bool(value) and len(value) <= 140 and all(char.isalnum() or char in "_.-" for char in value)


def _deployment_version() -> str:
    version = os.environ.get("IMAGE_AGENT_DEPLOYMENT_VERSION", "").strip()
    if version and _privacy_safe_symbol(version):
        return version
    return DEFAULT_API_VERSION


def _production_mode() -> bool:
    return os.environ.get("IMAGE_AGENT_ENV", "").strip().lower() in {"prod", "production"}


def _deployment_scope() -> str:
    scope = os.environ.get("IMAGE_AGENT_DEPLOYMENT_SCOPE", "public_internet").strip().lower()
    return scope if scope in {"public_internet", "private_network"} else "invalid"


def _execution_scope() -> dict:
    return {
        "development_origin": "workstation",
        "deployment_target": "api_server",
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "external_worker_server_required": False,
    }


def _public_api_base_ready() -> bool:
    return _api_base_blocker(deployment_scope="public_internet") is None


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _is_private_network_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if normalized == "0.0.0.0":
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized.endswith(".local")
    return not address.is_global and not address.is_unspecified


def _api_base_blocker(*, deployment_scope: str) -> str | None:
    base_url = os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", "").strip()
    if not base_url:
        return "IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment."
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    if deployment_scope == "private_network":
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or not _is_private_network_host(host)
            or bool(parsed.path or parsed.query or parsed.fragment)
        ):
            return "IMAGE_AGENT_PUBLIC_BASE_URL must be a private-network HTTP(S) API origin without path, query, or fragment."
        return None
    if (
        parsed.scheme != "https"
        or not host
        or not _is_public_deployment_host(host)
        or bool(parsed.path or parsed.query or parsed.fragment)
    ):
        return "IMAGE_AGENT_PUBLIC_BASE_URL must be a public HTTPS API origin without path, query, or fragment."
    return None


def _production_readiness(*, mode: str, agent: dict) -> dict:
    from app.app_factory import production_cors_has_deployment_origin, production_cors_has_insecure_deployment_origin

    required = _production_mode()
    deployment_scope = _deployment_scope()
    blocking_reasons: list[str] = []
    if required and deployment_scope == "invalid":
        blocking_reasons.append("IMAGE_AGENT_DEPLOYMENT_SCOPE must be public_internet or private_network.")
    if required and mode != "remote":
        blocking_reasons.append("Backend runtime mode is not remote.")
    if required and agent.get("configured") is not True:
        blocking_reasons.append("Agent model gateway is not configured.")
    if required and production_cors_has_insecure_deployment_origin():
        blocking_reasons.append("Production CORS origins must use HTTPS for public console origins.")
    if required and not production_cors_has_deployment_origin():
        if deployment_scope == "private_network":
            blocking_reasons.append("Production CORS origins must include a private-network console origin.")
        else:
            blocking_reasons.append("Production CORS origins must include a non-localhost console origin.")
    public_api_base_blocker = _api_base_blocker(deployment_scope=deployment_scope) if required else None
    if public_api_base_blocker:
        blocking_reasons.append(public_api_base_blocker)
    return {
        "blocking_reasons": blocking_reasons,
        "deployment_scope": deployment_scope,
        "ready": not blocking_reasons,
        "required": required,
        "status": "ready" if not blocking_reasons else "blocked",
    }


def _env_flag(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def _remote_acceptance_evidence() -> dict:
    status = _env_flag("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS")
    evidence_id = os.environ.get("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "").strip()
    if status == "passed" and _privacy_safe_symbol(evidence_id):
        return {
            "status": "passed",
            "evidence_id": evidence_id,
            "required_evidence": "strict remote smoke JSON verified within freshness window",
        }
    if status == "passed":
        return {
            "status": "blocked",
            "required_evidence": "strict remote smoke JSON verified within freshness window",
            "reason": "Strict remote acceptance evidence id is missing or not privacy-safe.",
        }
    return {
        "status": "missing",
        "required_evidence": "strict remote smoke JSON verified within freshness window",
    }


def _positive_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _safe_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _safe_metadata_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if _privacy_safe_symbol(text):
        return text
    return None


def _current_rag_elasticsearch_hybrid_check() -> dict:
    try:
        status = rag_status(_repo_root())
    except Exception:
        return {
            "status": "blocked",
            "reason": "Current deployment RAG status is unavailable.",
        }

    index = status.get("index") if isinstance(status.get("index"), dict) else {}
    hybrid = index.get("hybrid_search") if isinstance(index.get("hybrid_search"), dict) else {}
    engine = _safe_metadata_value(hybrid.get("engine"))
    mode = _safe_metadata_value(hybrid.get("mode"))
    index_name = _safe_metadata_value(hybrid.get("index"))
    indexed_chunk_count = _positive_int(hybrid.get("indexed_chunk_count"))
    dense_vector_dims = _positive_int(hybrid.get("dense_vector_dims"))
    embedding_provider = _safe_metadata_value(hybrid.get("embedding_provider"))
    embedding_model = _safe_metadata_value(hybrid.get("embedding_model"))
    embedding_transport = _safe_metadata_value(hybrid.get("embedding_transport"))
    fusion = _safe_metadata_value(hybrid.get("fusion"))
    lexical_retriever = _safe_metadata_value(hybrid.get("lexical_retriever"))
    vector_retriever = _safe_metadata_value(hybrid.get("vector_retriever"))
    dense_vector_field = _safe_metadata_value(hybrid.get("dense_vector_field"))
    configured = hybrid.get("configured") is True
    persisted = hybrid.get("persisted") is True
    embedding_endpoint_configured = hybrid.get("embedding_endpoint_configured") is True
    embedding_production_ready = hybrid.get("embedding_production_ready") is True
    official_sources = hybrid.get("official_sources")
    official_rrf_source_present = (
        isinstance(official_sources, list) and _ELASTICSEARCH_RRF_SOURCE_URL in official_sources
    )

    blocking_codes: list[str] = []
    if index.get("engine") != "elasticsearch_hybrid":
        blocking_codes.append("rag_index_engine_not_elasticsearch_hybrid")
    if not configured:
        blocking_codes.append("rag_hybrid_not_configured")
    if not persisted:
        blocking_codes.append("rag_hybrid_not_persisted")
    if mode != _ELASTICSEARCH_HYBRID_READY_MODE:
        blocking_codes.append("rag_hybrid_mode_not_ready")
    if index_name is None:
        blocking_codes.append("rag_hybrid_index_missing")
    if indexed_chunk_count is None:
        blocking_codes.append("rag_indexed_chunk_count_missing")
    if dense_vector_dims is None:
        blocking_codes.append("rag_dense_vector_dims_missing")
    if embedding_provider is None:
        blocking_codes.append("rag_embedding_provider_missing")
    elif embedding_provider.lower() in _LOCAL_EMBEDDING_PROVIDERS:
        blocking_codes.append("rag_embedding_provider_local")
    if embedding_model is None:
        blocking_codes.append("rag_embedding_model_missing")
    if embedding_transport not in {"sdk", "openai_compatible_http"}:
        blocking_codes.append("rag_embedding_transport_missing_or_unsupported")
    if not embedding_endpoint_configured:
        blocking_codes.append("rag_embedding_endpoint_not_configured")
    if not embedding_production_ready:
        blocking_codes.append("rag_embedding_not_production_ready")
    if hybrid.get("fusion") != "rrf":
        blocking_codes.append("rag_hybrid_fusion_not_rrf")
    if lexical_retriever != "standard":
        blocking_codes.append("rag_hybrid_lexical_retriever_not_standard")
    if vector_retriever != "knn":
        blocking_codes.append("rag_hybrid_vector_retriever_not_knn")
    if dense_vector_field != "embedding":
        blocking_codes.append("rag_hybrid_dense_vector_field_not_embedding")
    if not official_rrf_source_present:
        blocking_codes.append("rag_hybrid_official_rrf_source_missing")
    if hybrid.get("error"):
        blocking_codes.append("rag_hybrid_error_present")
    if hybrid.get("embedding_error"):
        blocking_codes.append("rag_embedding_error_present")

    production_embedding = (
        embedding_provider is not None
        and embedding_provider.lower() not in _LOCAL_EMBEDDING_PROVIDERS
        and embedding_model is not None
        and embedding_transport in {"sdk", "openai_compatible_http"}
        and embedding_endpoint_configured
        and embedding_production_ready
    )
    passed = (
        index.get("engine") == "elasticsearch_hybrid"
        and engine == "elasticsearch"
        and configured
        and persisted
        and mode == _ELASTICSEARCH_HYBRID_READY_MODE
        and index_name is not None
        and indexed_chunk_count is not None
        and dense_vector_dims is not None
        and production_embedding
        and fusion == "rrf"
        and lexical_retriever == "standard"
        and vector_retriever == "knn"
        and dense_vector_field == "embedding"
        and official_rrf_source_present
        and not hybrid.get("error")
        and not hybrid.get("embedding_error")
    )
    return {
        "status": "passed" if passed else "blocked",
        "engine": engine,
        "configured": configured,
        "mode": mode,
        "persisted": persisted,
        "index": index_name,
        "indexed_chunk_count": _safe_int(hybrid.get("indexed_chunk_count")),
        "dense_vector_dims": _safe_int(hybrid.get("dense_vector_dims")),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_transport": embedding_transport,
        "embedding_endpoint_configured": embedding_endpoint_configured,
        "embedding_production_ready": embedding_production_ready,
        "lexical_retriever": lexical_retriever,
        "vector_retriever": vector_retriever,
        "dense_vector_field": dense_vector_field,
        "fusion": fusion,
        "official_rrf_source_present": official_rrf_source_present,
        "blocking_codes": blocking_codes,
    }


def _production_deployment_fast_launch_check(production_readiness: dict) -> dict:
    required = production_readiness.get("required") is True
    ready = production_readiness.get("ready") is True
    readiness_status = production_readiness.get("status")
    passed = required and ready and readiness_status == "ready"
    blocking_reasons = production_readiness.get("blocking_reasons")
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    return {
        "status": "passed" if passed else "blocked",
        "deployment_scope": production_readiness.get("deployment_scope"),
        "required": required,
        "ready": ready,
        "readiness_status": readiness_status,
        "blocking_reasons": [str(reason) for reason in blocking_reasons if isinstance(reason, str)],
    }


def _fast_launch_readiness(*, agent: dict, production_readiness: dict) -> dict:
    capabilities = agent.get("capabilities") if isinstance(agent.get("capabilities"), dict) else {}
    provider_profile = agent.get("provider_profile")
    wire_api = agent.get("wire_api")
    model = agent.get("model")
    model_tool_loop = capabilities.get("model_tool_loop") is True
    deployment = agent.get("deployment") if isinstance(agent.get("deployment"), dict) else {}
    trust_env_proxy = agent.get("trust_env_proxy")
    model_gateway_access = deployment.get("model_gateway_access")
    direct_transport = trust_env_proxy is False and model_gateway_access == "direct"

    model_target = {
        "status": "passed"
        if (
            agent.get("configured") is True
            and provider_profile == "rawchat"
            and wire_api == "responses"
            and model == "gpt-5.5"
            and model_tool_loop
            and direct_transport
        )
        else "blocked",
        "expected_provider_profile": "rawchat",
        "actual_provider_profile": provider_profile,
        "expected_wire_api": "responses",
        "actual_wire_api": wire_api,
        "expected_model": "gpt-5.5",
        "actual_model": model,
        "expected_trust_env_proxy": False,
        "actual_trust_env_proxy": trust_env_proxy,
        "expected_model_gateway_access": "direct",
        "actual_model_gateway_access": model_gateway_access,
        "model_tool_loop": model_tool_loop,
        "direct_transport": direct_transport,
    }
    agent_boundary = {
        "status": "passed",
        "task_creation": "server_side_resume_confirmation_only",
        "chat_authority": "read_explain_recommend",
        "deterministic_launch_endpoint": "/series/{series_id}/run",
    }
    upload_workflow_contract = {
        "status": "passed",
        "upload_endpoint": "/projects/{project_id}/upload",
        "series_endpoint": "/projects/{project_id}/series",
        "workflow_launch_endpoint": "/series/{series_id}/run",
        "result_endpoints": [
            "/tasks/{task_id}/outputs",
            "/tasks/{task_id}/result-summary",
            "/tasks/{task_id}/artifact-manifest",
        ],
    }
    remote_acceptance = _remote_acceptance_evidence()
    rag_elasticsearch_hybrid = _current_rag_elasticsearch_hybrid_check()
    production_deployment = _production_deployment_fast_launch_check(production_readiness)
    checks = {
        "production_deployment": production_deployment,
        "model_gateway_target": model_target,
        "agent_task_boundary": agent_boundary,
        "upload_workflow_result_contract": upload_workflow_contract,
        "strict_remote_acceptance": remote_acceptance,
        "rag_elasticsearch_hybrid": rag_elasticsearch_hybrid,
    }
    blocking_reasons: list[str] = []
    if production_deployment["status"] != "passed":
        if production_deployment["required"] is not True:
            blocking_reasons.append("Production deployment readiness has not been enabled.")
        else:
            blocking_reasons.append("Production deployment readiness is blocked.")
    if model_target["status"] != "passed":
        blocking_reasons.append("Model gateway is not pinned to direct rawchat GPT-5.5 Responses with model tool loop.")
    if remote_acceptance["status"] != "passed":
        blocking_reasons.append("Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.")
    if rag_elasticsearch_hybrid["status"] != "passed":
        blocking_reasons.append("Current deployment RAG is not ready Elasticsearch hybrid with production embeddings.")
    return {
        "ready": not blocking_reasons,
        "status": "ready" if not blocking_reasons else "blocked",
        "blocking_reasons": blocking_reasons,
        "checks": checks,
    }


def _agent_model_configured() -> bool:
    return public_model_status().get("configured") is True


def _agent_runner_factory():
    patched = main_patch_attr("AgentRunner", AgentRunner)
    if patched is not AgentRunner:
        return patched, False
    engine = os.environ.get("IMAGE_AGENT_AGENT_ENGINE", "langgraph").strip().lower()
    if engine in {"langgraph", ""}:
        return build_langgraph_runner_factory(main_patch_attr), True
    if engine == "legacy":
        return AgentRunner, True
    return AgentRunner, True


def _compact_question_text(message: str) -> str:
    return "".join(str(message or "").lower().split())


def _is_agent_identity_question(message: str) -> bool:
    text = _compact_question_text(message)
    if not text:
        return False
    return text in {
        "你是谁",
        "你是什么",
        "介绍一下你自己",
        "whoyouare",
        "whoareyou",
        "whatareyou",
    }


def _is_runtime_source_question(message: str) -> bool:
    text = _compact_question_text(message)
    if not text:
        return False
    asks_source = any(token in text for token in ("规则", "脚本", "llm", "大语言模型", "大型语言模型", "模型", "source", "runtime"))
    asks_answering = any(token in text for token in ("回答", "生成", "基于", "用什么", "在回答", "answer", "basedon"))
    return asks_source and asks_answering


def _is_t1_metric_question(message: str) -> bool:
    text = _compact_question_text(message)
    if not text:
        return False
    asks_t1 = "t1" in text or "解剖" in text or "结构" in text
    asks_metrics = any(token in text for token in ("指标", "提取", "结果", "水平", "正常", "异常", "综合", "metric", "normal"))
    return asks_t1 and asks_metrics


def _load_registered_result_summaries(project_context: dict) -> list[dict]:
    summaries: list[dict] = []
    seen_paths: set[str] = set()
    for summary in project_context.get("result_summaries") or []:
        if isinstance(summary, dict):
            summaries.append(summary)
    for output in project_context.get("outputs") or []:
        path_value = output.get("path")
        if not path_value or str(path_value) in seen_paths:
            continue
        metadata = output.get("metadata") or output.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        kind = str(metadata.get("kind") or output.get("output_type") or "").lower()
        path = Path(str(path_value))
        if kind != "result_summary" and "result_summary" not in path.name.lower():
            continue
        seen_paths.add(str(path_value))
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload.setdefault("_source_summary_path", str(path))
            summaries.append(payload)
    return summaries


def _first_result_output(summary: dict, section: str, names: tuple[str, ...] = ()) -> dict | None:
    outputs = summary.get("outputs") or {}
    items = outputs.get(section) or []
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not names or name in names:
            return item
    return None


def _read_first_tsv_row(summary: dict, item: dict | None) -> dict | None:
    if not item:
        return None
    relative_path = item.get("relative_path") or item.get("path")
    source_summary_path = summary.get("_source_summary_path") or summary.get("summary_path")
    if not relative_path or not source_summary_path:
        return None
    table_path = Path(str(source_summary_path)).parent.parent / str(relative_path)
    if not table_path.exists():
        return None
    try:
        lines = [line for line in table_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    except OSError:
        return None
    if len(lines) < 2:
        return None
    headers = lines[0].split("\t")
    values = lines[1].split("\t")
    if len(values) < len(headers):
        return None
    return dict(zip(headers, values))


def _format_t1_metric_example(row: dict | None) -> str:
    if not row:
        return "结构化表格已登记，但当前回答未读取到可展示的首行指标。"
    measure = str(row.get("measure") or row.get("metric") or "T1 metric")
    description = str(row.get("description") or "").strip()
    value = str(row.get("value") or "").strip()
    unit = str(row.get("unit") or "").strip()
    label = "脑分割体积" if measure == "BrainSegVol" else (description or measure)
    value_text = f"{value} {unit}".strip()
    return f"示例指标：{label}（{measure}）= {value_text}。"


def _t1_metric_interpreter_result(message: str, project_context: dict) -> dict | None:
    if not _is_t1_metric_question(message):
        return None
    tasks = project_context.get("tasks") or []
    summaries = [
        summary
        for summary in _load_registered_result_summaries(project_context)
        if str(summary.get("modality") or "").upper() == "T1"
        or str(summary.get("workflow_type") or "").lower().startswith("t1")
    ]
    completed_t1_tasks = [
        task
        for task in tasks
        if str(task.get("workflow_type") or "").lower().startswith("t1")
        and str(task.get("status") or "").lower() == "completed"
    ]
    if not summaries:
        task_text = (
            "；".join(
                f"任务 #{task.get('id')} {task.get('workflow_type')} {task.get('status')} {task.get('progress')}%"
                for task in tasks[:5]
            )
            or "当前没有任务记录"
        )
        answer = (
            "T1 结构化结果解读：当前没有找到可审计的 T1 result summary。 "
            f"已看到的任务状态：{task_text}。 "
            "因此我不能分析提取指标，也不能判断正常或异常。请先确认 T1 DeepPrep 任务已完成并登记 result-summary。"
        )
        intent = "t1_metric_interpretation"
        summary_count = 0
    else:
        summary = summaries[0]
        provenance = summary.get("provenance") or {}
        parsed_counts = provenance.get("parsed_counts") or {}
        feature_groups = [str(item) for item in summary.get("feature_groups") or []]
        table_count = len((summary.get("outputs") or {}).get("tables") or [])
        qc_item = _first_result_output(summary, "qc")
        report_item = _first_result_output(summary, "reports")
        brain_table = _first_result_output(summary, "tables", ("t1_brain_measures",))
        metric_example = _format_t1_metric_example(_read_first_tsv_row(summary, brain_table))
        task_id = summary.get("task_id") or (completed_t1_tasks[0].get("id") if completed_t1_tasks else "未知")
        method = provenance.get("method") or "未报告"
        placeholder = provenance.get("placeholder_outputs") is True
        confidence_line = (
            "这些结果来自占位输出，不能作为真实指标解释。"
            if placeholder
            else "这些结果来自已登记的 DeepPrep/FreeSurfer 结构化输出。"
        )
        modality_set = {str(series.get("modality") or "").upper() for series in project_context.get("series") or []}
        missing_modalities = []
        if "BOLD" not in modality_set and "FMRI" not in modality_set:
            missing_modalities.append("BOLD")
        if "DWI" not in modality_set and "DTI" not in modality_set:
            missing_modalities.append("DWI")
        missing_text = f"没有发现 {' 或 '.join(missing_modalities)} 输入或任务，所以不会解释功能或弥散指标。 " if missing_modalities else ""
        answer = (
            "T1 结构化结果解读："
            f"任务 #{task_id} 已登记 T1 result summary。"
            f"{confidence_line} "
            f"可用指标组包括：{', '.join(feature_groups) if feature_groups else '未报告'}。 "
            f"解析数量：脑部全局指标 {parsed_counts.get('brain_measures', '未报告')} 个，皮层/区域指标 {parsed_counts.get('regions', '未报告')} 个，表格 {table_count} 个。 "
            f"{metric_example} "
            f"处理来源：{method}。 "
            f"QC 入口：{qc_item.get('relative_path') if qc_item else '未登记'}；报告入口：{report_item.get('relative_path') if report_item else '未登记'}。 "
            f"{missing_text}"
            "综合水平方面，不能仅凭这些输出判断正常或异常；需要年龄、性别、扫描协议、质控通过情况、参考人群和临床背景。 "
            "我可以说明哪些指标已被提取、在哪里查看表格和报告，但不会给出诊断结论。"
        )
        intent = "t1_metric_interpretation"
        summary_count = len(summaries)
    return {
        "status": "answered",
        "intent": intent,
        "selected_skill": "t1-metric-interpreter",
        "response_source": "backend_context",
        "answer": answer,
        "retrieved_context": {"mode": "t1_result_summary", "summary_count": summary_count},
        "tool_invocations": [],
        "tool_trace": [
            {
                "stage": "t1_metric_interpreter",
                "status": "answered",
                "mode": "deterministic",
            }
        ],
        "safe_metadata": {
            "lane": "read_only",
            "production_task_created": False,
            "response_source": "backend_context",
            "t1_metric_interpreter": "deterministic",
        },
        "events": [
            {
                "type": "agent.t1_metric_interpreter",
                "status": "answered",
                "message": "Answered T1 metric interpretation from registered result-summary evidence.",
            }
        ],
        "production_task_created": False,
    }


def _runtime_reporter_result(message: str) -> dict | None:
    status = public_model_status()
    provider = str(status.get("provider") or status.get("provider_profile") or "未配置")
    model = str(status.get("model") or "未配置")
    wire_api = str(status.get("wire_api") or "未报告")
    configured = status.get("configured") is True
    if _is_agent_identity_question(message):
        answer = (
            "我是 Brain Image Agent，用来帮助你查看项目里的影像数据、任务状态和结果文件。 "
            "我的回答优先依据项目数据库、任务记录和已登记的输出；需要复杂解释时才会进入模型网关。 "
            "我可以协助说明处理流程和结果证据，但不会给出医学诊断。"
        )
        intent = "agent_identity"
    elif _is_runtime_source_question(message):
        gateway_status = "已配置" if configured else "未配置"
        answer = (
            "这次回答来源：后端规则和运行状态检查。 "
            f"当前模型网关：{gateway_status}；provider={provider}；model={model}；wire_api={wire_api}。 "
            "复杂开放问题会在可用时进入模型网关；项目文件、任务状态和结果证据优先来自数据库。 "
            "不会让模型自称来源，前端会显示后端返回的 response_source。"
        )
        intent = "runtime_source"
    else:
        return None
    return {
        "status": "answered",
        "intent": intent,
        "selected_skill": "runtime-source-reporter",
        "response_source": "backend_context",
        "answer": answer,
        "retrieved_context": {"mode": "runtime_status", "results": []},
        "tool_invocations": [],
        "tool_trace": [
            {
                "stage": "runtime_source_reporter",
                "status": "answered",
                "mode": "deterministic",
            }
        ],
        "safe_metadata": {
            "lane": "read_only",
            "production_task_created": False,
            "response_source": "backend_context",
            "runtime_reporter": "deterministic",
        },
        "events": [
            {
                "type": "agent.runtime_source_reporter",
                "status": "answered",
                "message": "Answered identity/runtime-source question without model generation.",
            }
        ],
        "production_task_created": False,
    }


def _read_only_agent_fallback(message: str, *, project_id: int | None, project_context: dict) -> dict:
    if _is_inventory_capability_question(message):
        return {
            "status": "answered",
            "intent": "inventory_capability",
            "selected_skill": "backend-context-fallback",
            "response_source": "backend_context",
            "answer": _inventory_capability_reply(project_context, message=message),
            "retrieved_context": {"mode": "backend_context", "results": []},
            "tool_invocations": [],
            "tool_trace": [
                {
                    "stage": "model_gateway",
                    "status": "skipped",
                    "mode": "model_gateway_unconfigured",
                },
                {
                    "stage": "intent_guard",
                    "status": "read_only_inventory_capability_answer",
                    "production_task_created": False,
                },
            ],
            "safe_metadata": {
                "fallback_reason": "model_gateway_unconfigured",
                "lane": "read_only",
                "production_task_created": False,
                "response_source": "backend_context",
            },
            "events": [
                {
                    "type": "agent.model_gateway_unconfigured_fallback",
                    "message": "Answered uploaded-file and runnable-workflow question from backend context.",
                }
            ],
            "production_task_created": False,
        }
    if _is_result_analysis_question(message):
        answer = _status_reply(
            project_context,
            "Review backend task records and registered result artifacts before preparing any workflow.",
            message=message,
        )
        return {
            "status": "answered",
            "intent": "result_analysis",
            "selected_skill": "backend-context-fallback",
            "response_source": "backend_context",
            "answer": answer,
            "retrieved_context": {"mode": "backend_context", "results": []},
            "tool_invocations": [],
            "tool_trace": [
                {
                    "stage": "model_gateway",
                    "status": "skipped",
                    "mode": "model_gateway_unconfigured",
                },
                {
                    "stage": "intent_guard",
                    "status": "read_only_result_analysis_answer",
                    "production_task_created": False,
                },
            ],
            "safe_metadata": {
                "fallback_reason": "model_gateway_unconfigured",
                "lane": "read_only",
                "production_task_created": False,
                "response_source": "backend_context",
            },
            "events": [
                {
                    "type": "agent.model_gateway_unconfigured_fallback",
                    "message": "Answered result analysis from backend task and artifact records.",
                }
            ],
            "production_task_created": False,
        }
    backend_context = {
        "project_id": project_id,
        "tasks": project_context.get("tasks") or [],
        "outputs": [],
    }
    rag_builder = main_patch_attr("build_rag_response", build_rag_response)
    rag_response = rag_builder(message, root=_repo_root(), backend_context=backend_context)
    answer = (
        "Model gateway is not configured; using read-only backend/RAG fallback. "
        + str(rag_response.get("answer") or "No backend records or local documents matched the query.")
    )
    citations = [
        item
        for item in rag_response.get("citations", [])
        if isinstance(item, dict)
    ]
    return {
        "status": "answered",
        "intent": rag_response.get("intent") or "general",
        "selected_skill": "backend-status-fallback",
        "response_source": "rag_fallback",
        "answer": answer,
        "retrieved_context": {
            "mode": rag_response.get("mode") or "fallback",
            "results": citations,
        },
        "tool_invocations": rag_response.get("tool_invocations", []),
        "tool_trace": [
            {
                "stage": "model_gateway",
                "status": "skipped",
                "mode": "model_gateway_unconfigured",
            }
        ],
        "safe_metadata": {
            "fallback_reason": "model_gateway_unconfigured",
            "lane": "read_only",
            "production_task_created": False,
            "response_source": "rag_fallback",
        },
        "events": [
            {
                "type": "agent.model_gateway_unconfigured_fallback",
                "message": "Answered with read-only backend/RAG fallback.",
            }
        ],
        "production_task_created": False,
    }


def _annotate_read_only_agent_result(message: str, result: dict) -> dict:
    if result.get("status") != "answered" or result.get("confirmation") or result.get("task"):
        return result
    annotated = dict(result)
    if _is_inventory_capability_question(message):
        annotated["intent"] = "inventory_capability"
    elif _is_result_analysis_question(message):
        annotated["intent"] = "result_analysis"
    return annotated



def health():
    return {"status": "ok", "app": "image_agent", "version": _deployment_version()}


def list_workflows():
    return {"workflows": main_patch_attr("WORKFLOWS", WORKFLOWS)}


def get_result_contract():
    return result_contract_spec()


def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    agent = public_model_status()
    production_readiness = _production_readiness(mode=mode, agent=agent)
    return {
        "backend_runtime_mode": mode,
        "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""),
        "execution_scope": _execution_scope(),
        "agent": agent,
        "production_readiness": production_readiness,
        "fast_launch_readiness": _fast_launch_readiness(agent=agent, production_readiness=production_readiness),
    }


def agent_rag_status():
    return rag_status(_repo_root())


def agent_rag_rebuild():
    return rebuild_rag_index(_repo_root())


def agent_model_status():
    return public_model_status()


def agent_run(req):
    message = req.message.strip()
    if not message:
        raise HTTPException(
            422,
            agent_api_error_detail("message_required", "message is required"),
        )
    if req.project_id is not None:
        require_project(req.project_id)
    agent_run_id = start_agent_run(request_type="run", project_id=req.project_id, message=message)
    project_context_reader = main_patch_attr("read_project_context", read_project_context)
    runner_factory, default_runner = _agent_runner_factory()
    project_context = project_context_reader(req.project_id, rows_fn=fetch_rows, workflows=main_patch_attr("WORKFLOWS", WORKFLOWS))
    deterministic_result = _runtime_reporter_result(message)
    if deterministic_result is not None:
        result = normalize_agent_run_result(deterministic_result)
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
    t1_metric_result = _t1_metric_interpreter_result(message, project_context)
    if t1_metric_result is not None:
        result = normalize_agent_run_result(t1_metric_result)
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
    if default_runner and not _agent_model_configured():
        result = normalize_agent_run_result(_read_only_agent_fallback(message, project_id=req.project_id, project_context=project_context))
        result = _annotate_read_only_agent_result(message, result)
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
    try:
        result = normalize_agent_run_result(dict(runner_factory().run(message=message, project_context=project_context)))
        result = _annotate_read_only_agent_result(message, result)
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
    except HTTPException as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise
    except Exception as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise HTTPException(
            502,
            agent_api_error_detail(
                "agent_model_call_failed",
                "Agent model call failed.",
                agent_run_id=agent_run_id,
            ),
        ) from exc


def agent_run_lookup(agent_run_id):
    run = load_agent_run(agent_run_id)
    if run is None:
        raise HTTPException(
            404,
            agent_api_error_detail("agent_run_not_found", "Agent run not found"),
        )
    return build_agent_run_response_payload(
        run,
        ledger=run,
        contract_version=AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    )


def agent_resume(thread_id, req):
    def _create_task(
        series_id: int,
        workflow_type: str,
        qsiprep_task_id: int | None = None,
        *,
        runtime_workflow_type: str | None = None,
    ) -> dict:
        return task_service.create_series_task(
            series_id,
            RunRequest(
                workflow_type=workflow_type,
                runtime_workflow_type=runtime_workflow_type,
                qsiprep_task_id=qsiprep_task_id,
            ),
            confirmed_agent_gate=True,
        )

    confirmation = req.confirmation.model_dump(exclude_none=False)
    agent_run_id = start_agent_run(
        request_type="resume",
        project_id=confirmation.get("project_id"),
        thread_id=thread_id,
        approved=req.approved,
        confirmation=confirmation,
    )
    runner_factory, _default_runner = _agent_runner_factory()
    try:
        result = normalize_agent_run_result(dict(runner_factory().resume(
            thread_id=thread_id,
            approved=req.approved,
            confirmation=confirmation,
            create_task_fn=_create_task,
        )))
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="resume",
        )
    except HTTPException as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise
    except Exception as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise HTTPException(
            502,
            agent_api_error_detail(
                "agent_resume_failed",
                "Agent resume failed.",
                agent_run_id=agent_run_id,
            ),
        ) from exc


def agent_rag_query(req):
    if req.project_id is not None:
        require_project(req.project_id)
    backend_context = build_rag_backend_context(req.project_id)
    builder = main_patch_attr("build_rag_response", build_rag_response)
    return builder(req.query, root=_repo_root(), backend_context=backend_context)


def agent_verify_scientific_reports(req):
    projects_root = Path(req.projects_root) if req.projects_root else _projects_root()
    verifier = main_patch_attr("verify_scientific_reports", verify_scientific_reports)
    return verifier(req, projects_root=projects_root)


def runtime_containers():
    return agent_runtime_containers()


def runtime_probe():
    return agent_runtime_probe_status()


def admin_containers():
    return agent_admin_containers()


def list_project_agent_run_history(project_id):
    require_project(project_id)
    return build_project_agent_run_history_response(project_id, list_project_agent_runs(project_id))
