"""Generate a compact CycloneDX inventory from installed Python and npm packages."""

import importlib.metadata
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def main() -> None:
    python_components = [
        {
            "type": "library",
            "name": item.metadata["Name"],
            "version": item.version,
            "purl": f"pkg:pypi/{item.metadata['Name']}@{item.version}",
        }
        for item in importlib.metadata.distributions()
        if item.metadata["Name"]
    ]
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        raise RuntimeError("npm is required to generate the JavaScript SBOM")
    npm_result = subprocess.run(
        [npm, "ls", "--all", "--json"], capture_output=True, text=True, check=False
    )
    npm_tree: dict[str, Any] = json.loads(npm_result.stdout or "{}")
    npm_components: dict[str, dict[str, str]] = {}

    def visit(dependencies: dict[str, Any]) -> None:
        for name, value in dependencies.items():
            version = str(value.get("version", "unknown"))
            npm_components[f"{name}@{version}"] = {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:npm/{name}@{version}",
            }
            visit(value.get("dependencies", {}))

    visit(npm_tree.get("dependencies", {}))
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": sorted(
            [*python_components, *npm_components.values()],
            key=lambda item: item["purl"],
        ),
    }
    output = Path("artifacts/sbom.cdx.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(document['components'])} components to {output}")


if __name__ == "__main__":
    main()
