"""LLM 客户端占位实现。

后续可用该接口接入规划、定位或验证阶段的大语言模型调用。当前版本不绑定具体供应商，
以便保持离线测试的可复现性。
"""

from __future__ import annotations

from typing import Any


class LLMClient:
    """封装结构化大语言模型调用的客户端边界。"""

    def json_call(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """请求模型按给定 schema 返回 JSON 结构。"""

        return {
            "status": "unavailable",
            "reason": "LLM integration is out of scope for the offline core pass",
            "prompt": prompt,
            "schema": schema,
        }
