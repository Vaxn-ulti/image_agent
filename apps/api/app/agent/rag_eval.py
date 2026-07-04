from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.rag_orchestration import build_rag_response


RAGAnswerFn = Callable[[str, Path], dict[str, Any]]


DEFAULT_RAG_EVAL_THRESHOLDS: dict[str, dict[str, float]] = {
    "recall_at_5": {"min": 0.90},
    "mrr_at_10": {"min": 0.75},
    "context_precision": {"min": 0.70},
    "answer_correctness": {"min": 0.85},
    "faithfulness": {"min": 0.85},
    "citation_accuracy": {"min": 0.90},
    "refusal_accuracy": {"min": 0.90},
    "p95_retrieval_latency_ms": {"max": 800.0},
    "p95_end_to_end_latency_ms": {"max": 6000.0},
}


@dataclass(frozen=True)
class RAGEvalCase:
    id: str
    query: str
    relevant_sources: tuple[str, ...]
    required_answer_terms: tuple[str, ...] = ()
    forbidden_answer_terms: tuple[str, ...] = ()
    expected_citations: tuple[str, ...] = ()
    should_refuse: bool = False
    expected_refusal_terms: tuple[str, ...] = ()
    cost_usd: float | None = None
    satisfaction: float | None = None


def load_eval_cases(path: Path | str) -> list[RAGEvalCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError("RAG eval file must contain a cases list")
    cases = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("Each RAG eval case must be an object")
        cases.append(
            RAGEvalCase(
                id=_required_text(raw, "id"),
                query=_required_text(raw, "query"),
                relevant_sources=tuple(_text_list(raw.get("relevant_sources"))),
                required_answer_terms=tuple(_text_list(raw.get("required_answer_terms"))),
                forbidden_answer_terms=tuple(_text_list(raw.get("forbidden_answer_terms"))),
                expected_citations=tuple(_text_list(raw.get("expected_citations"))),
                should_refuse=bool(raw.get("should_refuse")),
                expected_refusal_terms=tuple(_text_list(raw.get("expected_refusal_terms"))),
                cost_usd=_optional_float(raw.get("cost_usd")),
                satisfaction=_optional_float(raw.get("satisfaction")),
            )
        )
    return cases


def evaluate_rag(
    *,
    root: Path | str,
    cases: Sequence[RAGEvalCase],
    answer_fn: RAGAnswerFn | None = None,
    thresholds: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    runner = answer_fn or _default_answer_fn
    case_reports = []
    end_to_end_latencies_ms = []
    retrieval_latencies_ms = []
    costs = []
    satisfaction_scores = []
    for case in cases:
        started = time.perf_counter()
        response = runner(case.query, root_path)
        latency_ms = (time.perf_counter() - started) * 1000.0
        end_to_end_latencies_ms.append(latency_ms)
        retrieval_latency_ms = _optional_float(response.get("retrieval_latency_ms"))
        if retrieval_latency_ms is not None:
            retrieval_latencies_ms.append(retrieval_latency_ms)
        if case.cost_usd is not None:
            costs.append(case.cost_usd)
        elif _optional_float(response.get("cost_usd")) is not None:
            costs.append(float(response["cost_usd"]))
        if case.satisfaction is not None:
            satisfaction_scores.append(case.satisfaction)
        case_reports.append(
            _score_case(
                case,
                response,
                end_to_end_latency_ms=latency_ms,
                retrieval_latency_ms=retrieval_latency_ms,
            )
        )
    thresholds = thresholds or DEFAULT_RAG_EVAL_THRESHOLDS
    aggregate = _aggregate(
        case_reports,
        end_to_end_latencies_ms=end_to_end_latencies_ms,
        retrieval_latencies_ms=retrieval_latencies_ms,
        costs=costs,
        satisfaction_scores=satisfaction_scores,
    )
    gate = evaluate_thresholds(aggregate, thresholds)
    aggregate["threshold_passed"] = gate["passed"]
    return {
        "schema_version": 1,
        "case_count": len(case_reports),
        "aggregate": aggregate,
        "cases": case_reports,
        "thresholds": thresholds,
        "threshold_gate": gate,
        "metric_definitions": metric_definitions(),
    }


def metric_definitions() -> dict[str, str]:
    return {
        "recall_at_5": "Fraction of cases where at least one expected relevant source appears in the top 5 retrieved citations.",
        "mrr_at_10": "Mean reciprocal rank of the first expected relevant source in the top 10 retrieved citations.",
        "context_precision": "Mean fraction of retrieved citations that are expected relevant sources.",
        "answer_correctness": "Mean rule score for required answer terms present and forbidden terms absent.",
        "faithfulness": "Mean fraction of answer-required terms supported by retrieved context snippets.",
        "citation_accuracy": "Mean fraction of expected citation sources present in returned citations.",
        "refusal_accuracy": "Mean correctness for cases marked should_refuse; non-refusal cases count as correct when the answer does not refuse.",
        "p95_retrieval_latency_ms": "95th percentile reported retrieval latency for eval queries.",
        "p95_end_to_end_latency_ms": "95th percentile measured wall-clock latency for full eval queries, including generation.",
        "p95_latency_ms": "Backward-compatible alias for p95_end_to_end_latency_ms.",
        "average_cost_per_query_usd": "Mean cost_usd supplied by responses or eval cases; zero when no model cost is reported.",
        "user_satisfaction": "Mean optional satisfaction score supplied in eval cases.",
    }


def _default_answer_fn(query: str, root: Path) -> dict[str, Any]:
    return build_rag_response(query, root=root, backend_context={"tasks": []})


def evaluate_thresholds(
    aggregate: dict[str, Any],
    thresholds: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    threshold_map = thresholds or DEFAULT_RAG_EVAL_THRESHOLDS
    checks = []
    for metric, rule in threshold_map.items():
        value = _optional_float(aggregate.get(metric))
        if value is None:
            checks.append({"metric": metric, "passed": False, "reason": "missing_metric", **rule})
            continue
        passed = True
        if "min" in rule and value < float(rule["min"]):
            passed = False
        if "max" in rule and value > float(rule["max"]):
            passed = False
        checks.append({"metric": metric, "value": value, "passed": passed, **rule})
    return {
        "passed": all(check["passed"] for check in checks),
        "failed_metrics": [check["metric"] for check in checks if not check["passed"]],
        "checks": checks,
    }


def _score_case(
    case: RAGEvalCase,
    response: dict[str, Any],
    *,
    end_to_end_latency_ms: float,
    retrieval_latency_ms: float | None,
) -> dict[str, Any]:
    citations = _citation_sources(response)
    answer = str(response.get("answer") or "")
    snippets = " ".join(str(item.get("snippet") or item.get("excerpt") or "") for item in response.get("citations") or [])
    relevant = set(_normalize_source(source) for source in case.relevant_sources)
    expected_citations = set(_normalize_source(source) for source in case.expected_citations or case.relevant_sources)
    top5 = citations[:5]
    top10 = citations[:10]
    first_rank = _first_relevant_rank(top10, relevant)
    answer_correctness = _answer_correctness(answer, case)
    faithfulness = _faithfulness(answer, snippets, case)
    citation_accuracy = _citation_accuracy(citations, expected_citations)
    refusal_accuracy = _refusal_accuracy(answer, case)
    return {
        "id": case.id,
        "query": case.query,
        "retrieved_sources": citations,
        "expected_relevant_sources": sorted(relevant),
        "recall_at_5": 1.0 if relevant and any(source in relevant for source in top5) else 0.0,
        "mrr_at_10": 0.0 if first_rank is None else 1.0 / first_rank,
        "context_precision": _context_precision(citations, relevant),
        "answer_correctness": answer_correctness,
        "faithfulness": faithfulness,
        "citation_accuracy": citation_accuracy,
        "refusal_accuracy": refusal_accuracy,
        "retrieval_latency_ms": None if retrieval_latency_ms is None else round(retrieval_latency_ms, 3),
        "end_to_end_latency_ms": round(end_to_end_latency_ms, 3),
        "latency_ms": round(end_to_end_latency_ms, 3),
        "answer_preview": answer[:240],
        "passed": min(answer_correctness, faithfulness, citation_accuracy, refusal_accuracy) >= 0.8,
    }


def _aggregate(
    reports: Sequence[dict[str, Any]],
    *,
    end_to_end_latencies_ms: Sequence[float],
    retrieval_latencies_ms: Sequence[float],
    costs: Sequence[float],
    satisfaction_scores: Sequence[float],
) -> dict[str, Any]:
    metric_names = [
        "recall_at_5",
        "mrr_at_10",
        "context_precision",
        "answer_correctness",
        "faithfulness",
        "citation_accuracy",
        "refusal_accuracy",
    ]
    aggregate = {name: _mean(float(report[name]) for report in reports) for name in metric_names}
    aggregate["p95_retrieval_latency_ms"] = _rounded_percentile_or_none(retrieval_latencies_ms, 95)
    aggregate["p95_end_to_end_latency_ms"] = round(_percentile(end_to_end_latencies_ms, 95), 3)
    aggregate["p95_latency_ms"] = aggregate["p95_end_to_end_latency_ms"]
    aggregate["average_cost_per_query_usd"] = round(_mean(costs), 8)
    aggregate["user_satisfaction"] = None if not satisfaction_scores else round(_mean(satisfaction_scores), 3)
    aggregate["passed_case_count"] = sum(1 for report in reports if report.get("passed") is True)
    aggregate["failed_case_count"] = sum(1 for report in reports if report.get("passed") is not True)
    return aggregate


def _citation_sources(response: dict[str, Any]) -> list[str]:
    sources = []
    for citation in response.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        source = _normalize_source(str(citation.get("source") or citation.get("path") or ""))
        if source:
            sources.append(source)
    return sources


def _first_relevant_rank(sources: Sequence[str], relevant: set[str]) -> int | None:
    for index, source in enumerate(sources, start=1):
        if source in relevant:
            return index
    return None


def _context_precision(sources: Sequence[str], relevant: set[str]) -> float:
    if not sources:
        return 0.0
    return sum(1 for source in sources if source in relevant) / len(sources)


def _answer_correctness(answer: str, case: RAGEvalCase) -> float:
    required = [term for term in case.required_answer_terms]
    forbidden = [term for term in case.forbidden_answer_terms]
    required_score = 1.0 if not required else sum(1 for term in required if _contains_term(answer, term)) / len(required)
    forbidden_score = 1.0 if not forbidden else sum(1 for term in forbidden if not _contains_term(answer, term)) / len(forbidden)
    return (required_score + forbidden_score) / 2.0


def _faithfulness(answer: str, snippets: str, case: RAGEvalCase) -> float:
    terms = [term for term in case.required_answer_terms]
    if not terms:
        return 1.0
    supported = 0
    for term in terms:
        if _contains_term(snippets, term) or (case.should_refuse and _contains_term(f"{answer} {snippets}", term)):
            supported += 1
    return supported / len(terms)


def _citation_accuracy(citations: Sequence[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    cited = set(citations)
    return sum(1 for source in expected if source in cited) / len(expected)


def _refusal_accuracy(answer: str, case: RAGEvalCase) -> float:
    refusal_terms = [term for term in case.expected_refusal_terms] or [
        "do not create production tasks",
        "unknown workflow",
        "unsupported",
        "proposal",
        "incubation",
        "cannot",
    ]
    refused = any(_contains_term(answer, term) for term in refusal_terms)
    return 1.0 if refused == case.should_refuse else 0.0


def _contains_term(text: str, term: str) -> bool:
    return _normalize_term(term) in _normalize_term(text)


def _normalize_term(text: str) -> str:
    return re.sub(r"[\s_\\-]+", " ", str(text).lower()).strip()


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"RAG eval case missing required text field: {key}")
    return value.strip()


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("RAG eval list fields must be lists")
    return [str(item).replace("\\", "/").strip() for item in value if str(item).strip()]


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _normalize_source(source: str) -> str:
    return source.replace("\\", "/").strip()


def _mean(values: Sequence[float] | Any) -> float:
    numbers = list(values)
    return 0.0 if not numbers else float(sum(numbers) / len(numbers))


def _percentile(values: Sequence[float], percentile: int) -> float:
    numbers = sorted(float(value) for value in values)
    if not numbers:
        return 0.0
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return numbers[int(position)]
    weight = position - lower
    return numbers[lower] * (1 - weight) + numbers[upper] * weight


def _rounded_percentile_or_none(values: Sequence[float], percentile: int) -> float | None:
    if not values:
        return None
    return round(_percentile(values, percentile), 3)
