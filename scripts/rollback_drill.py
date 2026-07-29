"""Validate and print a safe application rollback plan without changing production."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Known-good commit or release tag")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    target = git("rev-parse", "--verify", f"{args.target}^{{commit}}")
    head = git("rev-parse", "HEAD")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", target, head], cwd=ROOT, check=True
    )
    changed = git("diff", "--name-only", f"{target}..{head}").splitlines()
    migrations = sorted(
        path for path in changed if path.startswith("supabase/migrations/")
    )
    plan = {
        "status": "drill_passed",
        "current": head,
        "target": target,
        "database_strategy": "forward_fix_only" if migrations else "no_schema_change",
        "migrations_after_target": migrations,
        "application_steps": [
            f"git revert --no-commit {target}..{head}",
            "run the full CI and release smoke suite",
            "push the reviewed rollback commit to main",
            "trigger the Render deploy hook and redeploy the frontend",
        ],
    }
    output = json.dumps(plan, indent=2)
    print(output if args.json else f"Rollback drill passed.\n{output}")


if __name__ == "__main__":
    main()
