
import sqlite3
import os
from pathlib import Path

# Locate the database
base_dir = Path(__file__).parent.parent
db_path = base_dir / "data" / "gateway.db"

print(f"Checking database at: {db_path}")

if not db_path.exists():
    print("Database file not found!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if columns exist
    cursor.execute("PRAGMA table_info(model_endpoints)")
    columns = [info[1] for info in cursor.fetchall()]

    print(f"Current columns: {columns}")

    if "min_interval_seconds" not in columns:
        print("Adding column: min_interval_seconds")
        cursor.execute("ALTER TABLE model_endpoints ADD COLUMN min_interval_seconds INTEGER DEFAULT 0")
    else:
        print("Column min_interval_seconds already exists")

    if "last_request_at" not in columns:
        print("Adding column: last_request_at")
        cursor.execute("ALTER TABLE model_endpoints ADD COLUMN last_request_at TIMESTAMP")
    else:
        print("Column last_request_at already exists")

    conn.commit()
    print("✅ Database schema updated successfully!")

except Exception as e:
    print(f"❌ Error updating database: {e}")
    conn.rollback()
finally:
    conn.close()
