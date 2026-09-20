"""Restores the Postgres database from a .sql dump made by backup_db.py.

DESTRUCTIVE: this overwrites all current data in the database with the
contents of the backup. Requires typing "yes" to confirm unless --force
is passed.

Usage:
    python backend/scripts/restore_db.py                  # restores the latest backup
    python backend/scripts/restore_db.py path/to/dump.sql  # restores a specific backup
    python backend/scripts/restore_db.py --force           # skip the confirmation prompt
"""

import subprocess
import sys
from pathlib import Path

COMPOSE_SERVICE = "postgres"
DB_NAME = "clause_platform"
DB_USER = "postgres"
BACKUPS_DIR = Path(__file__).parent.parent / "backups"


def repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def latest_backup() -> Path | None:
    backups = sorted(BACKUPS_DIR.glob(f"{DB_NAME}_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]

    if args:
        source = Path(args[0])
    else:
        source = latest_backup()
        if source is None:
            print(f"No backups found in {BACKUPS_DIR}. Run backup_db.py first.", file=sys.stderr)
            sys.exit(1)

    if not source.exists():
        print(f"Backup file not found: {source}", file=sys.stderr)
        sys.exit(1)

    print(f"This will OVERWRITE the '{DB_NAME}' database with: {source}")
    if not force:
        confirm = input("Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Cancelled.")
            sys.exit(0)

    with source.open("rb") as f:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", COMPOSE_SERVICE, "psql", "-U", DB_USER, "-d", DB_NAME],
            cwd=repo_root(),
            stdin=f,
            stderr=subprocess.PIPE,
        )

    if result.returncode != 0:
        print(result.stderr.decode(errors="replace"), file=sys.stderr)
        print("Restore FAILED.", file=sys.stderr)
        sys.exit(1)

    print(f"Restored '{DB_NAME}' from {source}")


if __name__ == "__main__":
    main()
