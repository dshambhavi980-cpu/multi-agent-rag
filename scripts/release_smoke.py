"""Run the public DocPilot release smoke suite against a deployed environment."""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

import httpx

DEMO_DOCUMENT = b"""# DocPilot Release Demonstration

The release codename is HORIZON-14. Hybrid retrieval combines semantic similarity
with exact keyword matching. Human approval pauses sensitive agent actions before
the final answer is published.
"""
TERMINAL_JOBS = {"completed", "failed", "quarantined"}
TERMINAL_RUNS = {"completed", "failed", "cancelled", "timed_out", "awaiting_approval"}


@dataclass(frozen=True)
class ReleaseTarget:
    api_url: str
    supabase_url: str
    publishable_key: str
    service_role_key: str | None = None


class SmokeFailure(RuntimeError):
    pass


def expect(response: httpx.Response, *statuses: int) -> Any:
    if response.status_code not in statuses:
        raise SmokeFailure(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}: {response.text[:300]}"
        )
    return response.json() if response.content else None


def run_smoke(
    target: ReleaseTarget,
    timeout_seconds: int = 180,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {"checks": []}
    user_id: str | None = None
    workspace_id: str | None = None
    object_path: str | None = None
    token: str | None = None
    client = httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=True)
    try:
        health, version = _wait_for_release(
            client, target.api_url, expected_commit, timeout_seconds
        )
        expect(client.get(f"{target.api_url}/ready"), 200)
        report["checks"].append("system")

        auth_headers = {
            "apikey": target.publishable_key,
            "Content-Type": "application/json",
        }
        session = expect(
            client.post(
                f"{target.supabase_url}/auth/v1/signup", headers=auth_headers, json={}
            ),
            200,
        )
        token = str(session["access_token"])
        user_id = str(session["user"]["id"])
        workspace_id = str(uuid4())
        user_headers = {
            "apikey": target.publishable_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        workspace = {
            "id": workspace_id,
            "name": "DocPilot Release Smoke",
            "created_by": user_id,
        }
        expect(
            client.post(
                f"{target.supabase_url}/rest/v1/workspaces",
                headers={**user_headers, "Prefer": "return=minimal"},
                json=workspace,
            ),
            201,
        )
        api_headers = {
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": workspace_id,
        }
        expect(client.get(f"{target.api_url}/v1/auth/me", headers=api_headers), 200)
        report["checks"].append("anonymous_auth")

        digest = hashlib.sha256(DEMO_DOCUMENT).hexdigest()
        signed = expect(
            client.post(
                f"{target.api_url}/v1/documents/upload-url",
                headers=api_headers,
                json={
                    "filename": "docpilot-release-demo.md",
                    "content_type": "text/markdown",
                    "size_bytes": len(DEMO_DOCUMENT),
                    "sha256": digest,
                },
            ),
            201,
        )
        object_path = str(signed["object_path"])
        expect(
            client.put(
                str(signed["signed_url"]),
                headers={
                    "apikey": target.publishable_key,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/markdown",
                    "cache-control": "max-age=3600",
                    "x-upsert": "false",
                },
                content=DEMO_DOCUMENT,
            ),
            200,
        )
        accepted = expect(
            client.post(
                f"{target.api_url}/v1/documents/complete-upload",
                headers=api_headers,
                json={
                    "upload_id": signed["upload_id"],
                    "object_path": object_path,
                    "sha256": digest,
                    "title": "Release Demonstration",
                    "tags": ["release", "demo"],
                },
            ),
            202,
        )
        if accepted.get("job") is None:
            raise SmokeFailure("Upload was accepted without an ingestion job.")
        job = _poll(
            client,
            f"{target.api_url}/v1/ingestion-jobs/{accepted['job']['id']}",
            api_headers,
            "status",
            TERMINAL_JOBS,
            timeout_seconds,
        )
        if job["status"] != "completed":
            raise SmokeFailure(
                f"Ingestion ended in {job['status']}: {job.get('error_detail')}"
            )
        report["checks"].append("upload_and_ingestion")

        retrieval = expect(
            client.post(
                f"{target.api_url}/v1/retrieval/search",
                headers=api_headers,
                json={"query": "HORIZON-14", "mode": "hybrid", "limit": 3},
            ),
            200,
        )
        items = cast(list[dict[str, Any]], retrieval.get("items", []))
        if not items or not any(
            "HORIZON-14" in str(item.get("content")) for item in items
        ):
            raise SmokeFailure(
                "Hybrid retrieval did not return the seeded release marker."
            )
        report["checks"].append("hybrid_retrieval")

        conversation = expect(
            client.post(
                f"{target.api_url}/v1/conversations",
                headers={
                    **api_headers,
                    "Idempotency-Key": f"smoke-conversation-{uuid4()}",
                },
                json={"title": "Release smoke"},
            ),
            201,
        )
        run = expect(
            client.post(
                f"{target.api_url}/v1/conversations/{conversation['id']}/messages",
                headers={**api_headers, "Idempotency-Key": f"smoke-message-{uuid4()}"},
                json={
                    "content": "What is the release codename?",
                    "force_mode": "simple",
                },
            ),
            202,
        )
        finished = _poll(
            client,
            f"{target.api_url}/v1/runs/{run['run_id']}",
            api_headers,
            "status",
            TERMINAL_RUNS,
            timeout_seconds,
        )
        if finished["status"] != "completed":
            raise SmokeFailure(f"Grounded chat ended in {finished['status']}.")
        report["checks"].append("grounded_chat")
        report.update(
            {
                "status": "passed",
                "version": version,
                "cold_start": bool(health["cold_start"]),
            }
        )
        return report
    finally:
        _cleanup(client, target, token, user_id, workspace_id, object_path)
        client.close()


def _poll(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    field: str,
    terminal: set[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        body = cast(dict[str, Any], expect(client.get(url, headers=headers), 200))
        if body.get(field) in terminal:
            return body
        time.sleep(2)
    raise SmokeFailure(f"Timed out waiting for {url}.")


def _wait_for_release(
    client: httpx.Client,
    api_url: str,
    expected_commit: str | None,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last_commit = "unavailable"
    while time.monotonic() < deadline:
        try:
            health_response = client.get(f"{api_url}/health")
            version_response = client.get(f"{api_url}/version")
            if (
                health_response.status_code == 200
                and version_response.status_code == 200
            ):
                health = cast(dict[str, Any], health_response.json())
                version = cast(dict[str, Any], version_response.json())
                last_commit = str(version.get("commit", "unknown"))
                if expected_commit is None or (
                    last_commit.startswith(expected_commit)
                    or expected_commit.startswith(last_commit)
                ):
                    return health, version
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(5)
    raise SmokeFailure(
        "Timed out waiting for the expected backend release. "
        f"Expected {expected_commit or 'a healthy release'}, last observed {last_commit}."
    )


def _cleanup(
    client: httpx.Client,
    target: ReleaseTarget,
    token: str | None,
    user_id: str | None,
    workspace_id: str | None,
    object_path: str | None,
) -> None:
    cleanup_key = target.service_role_key or target.publishable_key
    cleanup_token = target.service_role_key or token
    if cleanup_token and object_path:
        client.request(
            "DELETE",
            f"{target.supabase_url}/storage/v1/object/workspace-documents",
            headers={
                "apikey": cleanup_key,
                "Authorization": f"Bearer {cleanup_token}",
                "Content-Type": "application/json",
            },
            json={"prefixes": [object_path]},
        )
    if cleanup_token and workspace_id:
        client.delete(
            f"{target.supabase_url}/rest/v1/workspaces?id=eq.{workspace_id}",
            headers={
                "apikey": cleanup_key,
                "Authorization": f"Bearer {cleanup_token}",
            },
        )
    if target.service_role_key and user_id:
        client.delete(
            f"{target.supabase_url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": target.service_role_key,
                "Authorization": f"Bearer {target.service_role_key}",
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=os.getenv("DOC_PILOT_API_URL"))
    parser.add_argument("--supabase-url", default=os.getenv("APP_SUPABASE_URL"))
    parser.add_argument(
        "--publishable-key", default=os.getenv("APP_SUPABASE_PUBLISHABLE_KEY")
    )
    parser.add_argument(
        "--service-role-key", default=os.getenv("APP_SUPABASE_SERVICE_ROLE_KEY")
    )
    parser.add_argument("--expected-commit", default=os.getenv("EXPECTED_GIT_COMMIT"))
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not args.api_url or not args.supabase_url or not args.publishable_key:
        parser.error("API URL, Supabase URL, and publishable key are required.")
    report = run_smoke(
        ReleaseTarget(
            api_url=args.api_url.rstrip("/"),
            supabase_url=args.supabase_url.rstrip("/"),
            publishable_key=args.publishable_key,
            service_role_key=args.service_role_key,
        ),
        args.timeout,
        args.expected_commit,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
