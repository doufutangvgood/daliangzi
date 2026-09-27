"""评论接入层：解析、清洗、平台适配。"""

from .model import Axis, Comment, Label, Stance
from .parse import CleanReport, LoadResult, load_from_file, load_from_text, records_to_comments

__all__ = [
    "Axis",
    "Comment",
    "Label",
    "Stance",
    "CleanReport",
    "LoadResult",
    "load_from_file",
    "load_from_text",
    "records_to_comments",
]
