#!/usr/bin/env python3
"""查询响应体中包含错误信息的日志"""

import sqlite3
import json
from datetime import datetime, timedelta

db_path = '/Users/yanghai/api-pool-gateway/data/gateway_recovered.db'

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 查询最近 7 天内有 response_body 的记录
seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()

cur.execute("""
    SELECT
        id,
        pool_type,
        requested_model,
        actual_model,
        provider_name,
        success,
        status_code,
        error_message,
        latency_ms,
        response_body,
        created_at
    FROM request_logs
    WHERE response_body IS NOT NULL
      AND created_at >= ?
    ORDER BY created_at DESC
    LIMIT 100
""", (seven_days_ago,))

rows = cur.fetchall()

print(f"找到 {len(rows)} 条有响应体的日志记录\n")
print("=" * 80)

error_logs = []

for row in rows:
    try:
        response_body = json.loads(row['response_body'])
        raw_stream = response_body.get('raw_stream', '')

        # 检测错误关键词
        error_keywords = [
            'context_length_exceeded',
            'invalid_request_error',
            'error',
            'Error',
            '"code"',
            '"type":"error"'
        ]

        has_error = any(keyword in raw_stream for keyword in error_keywords)

        if has_error:
            error_logs.append({
                'id': row['id'],
                'created_at': row['created_at'],
                'provider': row['provider_name'],
                'model': row['actual_model'],
                'success': row['success'],
                'status_code': row['status_code'],
                'error_message': row['error_message'],
                'raw_stream': raw_stream[:500]  # 只显示前 500 字符
            })
    except:
        continue

print(f"\n发现 {len(error_logs)} 条响应体包含错误信息的记录:\n")

for log in error_logs:
    print(f"ID: {log['id']}")
    print(f"时间: {log['created_at']}")
    print(f"服务商: {log['provider']}")
    print(f"模型: {log['model']}")
    print(f"成功标记: {log['success']}")
    print(f"状态码: {log['status_code']}")
    print(f"错误消息: {log['error_message']}")
    print(f"响应体片段:\n{log['raw_stream'][:300]}")
    print("-" * 80)

conn.close()
