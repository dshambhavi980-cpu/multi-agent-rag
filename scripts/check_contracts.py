from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    ROOT / "contracts" / "openapi.yaml",
    ROOT / "contracts" / "events.asyncapi.yaml",
)
READ_ONLY_POST_OPERATIONS = {"hybridSearch"}


def walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(walk(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(walk(value))
    return found


def resolve_pointer(document: dict[str, Any], pointer: str) -> Any:
    node: Any = document
    for raw_part in pointer.removeprefix("#/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def load_contract(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path.name} must contain a mapping at its root.")
    for node in walk(loaded):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/"):
            resolve_pointer(loaded, reference)
    return loaded


def validate_openapi(document: dict[str, Any]) -> None:
    if document.get("openapi") != "3.1.0":
        raise ValueError("The OpenAPI contract must use version 3.1.0.")

    operation_ids: list[str] = []
    methods = {"get", "post", "put", "patch", "delete"}
    for path, path_item in document["paths"].items():
        inherited = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method not in methods:
                continue
            operation_ids.append(operation["operationId"])
            if (
                path.startswith("/v1")
                and method in {"post", "put", "patch", "delete"}
                and operation["operationId"] not in READ_ONLY_POST_OPERATIONS
            ):
                parameters = [*inherited, *operation.get("parameters", [])]
                names = {
                    resolve_pointer(document, item["$ref"])["name"]
                    if "$ref" in item
                    else item["name"]
                    for item in parameters
                }
                if "Idempotency-Key" not in names:
                    raise ValueError(
                        f"{method.upper()} {path} must require Idempotency-Key."
                    )

    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("OpenAPI operationId values must be unique.")


def main() -> None:
    openapi = load_contract(CONTRACTS[0])
    asyncapi = load_contract(CONTRACTS[1])
    validate_openapi(openapi)
    if asyncapi.get("asyncapi") != "2.6.0":
        raise ValueError("The event contract must use AsyncAPI 2.6.0.")
    print(
        "Contracts valid:"
        f" {len(openapi['paths'])} HTTP paths,"
        f" {len(asyncapi['channels'])} event channels."
    )


if __name__ == "__main__":
    main()
