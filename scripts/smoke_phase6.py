from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx

TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.timed_out"}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def require(values: dict[str, str], key: str) -> str:
    value = values.get(key)
    if not value:
        raise RuntimeError(f"{key} is required in .env")
    return value


async def stream_run(
    client: httpx.AsyncClient,
    *,
    events_url: str,
    headers: dict[str, str],
    started: float,
) -> tuple[list[dict[str, Any]], float | None]:
    events: list[dict[str, Any]] = []
    first_delta_ms: float | None = None
    event_name = ""
    async with client.stream(
        "GET", events_url, headers=headers, timeout=90
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                payload = cast(
                    dict[str, Any], json.loads(line.removeprefix("data:").strip())
                )
                events.append(payload)
                if event_name == "answer.delta" and first_delta_ms is None:
                    first_delta_ms = (time.perf_counter() - started) * 1000
                if event_name in TERMINAL_EVENTS:
                    break
    return events, first_delta_ms


async def wait_until_ready(
    client: httpx.AsyncClient,
    *,
    api_headers: dict[str, str],
    document_id: str,
) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = await client.get("/v1/documents", headers=api_headers)
        response.raise_for_status()
        documents = cast(list[dict[str, Any]], response.json()["items"])
        document = next((item for item in documents if item["id"] == document_id), None)
        if document and document["status"] == "ready":
            return
        if document and document["status"] in {"failed", "quarantined"}:
            raise RuntimeError(f"Ingestion ended as {document['status']}")
        await asyncio.sleep(1)
    raise TimeoutError("Document did not become ready within 120 seconds")


async def run(base_url: str, env_path: Path) -> dict[str, Any]:
    env = load_env(env_path)
    supabase_url = require(env, "APP_SUPABASE_URL").rstrip("/")
    publishable_key = require(env, "APP_SUPABASE_PUBLISHABLE_KEY")
    service_key = require(env, "APP_SUPABASE_SERVICE_ROLE_KEY")
    email = f"phase6-{uuid4()}@example.test"
    password = f"Phase6-{secrets.token_urlsafe(24)}"
    user_id: str | None = None
    workspace_id: str | None = None

    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as external:
        admin_headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        }
        try:
            created_user = await external.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers=admin_headers,
                json={"email": email, "password": password, "email_confirm": True},
            )
            created_user.raise_for_status()
            user_id = str(created_user.json()["id"])

            signed_in = await external.post(
                f"{supabase_url}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": publishable_key},
                json={"email": email, "password": password},
            )
            signed_in.raise_for_status()
            access_token = str(signed_in.json()["access_token"])
            created_workspace = await external.post(
                f"{supabase_url}/rest/v1/workspaces",
                headers={**admin_headers, "Prefer": "return=representation"},
                json={"name": "Phase 6 smoke", "created_by": user_id},
            )
            created_workspace.raise_for_status()
            workspace_id = str(created_workspace.json()[0]["id"])

            api_headers = {
                "Authorization": f"Bearer {access_token}",
                "X-Workspace-ID": workspace_id,
            }
            source = (
                Path(__file__).resolve().parents[1]
                / "benchmarks"
                / "retrieval"
                / "corpus"
                / "operations.md"
            )
            content = source.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()

            async with httpx.AsyncClient(base_url=base_url, timeout=45) as api:
                upload = await api.post(
                    "/v1/documents/upload-url",
                    headers=api_headers,
                    json={
                        "filename": source.name,
                        "content_type": "text/markdown",
                        "size_bytes": len(content),
                        "sha256": checksum,
                    },
                )
                upload.raise_for_status()
                signed = cast(dict[str, Any], upload.json())
                stored = await external.put(
                    str(signed["signed_url"]),
                    headers={"Content-Type": "text/markdown", "x-upsert": "false"},
                    content=content,
                )
                stored.raise_for_status()
                complete = await api.post(
                    "/v1/documents/complete-upload",
                    headers=api_headers,
                    json={
                        "upload_id": signed["upload_id"],
                        "object_path": signed["object_path"],
                        "sha256": checksum,
                    },
                )
                complete.raise_for_status()
                document_id = str(complete.json()["document"]["id"])
                await wait_until_ready(
                    api,
                    api_headers=api_headers,
                    document_id=document_id,
                )

                conversation_headers = {
                    **api_headers,
                    "Idempotency-Key": f"conversation-{uuid4()}",
                }
                conversation = await api.post(
                    "/v1/conversations",
                    headers=conversation_headers,
                    json={"title": "Emergency operations"},
                )
                conversation.raise_for_status()
                conversation_id = str(conversation.json()["id"])

                answer_started = time.perf_counter()
                accepted = await api.post(
                    f"/v1/conversations/{conversation_id}/messages",
                    headers={
                        **api_headers,
                        "Idempotency-Key": f"supported-{uuid4()}",
                    },
                    json={
                        "content": "How should the ZX-42 emergency access token be reset?",
                        "document_ids": [document_id],
                        "force_mode": "simple",
                    },
                )
                accepted.raise_for_status()
                supported_events, ttft_ms = await stream_run(
                    api,
                    events_url=str(accepted.json()["events_url"]),
                    headers=api_headers,
                    started=answer_started,
                )
                supported_run = await api.get(
                    f"/v1/runs/{accepted.json()['run_id']}",
                    headers=api_headers,
                )
                supported_run.raise_for_status()
                detail = await api.get(
                    f"/v1/conversations/{conversation_id}",
                    headers=api_headers,
                )
                detail.raise_for_status()
                assistant_messages = [
                    message
                    for message in detail.json()["messages"]
                    if message["role"] == "assistant"
                ]
                if not assistant_messages:
                    terminal = supported_run.json()
                    event_summary = [
                        {
                            "event_type": event.get("event_type"),
                            "code": event.get("code"),
                            "detail": event.get("detail"),
                        }
                        for event in supported_events
                    ]
                    raise RuntimeError(
                        "Supported run did not persist an assistant message: "
                        f"run={terminal!r}, events={event_summary!r}"
                    )
                answer = assistant_messages[-1]
                citations = cast(list[dict[str, Any]], answer["citations"])
                if not citations or any(
                    citation["citation_id"] not in answer["content"]
                    for citation in citations
                ):
                    raise RuntimeError(
                        "Supported answer did not retain validated citations"
                    )
                source_response = await api.get(
                    str(citations[0]["source_url"]),
                    headers=api_headers,
                    follow_redirects=False,
                )
                if source_response.status_code != 307:
                    raise RuntimeError(
                        "Citation source did not return a signed redirect"
                    )

                unsupported_started = time.perf_counter()
                unsupported = await api.post(
                    f"/v1/conversations/{conversation_id}/messages",
                    headers={
                        **api_headers,
                        "Idempotency-Key": f"unsupported-{uuid4()}",
                    },
                    json={
                        "content": "What is the cafeteria menu on Mars?",
                        "document_ids": [str(uuid4())],
                        "force_mode": "simple",
                    },
                )
                unsupported.raise_for_status()
                unsupported_events, unsupported_ttft_ms = await stream_run(
                    api,
                    events_url=str(unsupported.json()["events_url"]),
                    headers=api_headers,
                    started=unsupported_started,
                )
                unsupported_detail = await api.get(
                    f"/v1/conversations/{conversation_id}",
                    headers=api_headers,
                )
                unsupported_detail.raise_for_status()
                fallback = [
                    message
                    for message in unsupported_detail.json()["messages"]
                    if message["role"] == "assistant"
                ][-1]
                if fallback["answer_status"] != "insufficient_evidence":
                    raise RuntimeError("Unsupported question did not fail safely")

                return {
                    "document_status": "ready",
                    "supported_run_status": supported_run.json()["status"],
                    "supported_event_types": sorted(
                        {str(event["event_type"]) for event in supported_events}
                    ),
                    "citation_ids": [citation["citation_id"] for citation in citations],
                    "citation_source_status": source_response.status_code,
                    "warm_ttft_ms": round(ttft_ms or 0, 3),
                    "unsupported_answer_status": fallback["answer_status"],
                    "unsupported_event_types": sorted(
                        {str(event["event_type"]) for event in unsupported_events}
                    ),
                    "unsupported_ttft_ms": round(unsupported_ttft_ms or 0, 3),
                }
        finally:
            if workspace_id and user_id:
                await external.delete(
                    f"{supabase_url}/rest/v1/workspaces",
                    params={"id": f"eq.{workspace_id}"},
                    headers=admin_headers,
                )
            if user_id:
                await external.delete(
                    f"{supabase_url}/auth/v1/admin/users/{user_id}",
                    headers=admin_headers,
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the live Phase 6 acceptance smoke test."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    report = asyncio.run(run(args.base_url, args.env_file))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
