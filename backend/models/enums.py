from enum import Enum

class ApiFormat(str, Enum):
    """API 格式类型"""
    OPENAI = "openai"           # /v1/chat/completions
    ANTHROPIC = "anthropic"     # /v1/messages


class PoolType(str, Enum):
    """池类型"""
    TOOL = "tool"
    NORMAL = "normal"
    ADVANCED = "advanced"
