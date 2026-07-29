from uuid import UUID

from httpx import AsyncClient

from app.services.readiness import ReadinessRegistry, static_check


async def test_health_reports_liveness_and_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["cold_start"] is False
    UUID(response.headers["X-Request-ID"])
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


async def test_cors_accepts_configured_origin_without_trailing_slash(
    client: AsyncClient,
) -> None:
    response = await client.options(
        "/rag/ask",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-workspace-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


async def test_valid_request_id_is_preserved(client: AsyncClient) -> None:
    request_id = "e7e1fe38-6cbc-4cc1-a7b6-5c30158f1f54"

    response = await client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


async def test_https_responses_enable_hsts(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


async def test_invalid_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "not-a-uuid"})

    assert response.headers["X-Request-ID"] != "not-a-uuid"
    UUID(response.headers["X-Request-ID"])


async def test_readiness_reports_dependencies(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"application": "ready"},
    }


async def test_unavailable_dependency_returns_503(client: AsyncClient) -> None:
    application = client._transport.app  # type: ignore[attr-defined]
    application.state.readiness = ReadinessRegistry(
        checks={
            "application": static_check("ready"),
            "database": static_check("unavailable"),
        }
    )

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["dependencies"]["database"] == "unavailable"


async def test_degraded_dependency_keeps_endpoint_available(client: AsyncClient) -> None:
    application = client._transport.app  # type: ignore[attr-defined]
    application.state.readiness = ReadinessRegistry(
        checks={"application": static_check("degraded")}
    )

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


async def test_version_uses_runtime_configuration(client: AsyncClient) -> None:
    response = await client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "version": "0.1.0",
        "commit": "test-commit",
        "environment": "test",
    }
