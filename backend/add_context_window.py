#!/usr/bin/env python3
"""添加 context_window 字段到 model_endpoints 表"""

import sqlite3
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "data" / "gateway.db"

def main():
    print(f"数据库路径: {DB_PATH}")

    if not DB_PATH.exists():
        print("❌ 数据库文件不存在")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_endpoints'")
        if not cursor.fetchone():
            print("❌ model_endpoints 表不存在")
            return

        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(model_endpoints)")
        columns = [row[1] for row in cursor.fetchall()]

        if "context_window" in columns:
            print("✅ context_window 字段已存在，无需添加")
        else:
            print("添加 context_window 字段...")
            cursor.execute("ALTER TABLE model_endpoints ADD COLUMN context_window INTEGER")
            conn.commit()
            print("✅ context_window 字段添加成功")

        # 显示当前字段
        cursor.execute("PRAGMA table_info(model_endpoints)")
        print("\n当前 model_endpoints 表字段:")
        for row in cursor.fetchall():
            print(f"  - {row[1]} ({row[2]})")

    except Exception as e:
        print(f"❌ 错误: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
