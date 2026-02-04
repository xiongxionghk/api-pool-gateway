"""请求/响应格式转换器 - OpenAI ↔ Anthropic"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RequestConverter:
    """请求格式转换器"""

    def convert(
        self,
        body: Dict[str, Any],
        from_format: str,
        to_format: str,
        target_model: str
    ) -> Dict[str, Any]:
        """
        转换请求格式

        Args:
            body: 原始请求体
            from_format: 源格式 ("openai" or "anthropic")
            to_format: 目标格式 ("openai" or "anthropic")
            target_model: 目标模型ID

        Returns:
            转换后的请求体
        """
        if from_format == to_format:
            # 格式相同，只替换模型名
            result = body.copy()
            result["model"] = target_model
            return result

        if from_format == "anthropic" and to_format == "openai":
            return self._anthropic_to_openai(body, target_model)

        if from_format == "openai" and to_format == "anthropic":
            return self._openai_to_anthropic(body, target_model)

        # 默认返回原样
        result = body.copy()
        result["model"] = target_model
        return result

    def _anthropic_to_openai(self, body: Dict[str, Any], target_model: str) -> Dict[str, Any]:
        """Anthropic Messages -> OpenAI Chat Completions"""
        messages = []

        # 处理 system
        system = body.get("system")
        if system:
            if isinstance(system, str):
                messages.append({"role": "system", "content": system})
            elif isinstance(system, list):
                # 多个 system block
                system_text = " ".join(
                    block.get("text", "") for block in system if block.get("type") == "text"
                )
                if system_text:
                    messages.append({"role": "system", "content": system_text})

        # 处理 messages
        for msg in body.get("messages", []):
            role = msg.get("role")
            content = msg.get("content")

            if role == "user":
                openai_content = self._convert_content_to_openai(content)
                messages.append({"role": "user", "content": openai_content})

            elif role == "assistant":
                openai_content = self._convert_assistant_content_to_openai(content)
                messages.append(openai_content)

        result = {
            "model": target_model,
            "messages": messages,
        }

        # 复制通用参数
        if "max_tokens" in body:
            result["max_tokens"] = body["max_tokens"]
        if "temperature" in body:
            result["temperature"] = body["temperature"]
        if "top_p" in body:
            result["top_p"] = body["top_p"]
        if "stream" in body:
            result["stream"] = body["stream"]

        # 转换 tools
        if "tools" in body:
            result["tools"] = self._convert_tools_to_openai(body["tools"])

        return result

    def _openai_to_anthropic(self, body: Dict[str, Any], target_model: str) -> Dict[str, Any]:
        """OpenAI Chat Completions -> Anthropic Messages"""
        messages = []
        system = None

        for msg in body.get("messages", []):
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                system = content

            elif role == "user":
                anthropic_content = self._convert_content_to_anthropic(content)
                messages.append({"role": "user", "content": anthropic_content})

            elif role == "assistant":
                anthropic_content = self._convert_assistant_content_to_anthropic(msg)
                messages.append({"role": "assistant", "content": anthropic_content})

            elif role == "tool":
                # OpenAI tool result -> Anthropic tool_result
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": content
                    }]
                })

        result = {
            "model": target_model,
            "messages": messages,
            "max_tokens": body.get("max_tokens", 4096),
        }

        if system:
            result["system"] = system

        if "temperature" in body:
            result["temperature"] = body["temperature"]
        if "top_p" in body:
            result["top_p"] = body["top_p"]
        if "stream" in body:
            result["stream"] = body["stream"]

        # 转换 tools
        if "tools" in body:
            result["tools"] = self._convert_tools_to_anthropic(body["tools"])

        return result

    def _convert_content_to_openai(self, content: Any) -> Any:
        """转换 content 到 OpenAI 格式"""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            result = []
            for block in content:
                block_type = block.get("type")
                if block_type == "text":
                    result.append({"type": "text", "text": block.get("text", "")})
                elif block_type == "image":
                    source = block.get("source", {})
                    if source.get("type") == "base64":
                        result.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{source.get('media_type')};base64,{source.get('data')}"
                            }
                        })
                elif block_type == "tool_result":
                    # 作为普通文本处理
                    result.append({"type": "text", "text": json.dumps(block)})
            return result if len(result) > 1 else (result[0]["text"] if result else "")

        return str(content)

    def _convert_assistant_content_to_openai(self, content: Any) -> Dict[str, Any]:
        """转换 assistant content 到 OpenAI 格式"""
        if isinstance(content, str):
            return {"role": "assistant", "content": content}

        if isinstance(content, list):
            text_parts = []
            tool_calls = []

            for block in content:
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}))
                        }
                    })

            result = {"role": "assistant", "content": " ".join(text_parts) or None}
            if tool_calls:
                result["tool_calls"] = tool_calls
            return result

        return {"role": "assistant", "content": str(content)}

    def _convert_content_to_anthropic(self, content: Any) -> Any:
        """转换 content 到 Anthropic 格式"""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            result = []
            for item in content:
                item_type = item.get("type")
                if item_type == "text":
                    result.append({"type": "text", "text": item.get("text", "")})
                elif item_type == "image_url":
                    # 需要解析 data URL
                    url = item.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        # 解析 data:image/png;base64,xxx
                        parts = url.split(",", 1)
                        if len(parts) == 2:
                            media_type = parts[0].split(":")[1].split(";")[0]
                            data = parts[1]
                            result.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": data
                                }
                            })
            return result if result else content

        return content

    def _convert_assistant_content_to_anthropic(self, msg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """转换 assistant message 到 Anthropic 格式"""
        result = []

        content = msg.get("content")
        if content:
            if isinstance(content, str):
                result.append({"type": "text", "text": content})
            elif isinstance(content, list):
                result.extend(content)

        # 转换 tool_calls
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            result.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": func.get("name"),
                "input": json.loads(func.get("arguments", "{}"))
            })

        return result if result else [{"type": "text", "text": ""}]

    def _convert_tools_to_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换 Anthropic tools 到 OpenAI 格式"""
        result = []
        for tool in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {})
                }
            })
        return result

    def _convert_tools_to_anthropic(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换 OpenAI tools 到 Anthropic 格式"""
        result = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                result.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
        return result


class ResponseConverter:
    """响应格式转换器"""

    def convert(
        self,
        body: Dict[str, Any],
        from_format: str,
        to_format: str,
        original_model: str
    ) -> Dict[str, Any]:
        """转换响应格式"""
        if from_format == to_format:
            return body

        if from_format == "openai" and to_format == "anthropic":
            return self._openai_to_anthropic(body, original_model)

        if from_format == "anthropic" and to_format == "openai":
            return self._anthropic_to_openai(body, original_model)

        return body

    def _openai_to_anthropic(self, body: Dict[str, Any], model: str) -> Dict[str, Any]:
        """OpenAI -> Anthropic 响应"""
        choices = body.get("choices", [])
        if not choices:
            return body

        choice = choices[0]
        message = choice.get("message", {})

        content = []
        if message.get("content"):
            content.append({"type": "text", "text": message["content"]})

        # 转换 tool_calls
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            content.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": func.get("name"),
                "input": json.loads(func.get("arguments", "{}"))
            })

        # 转换 stop_reason
        finish_reason = choice.get("finish_reason")
        stop_reason_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
        }
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        # 转换 usage
        usage = body.get("usage", {})
        anthropic_usage = {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

        return {
            "id": body.get("id", "msg_pool"),
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": anthropic_usage,
        }

    def _anthropic_to_openai(self, body: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Anthropic -> OpenAI 响应"""
        content_blocks = body.get("content", [])

        text_parts = []
        tool_calls = []

        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input", {}))
                    }
                })

        message = {
            "role": "assistant",
            "content": " ".join(text_parts) or None,
        }
        if tool_calls:
            message["tool_calls"] = tool_calls

        # 转换 finish_reason
        stop_reason = body.get("stop_reason")
        finish_reason_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }
        finish_reason = finish_reason_map.get(stop_reason, "stop")

        # 转换 usage
        usage = body.get("usage", {})
        openai_usage = {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }

        return {
            "id": body.get("id", "chatcmpl-pool"),
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }],
            "usage": openai_usage,
        }

    def convert_stream_line(
        self,
        line: str,
        from_format: str,
        to_format: str,
        original_model: str
    ) -> Optional[str]:
        """转换流式响应行"""
        if not line.startswith("data: "):
            return line

        if line.strip() == "data: [DONE]":
            return line

        try:
            data = json.loads(line[6:])  # 去掉 "data: " 前缀

            if from_format == to_format:
                return line

            if from_format == "openai" and to_format == "anthropic":
                converted = self._convert_stream_openai_to_anthropic(data, original_model)
            elif from_format == "anthropic" and to_format == "openai":
                converted = self._convert_stream_anthropic_to_openai(data, original_model)
            else:
                converted = data

            if converted:
                return f"data: {json.dumps(converted)}"
            return None

        except json.JSONDecodeError:
            return line

    def _convert_stream_openai_to_anthropic(self, data: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        """转换 OpenAI 流式 chunk 到 Anthropic 格式"""
        choices = data.get("choices", [])
        if not choices:
            return None

        delta = choices[0].get("delta", {})
        content = delta.get("content")

        if content:
            return {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "text_delta",
                    "text": content
                }
            }

        return None

    def _convert_stream_anthropic_to_openai(self, data: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        """转换 Anthropic 流式 event 到 OpenAI 格式"""
        event_type = data.get("type")

        if event_type == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                return {
                    "id": "chatcmpl-pool",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": delta.get("text", "")},
                        "finish_reason": None
                    }]
                }

        return None
