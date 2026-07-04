import json
from pathlib import Path

from app.agent.rag_eval import DEFAULT_RAG_EVAL_THRESHOLDS, RAGEvalCase, evaluate_rag, evaluate_thresholds, load_eval_cases, metric_definitions


def test_rag_eval_scores_retrieval_generation_and_system_metrics(tmp_path):
    cases = [
        RAGEvalCase(
            id="hybrid",
            query="How does hybrid search work?",
            relevant_sources=(
                "docs/rag/contracts/elasticsearch-hybrid-search.md",
                "docs/rag/vendor/elastic_official_hybrid_search.md",
            ),
            expected_citations=("docs/rag/contracts/elasticsearch-hybrid-search.md",),
            required_answer_terms=("BM25", "dense vector", "RRF"),
            forbidden_answer_terms=("Qdrant",),
            cost_usd=0.012,
            satisfaction=4.5,
        )
    ]

    def fake_answer(query, root):
        return {
            "answer": "Elasticsearch hybrid search combines BM25, dense vector kNN, and RRF.",
            "retrieval_latency_ms": 12.0,
            "citations": [
                {
                    "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                    "snippet": "BM25 dense vector kNN and RRF are used for hybrid retrieval.",
                },
                {
                    "source": "docs/rag/vendor/elastic_official_hybrid_search.md",
                    "snippet": "Elastic official docs describe RRF and kNN retrieval.",
                },
            ],
        }

    report = evaluate_rag(root=tmp_path, cases=cases, answer_fn=fake_answer)

    aggregate = report["aggregate"]
    assert aggregate["recall_at_5"] == 1.0
    assert aggregate["mrr_at_10"] == 1.0
    assert aggregate["context_precision"] == 1.0
    assert aggregate["answer_correctness"] == 1.0
    assert aggregate["faithfulness"] == 1.0
    assert aggregate["citation_accuracy"] == 1.0
    assert aggregate["refusal_accuracy"] == 1.0
    assert aggregate["p95_retrieval_latency_ms"] == 12.0
    assert aggregate["p95_latency_ms"] == aggregate["p95_end_to_end_latency_ms"]
    assert aggregate["average_cost_per_query_usd"] == 0.012
    assert aggregate["user_satisfaction"] == 4.5
    assert aggregate["failed_case_count"] == 0
    assert report["thresholds"] == DEFAULT_RAG_EVAL_THRESHOLDS
    assert report["threshold_gate"]["passed"] is True


def test_rag_eval_scores_refusal_accuracy_for_unknown_workflows(tmp_path):
    case = RAGEvalCase(
        id="unknown-workflow",
        query="Run an unknown external workflow",
        relevant_sources=("docs/rag/workflows/workflow_launchability_matrix.md",),
        expected_citations=("docs/rag/workflows/workflow_launchability_matrix.md",),
        required_answer_terms=("Do not create production tasks", "incubation"),
        should_refuse=True,
        expected_refusal_terms=("Do not create production tasks", "incubation"),
    )

    def fake_answer(query, root):
        return {
            "answer": "Do not create production tasks for this unknown workflow; keep it in incubation.",
            "citations": [
                {
                    "path": "docs/rag/workflows/workflow_launchability_matrix.md",
                    "excerpt": "Do not create production tasks. Unknown workflows go to incubation.",
                }
            ],
        }

    report = evaluate_rag(root=tmp_path, cases=[case], answer_fn=fake_answer)

    assert report["cases"][0]["refusal_accuracy"] == 1.0
    assert report["aggregate"]["failed_case_count"] == 0


def test_load_eval_cases_accepts_git_managed_json(tmp_path):
    eval_set = tmp_path / "eval.json"
    eval_set.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case-1",
                        "query": "What is cited?",
                        "relevant_sources": ["docs/rag/contracts/rag-evaluation.md"],
                        "required_answer_terms": ["Recall@5"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_eval_cases(eval_set)

    assert cases[0].id == "case-1"
    assert cases[0].relevant_sources == ("docs/rag/contracts/rag-evaluation.md",)
    assert "recall_at_5" in metric_definitions()


def test_rag_eval_threshold_gate_reports_failed_metrics():
    gate = evaluate_thresholds(
        {
            "recall_at_5": 0.89,
            "mrr_at_10": 0.75,
            "context_precision": 0.70,
            "answer_correctness": 0.85,
            "faithfulness": 0.85,
            "citation_accuracy": 0.90,
            "refusal_accuracy": 0.90,
            "p95_retrieval_latency_ms": 801.0,
            "p95_end_to_end_latency_ms": 6000.0,
        }
    )

    assert gate["passed"] is False
    assert gate["failed_metrics"] == ["recall_at_5", "p95_retrieval_latency_ms"]


def test_rag_eval_threshold_gate_fails_when_required_retrieval_latency_is_missing(tmp_path):
    case = RAGEvalCase(
        id="missing-retrieval-latency",
        query="Explain the fixed workflow launch contract",
        relevant_sources=("docs/rag/contracts/rag-evaluation.md",),
        expected_citations=("docs/rag/contracts/rag-evaluation.md",),
        required_answer_terms=("registry", "preflight", "fingerprint"),
    )

    def fake_answer(query, root):
        return {
            "answer": "Fixed workflows must pass registry, preflight, human confirmation, and fingerprint checks.",
            "citations": [
                {
                    "source": "docs/rag/contracts/rag-evaluation.md",
                    "snippet": "registry preflight human confirmation fingerprint",
                }
            ],
        }

    report = evaluate_rag(root=tmp_path, cases=[case], answer_fn=fake_answer)

    assert report["aggregate"]["p95_retrieval_latency_ms"] is None
    assert report["threshold_gate"]["passed"] is False
    failed = {
        check["metric"]: check
        for check in report["threshold_gate"]["checks"]
        if not check["passed"]
    }
    assert failed["p95_retrieval_latency_ms"]["reason"] == "missing_metric"


def test_rag_eval_retrieval_metrics_respect_top5_and_top10_boundaries(tmp_path):
    case = RAGEvalCase(
        id="rank-boundaries",
        query="Which source explains Elasticsearch hybrid search?",
        relevant_sources=("docs/rag/vendor/elastic_official_hybrid_search.md",),
        expected_citations=("docs/rag/vendor/elastic_official_hybrid_search.md",),
        required_answer_terms=("hybrid",),
    )

    def fake_answer(query, root):
        citations = [
            {"source": f"docs/rag/noise/source-{index}.md", "snippet": "noise"}
            for index in range(1, 6)
        ]
        citations.append(
            {
                "source": "docs/rag/vendor/elastic_official_hybrid_search.md",
                "snippet": "hybrid retrieval is documented by Elastic",
            }
        )
        return {
            "answer": "Elastic documents hybrid retrieval.",
            "retrieval_latency_ms": 25.0,
            "citations": citations,
        }

    report = evaluate_rag(root=tmp_path, cases=[case], answer_fn=fake_answer)
    scored = report["cases"][0]

    assert scored["recall_at_5"] == 0.0
    assert scored["mrr_at_10"] == 1 / 6
    assert scored["context_precision"] == 1 / 6
    assert scored["citation_accuracy"] == 1.0


def test_rag_eval_threshold_gate_allows_exact_production_boundaries():
    gate = evaluate_thresholds(
        {
            "recall_at_5": 0.90,
            "mrr_at_10": 0.75,
            "context_precision": 0.70,
            "answer_correctness": 0.85,
            "faithfulness": 0.85,
            "citation_accuracy": 0.90,
            "refusal_accuracy": 0.90,
            "p95_retrieval_latency_ms": 800.0,
            "p95_end_to_end_latency_ms": 6000.0,
        }
    )

    assert gate["passed"] is True
    assert gate["failed_metrics"] == []


def test_git_managed_golden_eval_has_no_per_case_metric_failures():
    repo_root = Path(__file__).resolve().parents[3]
    cases = load_eval_cases(repo_root / "docs/rag/evals/image_agent_rag_eval.json")

    report = evaluate_rag(root=repo_root, cases=cases)

    assert report["threshold_gate"]["passed"] is True
    assert report["aggregate"]["failed_case_count"] == 0
