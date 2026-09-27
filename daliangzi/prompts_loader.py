"""提示词加载。

提示词放在 prompts/*.md，用户可以随时改。改完不用重启服务。
"""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_CACHE: dict[str, tuple[float, str]] = {}


def load_prompt(name: str) -> str:
    """按文件名读取提示词（不含 .md）。带 mtime 缓存，改了自动生效。"""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"提示词文件不存在：{path}")

    mtime = path.stat().st_mtime
    cached = _CACHE.get(name)
    if cached and cached[0] == mtime:
        return cached[1]

    text = path.read_text(encoding="utf-8")
    _CACHE[name] = (mtime, text)
    return text


def list_prompts() -> list[dict[str, str | float]]:
    out = []
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        out.append({
            "name": path.stem,
            "file": path.name,
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
        })
    return out


def save_prompt(name: str, content: str) -> None:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"提示词文件不存在：{path}")
    path.write_text(content, encoding="utf-8")
    _CACHE.pop(name, None)
