import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks" / "retrieval" / "cases.json"


def reciprocal_rank(items: list[dict[str, Any]], expected: set[str]) -> float:
    for rank, item in enumerate(items, start=1):
        if str(item["filename"]) in expected:
            return 1 / rank
    return 0


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[position]


def search(
    *,
    base_url: str,
    token: str,
    workspace_id: str,
    case: dict[str, Any],
    mode: str,
) -> tuple[dict[str, Any], float]:
    if urlparse(base_url).scheme not in {"http", "https"}:
        raise ValueError("Base URL must use HTTP or HTTPS.")
    body = json.dumps(
        {
            "query": case["query"],
            "mode": mode,
            "limit": 6,
            "candidate_count": 30,
            "filters": case.get("filters", {}),
        }
    ).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/retrieval/search",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Workspace-ID": workspace_id,
        },
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = cast(dict[str, Any], json.load(response))
    return payload, (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare hybrid and dense retrieval quality."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    arguments = parser.parse_args()
    dataset = cast(
        dict[str, Any],
        json.loads(arguments.dataset.read_text(encoding="utf-8")),
    )
    metrics: dict[str, list[float]] = {"hybrid": [], "dense": []}
    latencies: list[float] = []
    for case in dataset["cases"]:
        expected = set(case["expected_filenames"])
        for mode in ("hybrid", "dense"):
            result, duration = search(
                base_url=arguments.base_url,
                token=arguments.token,
                workspace_id=arguments.workspace_id,
                case=case,
                mode=mode,
            )
            metrics[mode].append(reciprocal_rank(result["items"], expected))
            latencies.append(duration)

    hybrid_mrr = statistics.fmean(metrics["hybrid"])
    dense_mrr = statistics.fmean(metrics["dense"])
    report = {
        "cases": len(dataset["cases"]),
        "hybrid_mrr": round(hybrid_mrr, 4),
        "dense_mrr": round(dense_mrr, 4),
        "warm_p95_ms": round(percentile(latencies, 0.95), 3),
    }
    print(json.dumps(report, indent=2))
    if hybrid_mrr <= dense_mrr:
        raise SystemExit("Hybrid retrieval did not outperform dense-only retrieval.")


if __name__ == "__main__":
    main()
