---
source_type: rag_contract
status: product_eval_contract
retrieved_date: 2026-06-26
---

# RAG Evaluation Contract

Image Agent RAG is evaluated with a Git-managed golden set and repeatable JSON
reports. Retrieval metrics are Recall@5, MRR@10, and Context Precision.
Generation metrics are Answer Correctness, Faithfulness, Citation Accuracy, and
Refusal Accuracy. System metrics are P95 Latency, Average Cost per Query, and
optional User Satisfaction.

Run the local evaluator from `apps/api` with:

```bash
PYTHONPATH=. python scripts/evaluate_rag.py --repo-root ../..
```

Run the production threshold gate with:

```bash
PYTHONPATH=. python scripts/evaluate_rag.py --repo-root ../.. --fail-under-thresholds
```

The evaluator is deterministic by default. It scores required answer terms,
forbidden answer terms, expected citations, refusal behavior, measured latency,
and optional cost/satisfaction fields from the eval set or RAG response. LLM
judge scoring can be added later, but the baseline gate must remain runnable
without external model calls.

## Production Thresholds

The first usable release gate uses aggregate thresholds:

| Metric | Gate |
| --- | --- |
| Recall@5 | `>= 0.90` |
| MRR@10 | `>= 0.75` |
| Context Precision | `>= 0.70` |
| Answer Correctness | `>= 0.85` |
| Faithfulness | `>= 0.85` |
| Citation Accuracy | `>= 0.90` |
| Refusal Accuracy | `>= 0.90` |
| Retrieval P95 Latency | `<= 800 ms` |
| End-to-end P95 Latency | `<= 6000 ms` |

The JSON report includes `thresholds`, `threshold_gate`, and
`aggregate.threshold_passed`. `p95_latency_ms` is kept as a backward-compatible
alias for `p95_end_to_end_latency_ms`; new gates should read
`p95_retrieval_latency_ms` and `p95_end_to_end_latency_ms` explicitly.
If a required metric is not reported, the threshold gate fails with
`missing_metric`; missing retrieval latency must not be treated as zero.

Individual eval cases still expose `passed` for debugging. Release gating is
based on the aggregate `threshold_gate`, so a single weaker case can be visible
without failing the production gate when the aggregate target remains above the
threshold.
