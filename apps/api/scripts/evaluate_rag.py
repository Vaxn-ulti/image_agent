from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from app.agent.rag_eval import evaluate_rag, load_eval_cases
from app.agent.rag_index import build_local_rag_index


DEFAULT_EVAL_SET = Path("docs/rag/evals/image_agent_rag_eval.json")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate Image Agent RAG retrieval, generation, and system metrics.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[3])
    parser.add_argument("--eval-set", default=str(DEFAULT_EVAL_SET))
    parser.add_argument("--output-json", default="")
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument(
        "--fail-under-thresholds",
        action="store_true",
        help="Exit non-zero when the production RAG evaluation threshold gate fails.",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo_root)
    if args.rebuild_index:
        build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    eval_set = Path(args.eval_set)
    if not eval_set.is_absolute():
        eval_set = root / eval_set
    report = evaluate_rag(root=root, cases=load_eval_cases(eval_set))
    report["eval_set"] = str(eval_set)
    report["repo_root"] = str(root)
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.fail_under_thresholds and not report["threshold_gate"]["passed"]:
        failed = ", ".join(report["threshold_gate"]["failed_metrics"])
        raise SystemExit(f"RAG evaluation threshold gate failed: {failed}")


if __name__ == "__main__":
    main()
