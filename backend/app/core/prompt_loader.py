"""被控提示词加载器
让 AI 节点的提示词外置到 core/prompts/*.md，可脱离代码单独迭代优化。
读取约定：节点执行前先 load_prompt 读取提示词（=契约）；文件缺失时回退到内置默认。
"""
import os
from typing import Dict, Tuple

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
# 简单文件缓存，避免每次调用都读盘；改文件后缀 __token 即可强制重载
_CACHE: Dict[str, Tuple[float, str]] = {}


def _read_prompt_file(slug: str) -> str:
    """读取提示词文件内容；不存在返回 None"""
    path = os.path.join(_PROMPTS_DIR, f"{slug}.md")
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cached = _CACHE.get(slug)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    _CACHE[slug] = (mtime, content)
    return content


def load_prompt(slug: str, default: str, **kwargs) -> str:
    """
    取提示词：
    1) 若 Prompt 中心有"启用中的覆盖"，用覆盖内容（管理员在管理中心迭代的最新生效版）；
    2) 否则读 prompts/{slug}.md（内置种子）；
    3) 文件缺失/异常则回退 default。
    kwargs 中的键会替换模板里同名 {key} 占位符。
    说明：使用字面 replace 而非 str.format，避免模板内 JSON 花括号转义冲突。
    """
    try:
        from app.core.prompt_manager import loaded_prompt
        return loaded_prompt(slug, default, **kwargs)
    except Exception as e:
        print(f"[prompt_loader] Prompt中心不可用，回退文件/内置: {e}")
        content = _read_prompt_file(slug)
        if content is None:
            content = default
        for key, value in kwargs.items():
            content = content.replace("{" + key + "}", str(value))
        return content


def prompt_file_path(slug: str) -> str:
    """返回提示词文件的绝对路径（供控制文档/日志引用）"""
    return os.path.join(_PROMPTS_DIR, f"{slug}.md")