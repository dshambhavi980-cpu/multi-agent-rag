from app.services.readiness import ReadinessRegistry, static_check


async def test_registry_aggregates_degraded_state() -> None:
    registry = ReadinessRegistry(
        checks={
            "application": static_check("ready"),
            "provider": static_check("degraded"),
        }
    )

    result = await registry.evaluate()

    assert result.status == "degraded"
    assert result.dependencies == {
        "application": "ready",
        "provider": "degraded",
    }
