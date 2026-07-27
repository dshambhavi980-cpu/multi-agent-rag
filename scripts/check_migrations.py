import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{14})_[a-z0-9_]+\.sql$")


def main() -> None:
    migrations = sorted(MIGRATIONS.glob("*.sql"))
    versions: set[str] = set()

    for migration in migrations:
        match = MIGRATION_PATTERN.fullmatch(migration.name)
        if match is None:
            raise ValueError(
                f"Invalid migration name {migration.name!r}; expected "
                "YYYYMMDDHHMMSS_description.sql."
            )
        version = match.group("version")
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}.")
        versions.add(version)
        if migration.stat().st_size == 0:
            raise ValueError(f"Migration is empty: {migration.name}.")

    print(f"Migration history valid: {len(migrations)} migration(s).")


if __name__ == "__main__":
    main()
