"""Record a non-secret release and deployment configuration snapshot."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    api_url = args.api_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        health = client.get(f"{api_url}/health")
        version = client.get(f"{api_url}/version")
        frontend = client.get(frontend_url)
        for response in (health, version, frontend):
            response.raise_for_status()
    body = version.json()
    snapshot = {
        "release": args.release,
        "recorded_at": datetime.now(UTC).isoformat(),
        "api_url": api_url,
        "frontend_url": frontend_url,
        "api_version": body,
        "security_headers": {
            "api": {
                key: health.headers.get(key)
                for key in (
                    "strict-transport-security",
                    "x-content-type-options",
                    "x-frame-options",
                )
            },
            "frontend": {
                key: frontend.headers.get(key)
                for key in (
                    "content-security-policy",
                    "strict-transport-security",
                    "x-content-type-options",
                    "x-frame-options",
                )
            },
        },
    }
    output = args.output or Path(f"artifacts/releases/{args.release}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
