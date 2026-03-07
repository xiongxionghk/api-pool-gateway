#!/usr/bin/env python3
"""测试 failover 日志功能"""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from models.database import RequestLog


class TestRequestLogSchema(unittest.TestCase):
    """测试 RequestLog 表结构包含 failover 字段"""

    def test_requestlog_has_failover_fields(self):
        """验证 RequestLog 包含所有 failover 相关字段"""
        fields = {c.name for c in RequestLog.__table__.columns}

        # 验证新增字段存在
        self.assertIn("request_id", fields, "缺少 request_id 字段")
        self.assertIn("attempt_index", fields, "缺少 attempt_index 字段")
        self.assertIn("failover_reason", fields, "缺少 failover_reason 字段")
        self.assertIn("previous_model", fields, "缺少 previous_model 字段")
        self.assertIn("configured_timeout_ms", fields, "缺少 configured_timeout_ms 字段")


if __name__ == "__main__":
    unittest.main()
