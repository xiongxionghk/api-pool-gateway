import sqlite3
from pathlib import Path

# 定位数据库
base_dir = Path(__file__).resolve().parent.parent
db_path = base_dir / "data" / "gateway.db"

print(f"检查数据库: {db_path}")

if not db_path.exists():
    print("数据库文件不存在，跳过迁移（首次运行时会自动创建）")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 检查 request_logs 表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='request_logs'")
    if not cursor.fetchone():
        print("request_logs 表不存在，跳过迁移")
    else:
        cursor.execute("PRAGMA table_info(request_logs)")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"request_logs 表当前字段: {columns}")

        # 添加 request_body 字段
        if "request_body" not in columns:
            print("添加字段: request_body")
            cursor.execute("ALTER TABLE request_logs ADD COLUMN request_body TEXT")
        else:
            print("字段 request_body 已存在")

        # 添加 response_body 字段
        if "response_body" not in columns:
            print("添加字段: response_body")
            cursor.execute("ALTER TABLE request_logs ADD COLUMN response_body TEXT")
        else:
            print("字段 response_body 已存在")

        # 删除旧的 request_summary 字段（如果存在）
        if "request_summary" in columns:
            print("注意: request_summary 字段仍存在，可以手动删除（SQLite 不支持 DROP COLUMN）")

    conn.commit()
    print("✅ 数据库 schema 更新成功！")

except Exception as e:
    print(f"❌ 更新数据库时出错: {e}")
    conn.rollback()
finally:
    conn.close()
