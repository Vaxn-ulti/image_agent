# image_agent RAG Instructions

RAG is local file_search-like retrieval over `docs/rag` and `docs/skills`. It explains workflows, contracts, metrics, troubleshooting, vendor summaries, and safety policy.

Use this priority order: backend DB/task/output records > result-summary > skill policy/reference > RAG docs > model prior.

Do not put API keys, raw patient data, raw images, or sensitive logs into RAG. When retrieved documents are stale or conflict with backend state, keep backend state authoritative.
