"""The one runtime setting this app has: where the SQLite file lives.

A single env var rather than a settings framework, because one setting does
not need one.
"""

import os

DB_PATH = os.environ.get("DATABASE_PATH", "data/app.db")
