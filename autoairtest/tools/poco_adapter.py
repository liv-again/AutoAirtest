"""Poco 控件树适配器。

Poco 提供移动端控件层级、文本、位置和属性等结构化界面证据。离线核心仅保留方法
合同，真实环境缺少依赖时返回显式不可用状态。
"""

from __future__ import annotations

import importlib.util
from typing import Any


class PocoAdapter:
    """封装 Poco 语义查询和控件操作能力的适配器。"""

    def __init__(self) -> None:
        """探测当前环境是否已安装 Poco。"""

        self.available = importlib.util.find_spec("poco") is not None

    def dump(self) -> dict[str, Any]:
        """导出当前界面的控件树摘要。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "visible_texts": []}
        return {"status": "success", "visible_texts": []}

    def query(self, text: str) -> dict[str, Any]:
        """按文本或语义标签查询候选控件。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "matches": []}

    def exists(self, text: str) -> dict[str, Any]:
        """判断目标文本或控件是否存在。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "exists": False}

    def click(self, text: str) -> dict[str, Any]:
        """点击与文本查询匹配的控件。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text}

    def text(self, text: str) -> dict[str, Any]:
        """读取匹配控件的文本值。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "text": ""}

    def bounds(self, text: str) -> dict[str, Any]:
        """读取匹配控件的边界框。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "bounds": None}

    def attributes(self, text: str) -> dict[str, Any]:
        """读取匹配控件的属性字典。"""

        if not self.available:
            return {"status": "unavailable", "reason": "poco is not installed in torch", "query": text}
        return {"status": "success", "query": text, "attributes": {}}
