import json
from pathlib import Path
from typing import Any, cast

import tomllib
import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(detail)


def main() -> None:
    render = cast(dict[str, Any], yaml.safe_load((ROOT / "render.yaml").read_text()))
    service = cast(dict[str, Any], render["services"][0])
    command = str(service["startCommand"])
    require(service["healthCheckPath"] == "/health", "Render must use /health.")
    require(
        "--workers 1" in command, "Render must use one memory-conscious API worker."
    )
    require("--limit-concurrency" in command, "Render must apply request backpressure.")
    secret_keys = {
        "APP_SUPABASE_URL",
        "APP_SUPABASE_PUBLISHABLE_KEY",
        "APP_SUPABASE_SERVICE_ROLE_KEY",
        "GEMINI_API_KEY",
    }
    env = {item["key"]: item for item in service["envVars"]}
    require(secret_keys <= env.keys(), "Render secret declarations are incomplete.")
    require(
        all(env[key].get("sync") is False for key in secret_keys),
        "Render secrets must remain dashboard-managed.",
    )

    vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    require(
        vercel["rewrites"][0]["destination"] == "/index.html",
        "Vercel SPA rewrite missing.",
    )
    header_keys = {item["key"] for item in vercel["headers"][0]["headers"]}
    require("Content-Security-Policy" in header_keys, "Vercel CSP is missing.")

    wrangler = tomllib.loads(
        (ROOT / "apps/web/wrangler.toml").read_text(encoding="utf-8")
    )
    require(
        wrangler["pages_build_output_dir"] == "./dist",
        "Cloudflare output is incorrect.",
    )
    redirects = (ROOT / "apps/web/public/_redirects").read_text(encoding="utf-8")
    require("/* /index.html 200" in redirects, "Cloudflare SPA fallback is missing.")
    cloudflare_headers = (ROOT / "apps/web/public/_headers").read_text(encoding="utf-8")
    require(
        "Content-Security-Policy" in cloudflare_headers, "Cloudflare CSP is missing."
    )

    supabase = tomllib.loads(
        (ROOT / "supabase/config.toml").read_text(encoding="utf-8")
    )
    require(
        supabase["auth"]["enable_anonymous_sign_ins"] is True,
        "Guest auth must be enabled.",
    )
    require(supabase["storage"]["file_size_limit"] == "25MiB", "Upload limit drifted.")
    require((ROOT / "supabase/seed.sql").exists(), "Local demo seed is missing.")
    print("Release configuration is reproducible and secret-safe.")


if __name__ == "__main__":
    main()
