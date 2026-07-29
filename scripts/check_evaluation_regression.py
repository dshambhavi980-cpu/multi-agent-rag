import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.evaluation_metrics import (
    answer_metrics,
    release_gate,
    retrieval_metrics,
)

SNAPSHOT = ROOT / "benchmarks" / "evaluation" / "regression_snapshot.json"


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0


def main() -> None:
    snapshot = cast(
        dict[str, Any], json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    )
    retrieval: dict[str, list[float]] = {
        "hybrid": [],
        "dense_only": [],
        "keyword_only": [],
    }
    tenant_results: list[float] = []
    for case in snapshot["retrieval_cases"]:
        for variant, source_key in (
            ("hybrid", "hybrid"),
            ("dense_only", "dense"),
            ("keyword_only", "keyword_only"),
        ):
            filenames = cast(list[str], case[source_key])
            items = [
                {"filename": filename, "section_heading": ""}
                for filename in filenames
            ]
            scored = retrieval_metrics(
                items,
                expected_filenames=case["expected"],
                expected_source_chunks=[],
            )
            retrieval[variant].append(scored["ndcg"])
            forbidden = set(case.get("forbidden", []))
            if forbidden:
                tenant_results.append(
                    float(not any(filename in forbidden for filename in filenames))
                )

    answer_scores = []
    critical_scores = []
    for case in snapshot["answer_cases"]:
        score = answer_metrics(
            answer=case["answer"],
            citations=[{"label": label} for label in case["citations"]],
            expected_filenames=case["expected"],
            expected_facts=case["facts"],
            forbidden_terms=case.get("forbidden", []),
            forbidden_filenames=[],
            answer_status="grounded" if case["expected"] else "insufficient_evidence",
        )
        answer_scores.append(score)
        if case.get("critical"):
            critical_scores.append(score["safety_pass"])
        if case.get("tenant"):
            tenant_results.append(score["safety_pass"])

    hybrid_ndcg = mean(retrieval["hybrid"])
    dense_ndcg = mean(retrieval["dense_only"])
    metrics = {
        "hybrid_ndcg": round(hybrid_ndcg, 4),
        "dense_only_ndcg": round(dense_ndcg, 4),
        "keyword_only_ndcg": round(mean(retrieval["keyword_only"]), 4),
        "hybrid_ndcg_gain": round(
            (hybrid_ndcg - dense_ndcg) / dense_ndcg if dense_ndcg else 1,
            4,
        ),
        "citation_precision": round(
            mean([score["citation_precision"] for score in answer_scores]), 4
        ),
        "citation_recall": round(
            mean([score["citation_recall"] for score in answer_scores]), 4
        ),
        "groundedness": round(
            mean([score["groundedness"] for score in answer_scores]), 4
        ),
        "answer_coverage": round(
            mean([score["answer_coverage"] for score in answer_scores]), 4
        ),
        "critical_safety_pass_rate": round(mean(critical_scores), 4),
        "tenant_isolation_pass_rate": round(mean(tenant_results), 4),
    }
    gate = release_gate(metrics)
    print(json.dumps({**metrics, "gate_passed": gate.passed}, indent=2))
    if not gate.passed:
        raise SystemExit(
            f"Evaluation regression blocks release: {', '.join(gate.failures)}"
        )


if __name__ == "__main__":
    main()
