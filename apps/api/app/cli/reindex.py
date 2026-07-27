import argparse
import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.infrastructure.supabase.admin import SupabaseAdminClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Queue a controlled document or workspace re-index."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--document-id", type=UUID)
    target.add_argument("--workspace", action="store_true")
    parser.add_argument("--workspace-id", type=UUID, required=True)
    parser.add_argument("--actor-id", type=UUID, required=True)
    parser.add_argument(
        "--strategy",
        choices=("fixed", "recursive", "heading_recursive"),
        default=None,
    )
    return parser


async def _run(arguments: argparse.Namespace) -> Any:
    settings = get_settings()
    if settings.supabase_url is None or settings.supabase_service_role_key is None:
        raise SystemExit("APP_SUPABASE_URL and APP_SUPABASE_SERVICE_ROLE_KEY are required.")
    client = SupabaseAdminClient(
        supabase_url=str(settings.supabase_url),
        service_key=settings.supabase_service_role_key.get_secret_value(),
        timeout_seconds=settings.supabase_http_timeout_seconds,
    )
    try:
        common = {
            "p_workspace_id": str(arguments.workspace_id),
            "p_actor_id": str(arguments.actor_id),
            "p_request_id": str(uuid4()),
            "p_strategy": arguments.strategy,
        }
        if arguments.document_id:
            return await client.rpc(
                "enqueue_document_reindex",
                {"p_document_id": str(arguments.document_id), **common},
            )
        return await client.rpc("enqueue_workspace_reindex", common)
    finally:
        await client.aclose()


def main() -> None:
    arguments = _parser().parse_args()
    print(json.dumps(asyncio.run(_run(arguments)), indent=2))  # noqa: T201


if __name__ == "__main__":
    main()
