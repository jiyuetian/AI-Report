"""输入净化与文件名安全（P3-2 / P3-3 / P4-2）

设计原则：
- 后端做"净化"（剥离危险标签/事件处理器/路径遍历字符），输出仍走 JSON，
  由前端 React 自动转义渲染（已 grep 确认 src 内无 dangerouslySetInnerHTML）。
- 不做实体转义存储，避免二次转义破坏正常中文显示。
"""
import re

_MAX_LEN = 200

# 剥离会执行脚本/嵌入外部资源的危险标签
_DANGEROUS_TAG_RE = re.compile(
    r"<(?:\s*/?\s*(?:script|iframe|object|embed|link|meta|style|img|svg|"
    r"form|base|frame|frameset|video|audio|math)\b[^>]*)>",
    re.IGNORECASE,
)
_EVENT_HANDLER_RE = re.compile(r"\s\son\w+\s*=\s*", re.IGNORECASE)
_JAVASCRIPT_RE = re.compile(r"javascript:", re.IGNORECASE)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str, max_len: int = _MAX_LEN) -> str:
    """净化自由文本：去控制字符、剥离危险 HTML 标签/事件处理器/javascript: URI，并限长。"""
    if not isinstance(value, str):
        return value
    value = _CONTROL_CHAR_RE.sub("", value)
    value = _DANGEROUS_TAG_RE.sub("", value)
    value = _EVENT_HANDLER_RE.sub(" ", value)
    value = _JAVASCRIPT_RE.sub("", value)
    return value[:max_len]


def sanitize_filename(filename: str, max_len: int = _MAX_LEN) -> str:
    """净化文件名：仅保留 basename、去路径遍历/控制字符/非法字符、限长。"""
    if not isinstance(filename, str):
        filename = str(filename)
    # 去目录，只留 basename
    filename = filename.replace("\\", "/").split("/")[-1]
    filename = _CONTROL_CHAR_RE.sub("", filename)
    # 替换文件系统非法字符
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    filename = filename.strip(". ").strip()
    if not filename:
        filename = "upload"
    return filename[:max_len]
