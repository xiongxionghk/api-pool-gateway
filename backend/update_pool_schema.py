import sqlite3
import os
from pathlib import Path

# Locate the database
# Assuming this script is in backend/
# Current working dir of the script will be backend/ if run from there, or we use relative paths
# The user's repo structure seems to be:
# api-pool-gateway/
#   backend/
#   data/ (gateway.db seems to be here based on fix_db_schema.py)
#   frontend/

base_dir = Path(__file__).resolve().parent.parent
db_path = base_dir / "data" / "gateway.db"

print(f"Checking database at: {db_path}")

if not db_path.exists():
    # Fallback check if running from root
    db_path = Path("data/gateway.db")
    if not db_path.exists():
        print(f"Database file not found at {db_path}!")
        # It's possible the DB hasn't been created yet if it's a fresh install
        # In that case, SQLAlchemy create_all will handle it.
        # But if it exists, we must patch it.
        exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check pools table
    # Ensure table exists first
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pools'")
    if not cursor.fetchone():
        print("Pools table does not exist yet. Skipping migration.")
    else:
        cursor.execute("PRAGMA table_info(pools)")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"Pools table columns: {columns}")

        if "timeout_seconds" not in columns:
            print("Adding column: timeout_seconds")
            cursor.execute("ALTER TABLE pools ADD COLUMN timeout_seconds INTEGER DEFAULT 60")
        else:
            print("Column timeout_seconds already exists")

    conn.commit()
    print("✅ Database schema updated successfully!")

except Exception as e:
    print(f"❌ Error updating database: {e}")
    conn.rollback()
finally:
    conn.close()
