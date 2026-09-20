import os
import tempfile
from pathlib import Path

# The API tests run against a throwaway SQLite file, never the real database.
# This must be set before anything imports app.core.config.
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'test.db'}"
