from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        git_sha="test-commit",
        cold_start_window_seconds=0,
        cors_origins=[AnyHttpUrl("http://localhost:5173")],
        supabase_url=None,
        supabase_publishable_key=None,
        supabase_service_role_key=None,
        ingestion_worker_enabled=False,
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
