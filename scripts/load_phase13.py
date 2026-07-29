"""Dependency-free Phase 13 load probe for health and authenticated API paths."""

import argparse
import asyncio
import json
import statistics
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx


@dataclass(frozen=True)
class Scenario:
    name: str
    method: str
    path: str
    body: dict[str, Any] | None = None


async def execute(
    client: httpx.AsyncClient, scenario: Scenario, semaphore: asyncio.Semaphore
) -> tuple[float, int]:
    async with semaphore:
        started = perf_counter()
        response = await client.request(
            scenario.method, scenario.path, json=scenario.body
        )
        await response.aread()
        return (perf_counter() - started) * 1000, response.status_code


async def run(args: argparse.Namespace) -> int:
    headers: dict[str, str] = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    if args.workspace_id:
        headers["X-Workspace-ID"] = args.workspace_id
    scenarios = [Scenario("health", "GET", "/health")]
    if args.token and args.workspace_id:
        scenarios.append(
            Scenario(
                "retrieval",
                "POST",
                "/v1/retrieval/search",
                {"query": args.query, "limit": 6, "candidate_count": 30},
            )
        )

    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.timeout
    ) as client:
        for scenario in scenarios:
            samples = await asyncio.gather(
                *(execute(client, scenario, semaphore) for _ in range(args.requests))
            )
            latencies = sorted(sample[0] for sample in samples)
            statuses: dict[int, int] = {}
            for _, status in samples:
                statuses[status] = statuses.get(status, 0) + 1
            report = {
                "scenario": scenario.name,
                "requests": len(samples),
                "concurrency": args.concurrency,
                "p50_ms": round(statistics.median(latencies), 2),
                "p95_ms": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 2),
                "max_ms": round(max(latencies), 2),
                "statuses": statuses,
            }
            print(json.dumps(report, sort_keys=True))
            if any(status >= 500 for status in statuses):
                return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--token")
    parser.add_argument("--workspace-id")
    parser.add_argument("--query", default="Summarize the indexed documents.")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
