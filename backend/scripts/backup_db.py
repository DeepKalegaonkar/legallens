"""Backs up the Postgres database running in the docker-compose "postgres" service.

Runs `pg_dump` inside the running container and writes a timestamped .sql
dump to backend/backups/ on the host. Keeps only the most recent
MAX_BACKUPS_TO_KEEP dumps to avoid unbounded disk growth.

Run from the repo root or backend/, with the postgres container up
(`docker compose up -d postgres`):
    python backend/scripts/backup_db.py
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

COMPOSE_SERVICE = "postgres"
DB_NAME = "clause_platform"
DB_USER = "postgres"
BACKUPS_DIR = Path(__file__).parent.parent / "backups"
MAX_BACKUPS_TO_KEEP = 10


def repo_root() -> Path:
    # docker-compose.yml lives at the repo root, one level above backend/.
    return Path(__file__).parent.parent.parent


def main() -> None:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUPS_DIR / f"{DB_NAME}_{timestamp}.sql"

    print(f"Dumping '{DB_NAME}' from the '{COMPOSE_SERVICE}' container...")
    with destination.open("wb") as f:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", COMPOSE_SERVICE, "pg_dump", "-U", DB_USER, "-d", DB_NAME],
            cwd=repo_root(),
            stdout=f,
            stderr=subprocess.PIPE,
        )

    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        print(result.stderr.decode(errors="replace"), file=sys.stderr)
        print("Backup FAILED. Is the postgres container running? (docker compose up -d postgres)", file=sys.stderr)
        sys.exit(1)

    size_kb = destination.stat().st_size / 1024
    print(f"Saved backup: {destination} ({size_kb:.1f} KB)")

    _rotate_old_backups()


def _rotate_old_backups() -> None:
    backups = sorted(BACKUPS_DIR.glob(f"{DB_NAME}_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in backups[MAX_BACKUPS_TO_KEEP:]:
        stale.unlink()
        print(f"Removed old backup: {stale.name}")


if __name__ == "__main__":
    main()
